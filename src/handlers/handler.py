"""
SQS-triggered Lambda handler

    Reads email from S3, runs Bedrock analysis, forwards/blocks via SES
    Processes up to 10 records per invocation concurrently (all I/O-bound)
    Returns batchItemFailures so SQS only retries the messages that actually failed
"""

import json
import os
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from email import message_from_string
from typing import Dict, List, Optional

import boto3

s3 = boto3.client("s3")
ses = boto3.client("ses")
dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client(
    "bedrock-runtime", region_name=os.environ.get("BEDROCK_REGION", "us-east-1")
)

FORWARD_TO_EMAIL = os.environ["FORWARD_TO_EMAIL"]
SENDER_EMAIL = os.environ["SENDER_EMAIL"]
ANALYSIS_RESULTS_TABLE = os.environ["ANALYSIS_RESULTS_TABLE"]
BLOCKLIST_TABLE = os.environ.get("BLOCKLIST_TABLE", "")

analysis_table = dynamodb.Table(ANALYSIS_RESULTS_TABLE)


def _log_metric(name: str, value: float, **tags) -> None:
    # format: METRIC <name> <ms> [key=val ...]
    # plain float so CWL Insights can run pct()/avg() on it directly
    tag_str = " ".join(f"{k}={v}" for k, v in tags.items())
    print(f"METRIC {name} {value:.2f} {tag_str}".strip())


def extract_urls(text: str) -> List[str]:
    pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    return list(set(re.findall(pattern, text, re.IGNORECASE)))


def analyze_with_bedrock(email_data: Dict) -> Dict:
    subject = email_data.get("subject", "")
    body = email_data.get("body_text", "")
    sender = email_data.get("from", "")
    urls = extract_urls(body)

    prompt = f"""Analyze this email for security threats (phishing, malware, scams).

FROM: {sender}
SUBJECT: {subject}
BODY: {body[:1000]}
URLs: {urls}

Check for: phishing, malicious links, scams, typosquatting, social engineering.

Respond in JSON only:
{{
  "threat_level": "HIGH|MEDIUM|LOW",
  "reasoning": "brief explanation",
  "suspicious_indicators": ["indicator1"],
  "suspicious_urls": ["url1"],
  "recommendation": "BLOCK|WARN|ALLOW"
}}"""

    try:
        t0 = time.perf_counter()
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 512,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
        )
        bedrock_ms = (time.perf_counter() - t0) * 1000
        content = json.loads(response["body"].read())["content"][0]["text"]

        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        threat = result.get("threat_level", "MEDIUM")
        _log_metric("bedrock_latency", bedrock_ms, threat=threat)
        return {
            "threat_level": threat,
            "reasoning": result.get("reasoning", ""),
            "suspicious_indicators": result.get("suspicious_indicators", []),
            "suspicious_urls": result.get("suspicious_urls", []),
            "recommendation": result.get("recommendation", "WARN"),
            "urls": urls,
            "bedrock_ms": round(bedrock_ms, 2),
        }

    except Exception as e:
        print(f"Bedrock error: {e}")
        error_str = str(e)
        reasoning = (
            "AI analysis unavailable. Email forwarded with caution."
            if "use case" in error_str or "ResourceNotFoundException" in error_str
            else "Analysis failed. Email forwarded with caution."
        )
        return {
            "threat_level": "MEDIUM",
            "reasoning": reasoning,
            "suspicious_indicators": [],
            "suspicious_urls": [],
            "recommendation": "WARN",
            "urls": urls,
            "error": error_str,
        }


def forward_email(email_data: Dict, analysis: Dict) -> str:
    threat_level = analysis["threat_level"]
    subject = email_data.get("subject", "No Subject")
    body_text = email_data.get("body_text", "")
    body_html = email_data.get("body_html", "")
    sender = email_data.get("from", "unknown")

    if threat_level == "HIGH":
        print(f"BLOCKED: {subject}")
        indicators = (
            "\n".join(f"  - {i}" for i in analysis["suspicious_indicators"]) or "  none"
        )
        sus_urls = (
            "\n".join(f"  - {u}" for u in analysis["suspicious_urls"]) or "  none"
        )
        alert = f"""[BLOCKED] This email was not forwarded.

From:    {sender}
Subject: {subject}
Date:    {email_data.get("date", "unknown")}

Threat analysis: {analysis["reasoning"]}

Suspicious indicators:
{indicators}

Suspicious URLs:
{sus_urls}

---
inboXray
"""
        ses.send_email(
            Source=SENDER_EMAIL,
            Destination={"ToAddresses": [FORWARD_TO_EMAIL]},
            Message={
                "Subject": {"Data": f"[BLOCKED] {subject}"},
                "Body": {"Text": {"Data": alert}},
            },
        )
        return "blocked"

    if threat_level == "MEDIUM":
        subject = f"[SUSPICIOUS] {subject}"
        indicators = (
            "\n".join(f"  - {i}" for i in analysis["suspicious_indicators"]) or "  none"
        )
        warning = f"""[SUSPICIOUS EMAIL]

Threat analysis: {analysis["reasoning"]}

Indicators:
{indicators}

{"=" * 60}

"""
        body_text = warning + body_text

        if body_html:
            ind_html = "".join(
                f"<li>{i}</li>" for i in analysis["suspicious_indicators"]
            )
            html_warning = (
                '<div style="background:#fff3cd;border:1px solid #856404;padding:12px;'
                'margin-bottom:16px;font-family:sans-serif;font-size:13px;">'
                f"<strong>[SUSPICIOUS EMAIL]</strong><br>{analysis['reasoning']}"
                + (f"<ul>{ind_html}</ul>" if ind_html else "")
                + "</div>"
            )
            body_html = html_warning + body_html

    body = {"Text": {"Data": body_text}}
    if body_html:
        body["Html"] = {"Data": body_html}

    ses.send_email(
        Source=SENDER_EMAIL,
        Destination={"ToAddresses": [FORWARD_TO_EMAIL]},
        Message={"Subject": {"Data": subject}, "Body": body},
    )
    print(f"Forwarded: threat={threat_level}")
    return "forwarded"


def _process_record(record: Dict) -> Optional[str]:
    # returns messageId on failure (for batchItemFailures), None on success
    t0 = time.perf_counter()
    message_id = record.get("messageId", "unknown")
    try:
        body = json.loads(record["body"])
        ses_message = json.loads(body["Message"]) if "Message" in body else body

        if "receipt" in ses_message:
            bucket = ses_message["receipt"]["action"]["bucketName"]
            key = ses_message["receipt"]["action"]["objectKey"]
        else:
            bucket = ses_message["s3_bucket"]
            key = ses_message["s3_key"]

        print(f"Processing s3://{bucket}/{key}")

        raw = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        msg = message_from_string(raw)

        email_data = {
            "from": msg.get("From", ""),
            "to": msg.get("To", ""),
            "subject": msg.get("Subject", ""),
            "date": msg.get("Date", ""),
            "message_id": msg.get("Message-ID", ""),
            "body_text": "",
            "body_html": "",
        }

        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain" and not email_data["body_text"]:
                    email_data["body_text"] = part.get_payload(decode=True).decode(
                        "utf-8", errors="ignore"
                    )
                elif ct == "text/html" and not email_data["body_html"]:
                    email_data["body_html"] = part.get_payload(decode=True).decode(
                        "utf-8", errors="ignore"
                    )
        else:
            payload = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
            if msg.get_content_type() == "text/html":
                email_data["body_html"] = payload
            else:
                email_data["body_text"] = payload

        # Loop guard: drop automated replies and emails sent by this system itself
        # Auto-Submitted header (RFC 3834): any value other than "no" means auto-generated
        auto_submitted = msg.get("Auto-Submitted", "no").lower()
        x_auto = msg.get("X-Auto-Response-Suppress", "")
        from_addr = email_data["from"].lower()
        is_self = (
            SENDER_EMAIL.lower() in from_addr
            or FORWARD_TO_EMAIL.lower() in from_addr
        )
        if auto_submitted != "no" or x_auto or is_self:
            print(f"Skipping automated/self email: Auto-Submitted={auto_submitted!r} from={email_data['from']}")
            s3.delete_object(Bucket=bucket, Key=key)
            return None

        if BLOCKLIST_TABLE:
            try:
                result = dynamodb.Table(BLOCKLIST_TABLE).get_item(
                    Key={"sender": email_data["from"]}
                )
                if "Item" in result:
                    print(f"Blocked sender: {email_data['from']}")
                    s3.delete_object(Bucket=bucket, Key=key)
                    return None
            except Exception as e:
                print(f"Blocklist error: {e}")

        analysis = analyze_with_bedrock(email_data)
        status = forward_email(email_data, analysis)

        analysis_table.put_item(
            Item={
                "message_id": email_data["message_id"] or key,
                "timestamp": int(time.time()),
                "from": email_data["from"],
                "subject": email_data["subject"],
                "threat_level": analysis["threat_level"],
                "reasoning": analysis["reasoning"],
                "suspicious_indicators": analysis["suspicious_indicators"],
                "suspicious_urls": analysis["suspicious_urls"],
                "urls": analysis["urls"],
                "recommendation": analysis["recommendation"],
                "forward_status": status,
                "s3_key": key,
                "bedrock_ms": Decimal(str(analysis.get("bedrock_ms", 0))),
            }
        )

        total_ms = (time.perf_counter() - t0) * 1000
        _log_metric(
            "email_processing_latency",
            total_ms,
            threat=analysis["threat_level"],
            status=status,
        )
        print(f"Done: threat={analysis['threat_level']} status={status} total_ms={total_ms:.0f}")
        s3.delete_object(Bucket=bucket, Key=key)
        return None  # success

    except Exception as e:
        print(f"Error processing {message_id}: {e}")
        traceback.print_exc()
        return message_id  # signal failure to SQS for retry


def lambda_handler(event, context):
    records = event["Records"]
    batch_size = len(records)
    batch_start = time.perf_counter()

    # all records run concurrently — work is I/O-bound so threads don't compete
    failed_message_ids = []
    with ThreadPoolExecutor(max_workers=batch_size) as executor:
        future_to_id = {
            executor.submit(_process_record, record): record.get("messageId")
            for record in records
        }
        for future in as_completed(future_to_id):
            result = future.result()
            if result is not None:
                failed_message_ids.append(result)

    batch_ms = (time.perf_counter() - batch_start) * 1000
    succeeded = batch_size - len(failed_message_ids)
    _log_metric("batch_latency", batch_ms, batch_size=batch_size, succeeded=succeeded)
    print(f"Batch done: {succeeded}/{batch_size} succeeded in {batch_ms:.0f}ms")

    # only retry failed messages, not the whole batch
    if failed_message_ids:
        return {
            "batchItemFailures": [
                {"itemIdentifier": mid} for mid in failed_message_ids
            ]
        }

    return {"statusCode": 200}

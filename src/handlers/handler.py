"""
Lambda function handler for processing incoming emails from S3, sanitizing, and forwarding
"""

import json
import os

from src.adapters.adapter import AWSAdapter
from src.core.sanitizer import EmailSanitizer


def handler(event, context):
    """Lambda handler"""
    sanitizer = EmailSanitizer()
    aws = AWSAdapter()

    forward_to = os.environ.get("FORWARD_TO_EMAIL")
    sender_email = os.environ.get("SENDER_EMAIL")
    enable_analysis = os.environ.get("ENABLE_ANALYSIS", "false").lower() == "true"
    analysis_queue_url = os.environ.get("ANALYSIS_QUEUE_URL")

    try:
        for record in event["Records"]:
            bucket = record["s3"]["bucket"]["name"]
            key = record["s3"]["object"]["key"]

            print(f"Processing email from s3://{bucket}/{key}")

            raw_email = aws.get_email_from_s3(bucket, key)

            email_data = sanitizer.sanitize(raw_email)

            sender = email_data["from"]
            if aws.is_sender_blocked(sender):
                print(f"Blocked email from {sender}")
                aws.delete_email_from_s3(bucket, key)
                continue

            # Phase 1: Forward clean email
            aws.send_email(
                to_address=forward_to,
                subject=f"[Sanitized] {email_data['subject']}",
                body_html=email_data["body_html"],
                body_text=email_data["body_text"],
                from_address=sender_email,
            )

            print(f"Forwarded email to {forward_to}")

            # Phase 2: Push to SQS for deep analysis (optional)
            if enable_analysis and analysis_queue_url:
                analysis_job = {
                    "s3_bucket": bucket,
                    "s3_key": key,
                    "email_from": sender,
                    "email_to": email_data["to"],
                    "subject": email_data["subject"],
                    "date": email_data["date"],
                    "message_id": email_data["message_id"],
                }
                aws.push_to_sqs(analysis_queue_url, analysis_job)
                print(f"Pushed analysis job to SQS: {email_data['message_id']}")

            # Keep email in S3 if analysis enabled, delete otherwise
            if not enable_analysis:
                aws.delete_email_from_s3(bucket, key)

        return {"statusCode": 200, "body": json.dumps("Email processed successfully")}

    except Exception as e:
        print(f"Error processing email: {str(e)}")
        return {"statusCode": 500, "body": json.dumps(f"Error: {str(e)}")}

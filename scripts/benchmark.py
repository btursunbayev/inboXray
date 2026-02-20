"""
Benchmark script for inboXray performance

    Injects synthetic emails into SQS, waits for Lambda to drain,
    Then queries CloudWatch Logs Insights for P50/P95/P99
    Usage: python scripts/benchmark.py --count 10
"""

import argparse
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

import boto3

# ── Config ────────────────────────────────────────────────────────────────────
REGION = "us-east-1"
LOG_GROUP = "/aws/lambda/inboxray-email-analyzer"


def get_terraform_output(key: str) -> str:
    result = subprocess.run(
        ["terraform", "output", "-raw", key],
        capture_output=True,
        text=True,
        cwd="terraform",
    )
    if result.returncode != 0:
        raise RuntimeError(f"terraform output {key} failed: {result.stderr}")
    return result.stdout.strip()


def get_config():
    return {
        "s3_bucket": get_terraform_output("s3_bucket_name"),
        "sqs_url": get_terraform_output("analysis_queue_url"),
    }


# ── Synthetic email templates ─────────────────────────────────────────────────
PHISHING_TEMPLATE = """\
From: security@paypa1-secure.com
To: user@btursunbayev.com
Subject: Urgent: Your account has been limited
Date: {date}
Message-ID: <{msg_id}>
Content-Type: text/plain

Dear Customer,

Your PayPal account has been limited due to suspicious activity.
Click here immediately to verify: http://paypa1-secure.com/verify.php?token={token}

Failure to verify within 24 hours will result in permanent suspension

PayPal Security Team
"""

SAFE_TEMPLATE = """\
From: newsletter@example.com
To: user@btursunbayev.com
Subject: Weekly digest - {token}
Date: {date}
Message-ID: <{msg_id}>
Content-Type: text/plain

Hello,

Here is your weekly digest. Check out our latest blog posts at https://example.com/blog.

Thanks for subscribing.
"""

TEMPLATES = [PHISHING_TEMPLATE, SAFE_TEMPLATE]


def make_email(i: int) -> str:
    template = TEMPLATES[i % len(TEMPLATES)]
    return template.format(
        date=datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000"),
        msg_id=f"bench-{uuid.uuid4()}@test",
        token=uuid.uuid4().hex[:8],
    )


# ── Upload + enqueue ───────────────────────────────────────────────────────────
def upload_and_enqueue(
    s3_client, sqs_client, bucket: str, sqs_url: str, count: int
) -> list[str]:
    keys = []
    print(f"Uploading {count} synthetic emails to s3://{bucket}/benchmark/ ...")
    for i in range(count):
        key = f"benchmark/bench-{uuid.uuid4().hex}.eml"
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=make_email(i).encode(),
        )
        keys.append(key)

    print(f"Sending {count} SQS messages ...")
    start_ts = time.time()

    # SQS send_message_batch accepts up to 10 entries
    for batch_start in range(0, count, 10):
        batch = keys[batch_start : batch_start + 10]
        entries = [
            {
                "Id": str(idx),
                "MessageBody": json.dumps({"s3_bucket": bucket, "s3_key": key}),
            }
            for idx, key in enumerate(batch)
        ]
        sqs_client.send_message_batch(QueueUrl=sqs_url, Entries=entries)

    print(
        f"All messages enqueued at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
    )
    return keys, start_ts


# ── Wait for queue to drain ───────────────────────────────────────────────────
def wait_for_drain(
    sqs_client, main_url: str, dlq_url: str, timeout: int = 300, dlq_baseline: int = 0
) -> float:
    """
    Wait until the main queue has been empty (visible + in-flight = 0) for
    16 consecutive seconds. Reports new DLQ messages (above baseline) as failures
    """
    print("Waiting for processing to complete ", end="", flush=True)
    deadline = time.time() + timeout
    consecutive_empty = 0
    required_consecutive = 4  # 4 x 4s = 16s quiet period

    while time.time() < deadline:
        main_attrs = sqs_client.get_queue_attributes(
            QueueUrl=main_url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
            ],
        )["Attributes"]
        dlq_attrs = sqs_client.get_queue_attributes(
            QueueUrl=dlq_url,
            AttributeNames=["ApproximateNumberOfMessages"],
        )["Attributes"]

        visible = int(main_attrs["ApproximateNumberOfMessages"])
        in_flight = int(main_attrs["ApproximateNumberOfMessagesNotVisible"])
        dlq_depth = int(dlq_attrs["ApproximateNumberOfMessages"])
        new_failures = max(0, dlq_depth - dlq_baseline)

        if visible == 0 and in_flight == 0:
            consecutive_empty += 1
        else:
            consecutive_empty = 0

        if consecutive_empty >= required_consecutive:
            status = f"dlq_new={new_failures}" if new_failures else "ok"
            print(f" done ({status})")
            return time.time()

        print(".", end="", flush=True)
        time.sleep(4)

    print(" timed out")
    return time.time()


# ── Query CloudWatch Logs Insights ────────────────────────────────────────────
def query_metrics(logs_client, since_ts: float) -> dict:
    start = int(since_ts) - 10
    end = int(time.time()) + 60  # wide end window to cover indexing lag

    query = """
fields @timestamp, @message
| filter @message like /^METRIC /
| parse @message "METRIC * * *" as metric_name, metric_value, tags
| stats
    count() as n,
    avg(metric_value) as avg,
    pct(metric_value, 50) as p50,
    pct(metric_value, 95) as p95,
    pct(metric_value, 99) as p99,
    max(metric_value) as max
  by metric_name
"""
    # CWL Insights indexes logs with ~15-30s latency after Lambda writes them
    # Wait before querying so results are available
    print("Waiting 30s for CloudWatch Logs to index ...", flush=True)
    time.sleep(30)

    resp = logs_client.start_query(
        logGroupName=LOG_GROUP,
        startTime=start,
        endTime=end,
        queryString=query,
    )
    query_id = resp["queryId"]

    print("Querying CloudWatch Logs Insights ", end="", flush=True)
    for _ in range(20):
        time.sleep(6)
        result = logs_client.get_query_results(queryId=query_id)
        if result["status"] == "Complete":
            print(" done")
            return result["results"]
        print(".", end="", flush=True)

    print(" timed out")
    return []


# ── Print results ─────────────────────────────────────────────────────────────
def print_results(results: list, total_wall_ms: float, count: int):
    print()
    print("=" * 56)
    print("  inboXray Benchmark Results")
    print("=" * 56)

    metrics = {}
    for row in results:
        row_dict = {f["field"]: f["value"] for f in row}
        name = row_dict.get("metric_name", "").strip()
        if name:
            metrics[name] = row_dict

    labels = {
        "bedrock_latency": "Bedrock inference latency",
        "email_processing_latency": "End-to-end per-email latency",
        "batch_latency": "Batch wall-time (concurrent)",
    }

    for key, label in labels.items():
        if key in metrics:
            m = metrics[key]
            print(f"\n{label}:")
            print(f"  Samples : {m.get('n', '?')}")
            print(f"  Avg     : {float(m.get('avg', 0)):.0f} ms")
            print(f"  P50     : {float(m.get('p50', 0)):.0f} ms")
            print(f"  P95     : {float(m.get('p95', 0)):.0f} ms")
            print(f"  P99     : {float(m.get('p99', 0)):.0f} ms")
            print(f"  Max     : {float(m.get('max', 0)):.0f} ms")

    print(f"\nTotal wall time for {count} emails: {total_wall_ms / 1000:.1f}s")
    throughput = count / (total_wall_ms / 1000)
    print(f"Throughput: {throughput:.1f} emails/sec")
    print("=" * 56)


# ── Cleanup ───────────────────────────────────────────────────────────────────
def cleanup_benchmark_objects(s3_client, bucket: str, keys: list):
    print(f"\nCleaning up {len(keys)} S3 objects ...")
    for batch_start in range(0, len(keys), 1000):
        batch = keys[batch_start : batch_start + 1000]
        s3_client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": k} for k in batch]},
        )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="inboXray benchmark")
    parser.add_argument(
        "--count", type=int, default=20, help="Number of emails to inject (default: 20)"
    )
    parser.add_argument(
        "--no-cleanup", action="store_true", help="Skip S3 cleanup after benchmark"
    )
    args = parser.parse_args()

    if args.count < 1 or args.count > 500:
        print("--count must be between 1 and 500")
        sys.exit(1)

    print(f"inboXray benchmark  |  emails={args.count}  |  region={REGION}")
    print()

    config = get_config()
    dlq_url = config["sqs_url"].replace("analysis-queue", "analysis-dlq")
    s3_client = boto3.client("s3", region_name=REGION)
    sqs_client = boto3.client("sqs", region_name=REGION)
    logs_client = boto3.client("logs", region_name=REGION)

    # Record DLQ depth before we start so we can detect new failures only
    dlq_before = int(
        sqs_client.get_queue_attributes(
            QueueUrl=dlq_url,
            AttributeNames=["ApproximateNumberOfMessages"],
        )["Attributes"]["ApproximateNumberOfMessages"]
    )
    if dlq_before > 0:
        print(
            f"Note: DLQ already has {dlq_before} stale message(s) from previous runs (will be ignored)\n"
        )

    keys, start_ts = upload_and_enqueue(
        s3_client, sqs_client, config["s3_bucket"], config["sqs_url"], args.count
    )

    end_ts = wait_for_drain(
        sqs_client, config["sqs_url"], dlq_url, dlq_baseline=dlq_before
    )
    total_wall_ms = (end_ts - start_ts) * 1000

    results = query_metrics(logs_client, start_ts)
    print_results(results, total_wall_ms, args.count)

    if not args.no_cleanup:
        cleanup_benchmark_objects(s3_client, config["s3_bucket"], keys)


if __name__ == "__main__":
    main()

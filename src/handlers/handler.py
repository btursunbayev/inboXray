"""
Lambda function handler for processing incoming emails from S3, sanitizing, and forwarding
"""

import json
import os

from src.adapters.aws_adapter import AWSAdapter
from src.core.sanitizer import EmailSanitizer


def handler(event, context):
    """Lambda handler"""
    sanitizer = EmailSanitizer()
    aws = AWSAdapter()

    forward_to = os.environ.get("FORWARD_TO_EMAIL")
    sender_email = os.environ.get("SENDER_EMAIL")

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

            aws.send_email(
                to_address=forward_to,
                subject=f"[Sanitized] {email_data['subject']}",
                body_html=email_data["body_html"],
                body_text=email_data["body_text"],
                from_address=sender_email,
            )

            print(f"Forwarded email to {forward_to}")

            aws.delete_email_from_s3(bucket, key)

        return {"statusCode": 200, "body": json.dumps("Email processed successfully")}

    except Exception as e:
        print(f"Error processing email: {str(e)}")
        return {"statusCode": 500, "body": json.dumps(f"Error: {str(e)}")}

"""
AWS service adapters for S3, DynamoDB, and SES
"""

import os
from typing import Dict, Optional

import boto3


class AWSAdapter:
    """AWS adapter"""

    def __init__(self):
        """Initialize AWS clients"""
        self.s3 = boto3.client("s3")
        self.dynamodb = boto3.resource("dynamodb")
        self.ses = boto3.client("ses")

        self.aliases_table = self.dynamodb.Table(
            os.environ.get("ALIASES_TABLE", "inboxray-aliases")
        )
        self.blocklist_table = self.dynamodb.Table(
            os.environ.get("BLOCKLIST_TABLE", "inboxray-blocklist")
        )

    def get_email_from_s3(self, bucket: str, key: str) -> str:
        """Get email content from S3"""
        response = self.s3.get_object(Bucket=bucket, Key=key)
        return response["Body"].read().decode("utf-8")

    def delete_email_from_s3(self, bucket: str, key: str) -> None:
        """Delete processed email from S3"""
        self.s3.delete_object(Bucket=bucket, Key=key)

    def check_alias_active(self, alias: str) -> bool:
        """Check if email alias is active"""
        try:
            response = self.aliases_table.get_item(Key={"alias": alias})
            item = response.get("Item", {})
            return item.get("status") == "active"
        except Exception as e:
            print(f"Error checking alias: {e}")
            return True  # Allow by default if check fails

    def is_sender_blocked(self, sender: str) -> bool:
        """Check if sender is blocked"""
        try:
            response = self.blocklist_table.get_item(Key={"sender": sender})
            return "Item" in response
        except Exception as e:
            print(f"Error checking blocklist: {e}")
            return False  # Allow by default if check fails

    def send_email(
        self,
        to_address: str,
        subject: str,
        body_html: Optional[str],
        body_text: Optional[str],
        from_address: str,
    ) -> Dict:
        """Send email via SES"""
        message = {"Subject": {"Data": subject}, "Body": {}}

        if body_html:
            message["Body"]["Html"] = {"Data": body_html}

        if body_text:
            message["Body"]["Text"] = {"Data": body_text}

        response = self.ses.send_email(
            Source=from_address,
            Destination={"ToAddresses": [to_address]},
            Message=message,
        )

        return response

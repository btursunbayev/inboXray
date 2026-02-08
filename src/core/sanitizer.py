"""
Email parsing and sanitization
"""

import re
from email import message_from_string
from email.message import Message
from typing import Dict, Optional


class EmailSanitizer:
    """Email parsing and sanitization"""

    def __init__(self):
        """Tracking patterns"""
        self.tracking_patterns = [
            r'<img[^>]*src=["\']https?://[^"\']*track[^"\']*["\'][^>]*>',
            r'<img[^>]*width=["\']1["\'][^>]*height=["\']1["\'][^>]*>',
            r'<img[^>]*height=["\']1["\'][^>]*width=["\']1["\'][^>]*>',
        ]

    def parse_email(self, raw_content: str) -> Dict:
        """Structured format parsing for raw email"""
        msg = message_from_string(raw_content)

        return {
            "from": msg.get("From", ""),
            "to": msg.get("To", ""),
            "subject": msg.get("Subject", ""),
            "date": msg.get("Date", ""),
            "message_id": msg.get("Message-ID", ""),
            "body_html": self._extract_html(msg),
            "body_text": self._extract_text(msg),
        }

    def _extract_html(self, msg: Message) -> Optional[str]:
        """Extract HTML from email"""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    return part.get_payload(decode=True).decode(
                        "utf-8", errors="ignore"
                    )
        elif msg.get_content_type() == "text/html":
            return msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        return None

    def _extract_text(self, msg: Message) -> Optional[str]:
        """Extract plain text from email"""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    return part.get_payload(decode=True).decode(
                        "utf-8", errors="ignore"
                    )
        elif msg.get_content_type() == "text/plain":
            return msg.get_payload(decode=True).decode("utf-8", errors="ignore")
        return None

    def remove_tracking_pixels(self, html_content: str) -> str:
        """Remove tracking pixels from HTML"""
        if not html_content:
            return html_content

        sanitized = html_content

        for pattern in self.tracking_patterns:
            sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)

        return sanitized

    def sanitize(self, raw_email: str) -> Dict:
        """Sanitize email"""
        parsed = self.parse_email(raw_email)

        if parsed["body_html"]:
            parsed["body_html"] = self.remove_tracking_pixels(parsed["body_html"])

        return parsed

"""
Unit tests for email sanitizer
"""

import os
import unittest

from src.core.sanitizer import EmailSanitizer


class TestEmailSanitizer(unittest.TestCase):
    """Test cases for EmailSanitizer class"""

    def setUp(self):
        """Set up test data"""
        self.sanitizer = EmailSanitizer()
        self.test_data_dir = os.path.join(os.path.dirname(__file__), "..", "test_data")

    def test_remove_tracking_pixel_basic(self):
        """Test removal of 1x1 tracking pixel"""
        html = """
        <html>
            <body>
                <p>Hello World</p>
                <img src="http://tracker.com/pixel.gif" width="1" height="1">
            </body>
        </html>
        """
        result = self.sanitizer.remove_tracking_pixels(html)
        self.assertNotIn("tracker.com", result)
        self.assertIn("Hello World", result)

    def test_remove_tracking_pixel_with_track_keyword(self):
        """Test removal of pixels with 'track' in URL"""
        html = '<img src="https://example.com/track/open.gif" />'
        result = self.sanitizer.remove_tracking_pixels(html)
        self.assertNotIn("track/open.gif", result)

    def test_preserve_normal_images(self):
        """Test that normal images are preserved"""
        html = '<img src="https://example.com/photo.jpg" width="800" height="600">'
        result = self.sanitizer.remove_tracking_pixels(html)
        self.assertIn("photo.jpg", result)

    def test_parse_simple_email(self):
        """Test parsing of simple email"""
        raw_email = """From: sender@example.com
To: recipient@example.com
Subject: Test Email
Date: Thu, 07 Feb 2026 10:00:00 +0000

This is a test email body.
"""
        result = self.sanitizer.parse_email(raw_email)
        self.assertEqual(result["from"], "sender@example.com")
        self.assertEqual(result["to"], "recipient@example.com")
        self.assertEqual(result["subject"], "Test Email")
        self.assertIn("test email body", result["body_text"].lower())

    def test_parse_html_email(self):
        """Test parsing of HTML email"""
        raw_email = """From: sender@example.com
To: recipient@example.com
Subject: HTML Test
Content-Type: text/html; charset="utf-8"

<html><body><p>HTML content</p></body></html>
"""
        result = self.sanitizer.parse_email(raw_email)
        self.assertIsNotNone(result["body_html"])
        self.assertIn("HTML content", result["body_html"])

    def test_sanitize_end_to_end(self):
        """Test full sanitization pipeline"""
        raw_email = """From: sender@example.com
To: recipient@example.com
Subject: Newsletter
Content-Type: text/html; charset="utf-8"

<html>
<body>
    <h1>Newsletter</h1>
    <img src="http://tracker.com/pixel.gif" width="1" height="1">
</body>
</html>
"""
        result = self.sanitizer.sanitize(raw_email)
        self.assertEqual(result["subject"], "Newsletter")
        self.assertNotIn("tracker.com", result["body_html"])
        self.assertIn("Newsletter", result["body_html"])


if __name__ == "__main__":
    unittest.main()

"""
Unit tests for handler.py
"""

from src.handlers.handler import extract_urls


class TestExtractUrls:
    def test_finds_http_url(self):
        urls = extract_urls("Visit http://example.com for details")
        assert "http://example.com" in urls

    def test_finds_https_url(self):
        urls = extract_urls("Go to https://secure.example.com/path")
        assert "https://secure.example.com/path" in urls

    def test_finds_www_url(self):
        urls = extract_urls("Check www.example.com today")
        assert "www.example.com" in urls

    def test_finds_multiple_urls(self):
        text = "See https://a.com and https://b.com for info"
        urls = extract_urls(text)
        assert len(urls) == 2

    def test_deduplicates_repeated_url(self):
        text = "https://phish.com click https://phish.com now"
        urls = extract_urls(text)
        assert urls.count("https://phish.com") == 1

    def test_empty_string_returns_empty(self):
        assert extract_urls("") == []

    def test_no_urls_returns_empty(self):
        assert extract_urls("This email has no links at all.") == []

    def test_url_with_query_params(self):
        url = "https://evil.com/track?id=123&ref=abc"
        urls = extract_urls(f"Click here: {url}")
        assert url in urls

    def test_ignores_email_addresses(self):
        # email addresses should not be matched as URLs
        urls = extract_urls("Contact us at support@example.com")
        assert all("@" not in u for u in urls)

    def test_phishing_style_url(self):
        url = "http://paypal-secure.evil.com/login"
        urls = extract_urls(f"Verify your account: {url}")
        assert url in urls

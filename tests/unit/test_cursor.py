"""
Unit tests for app.py
"""

from decimal import Decimal

from src.api.app import _decode_cursor, _encode_cursor, _from_json, _to_json

# ---------------------------------------------------------------------------
# _to_json: Decimal → float (for JSON serialization)
# ---------------------------------------------------------------------------


class TestToJson:
    def test_decimal_becomes_float(self):
        assert _to_json(Decimal("1.5")) == 1.5

    def test_decimal_in_dict(self):
        result = _to_json({"score": Decimal("0.99"), "name": "test"})
        assert result == {"score": 0.99, "name": "test"}

    def test_decimal_in_nested_dict(self):
        result = _to_json({"outer": {"inner": Decimal("42")}})
        assert result["outer"]["inner"] == 42.0

    def test_decimal_in_list(self):
        result = _to_json([Decimal("1"), Decimal("2")])
        assert result == [1.0, 2.0]

    def test_plain_string_unchanged(self):
        assert _to_json("hello") == "hello"

    def test_none_unchanged(self):
        assert _to_json(None) is None


# ---------------------------------------------------------------------------
# _from_json: float → Decimal (for DynamoDB writes after JSON decode)
# ---------------------------------------------------------------------------


class TestFromJson:
    def test_float_becomes_decimal(self):
        assert _from_json(1.5) == Decimal("1.5")

    def test_float_in_dict(self):
        result = _from_json({"score": 0.99, "name": "test"})
        assert result["score"] == Decimal("0.99")
        assert result["name"] == "test"

    def test_nested_float(self):
        result = _from_json({"outer": {"val": 3.14}})
        assert result["outer"]["val"] == Decimal("3.14")

    def test_float_in_list(self):
        result = _from_json([1.0, 2.0])
        assert result == [Decimal("1.0"), Decimal("2.0")]

    def test_int_unchanged(self):
        # integers are not floats — DynamoDB accepts Python int directly
        assert _from_json(5) == 5

    def test_string_unchanged(self):
        assert _from_json("abc") == "abc"


# ---------------------------------------------------------------------------
# _encode_cursor / _decode_cursor: round-trip pagination cursor
# ---------------------------------------------------------------------------


class TestCursorRoundTrip:
    def test_string_key_round_trips(self):
        key = {"messageId": "abc-123", "sk": "2024-01-01"}
        assert _decode_cursor(_encode_cursor(key)) == key

    def test_decimal_key_survives_round_trip(self):
        # DynamoDB LastEvaluatedKey can contain Decimal numeric types
        # After encode (Decimal→float) and decode (float→Decimal) the value
        # must come back as Decimal so boto3 accepts it
        key = {"messageId": "abc", "score": Decimal("1234567890")}
        result = _decode_cursor(_encode_cursor(key))
        assert result["messageId"] == "abc"
        assert isinstance(result["score"], Decimal)
        assert result["score"] == Decimal("1234567890")

    def test_cursor_has_no_padding(self):
        # Cursors are passed in query strings — trailing = breaks URL parsing
        key = {"messageId": "x"}
        encoded = _encode_cursor(key)
        assert "=" not in encoded

    def test_various_key_lengths_decode_correctly(self):
        # base64 padding is tricky: test three lengths to cover all mod-4 cases
        for suffix in ["a", "ab", "abc"]:
            key = {"messageId": suffix}
            assert _decode_cursor(_encode_cursor(key)) == key

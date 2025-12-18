import logging
import json

import pytest

from app.config import _parse_admin_ids, _parse_json


def test_parse_admin_ids_skips_invalid(caplog):
    with caplog.at_level(logging.WARNING):
        result = _parse_admin_ids("123, abc, 456 ")

    assert result == {123, 456}
    assert "Invalid admin id" in caplog.text


def test_parse_json_invalid_returns_default(caplog):
    default = [{"key": "value"}]

    with caplog.at_level(logging.WARNING):
        result = _parse_json("{not json}", default)

    assert result == default
    assert "Failed to parse JSON" in caplog.text


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", []),
        (None, []),
        (json.dumps([{"doc_id": "1"}] ), [{"doc_id": "1"}]),
    ],
)
def test_parse_json_variants(raw, expected):
    assert _parse_json(raw, []) == expected

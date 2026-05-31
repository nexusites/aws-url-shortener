import json
import pytest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("TABLE_NAME", "url-shortener-table")
os.environ.setdefault("BASE_URL", "https://example.execute-api.eu-west-1.amazonaws.com/prod")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")

# Patch boto3 before handler is imported so the module-level resource() call is mocked
_dynamo_patch = patch("boto3.resource")
_mock_dynamo = _dynamo_patch.start()
_mock_dynamo_table = MagicMock()
_mock_dynamo.return_value.Table.return_value = _mock_dynamo_table

import handler  # noqa: E402 — must import after patching

_dynamo_patch.stop()


# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "url-shortener-table")
    monkeypatch.setenv("BASE_URL", "https://example.execute-api.eu-west-1.amazonaws.com/prod")


@pytest.fixture
def mock_table():
    """Replace handler.table with a fresh MagicMock for each test."""
    tbl = MagicMock()
    with patch.object(handler, "table", tbl):
        yield tbl


# ── create_short_url ──────────────────────────────────────────────────────────
class TestCreateShortUrl:
    def test_valid_url_returns_201(self, mock_table):
        from handler import create_short_url
        event = {"body": json.dumps({"url": "https://example.com"})}
        resp = create_short_url(event, None)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert "short_url" in body
        assert "short_code" in body
        mock_table.put_item.assert_called_once()

    def test_missing_url_returns_400(self, mock_table):
        from handler import create_short_url
        event = {"body": json.dumps({})}
        resp = create_short_url(event, None)
        assert resp["statusCode"] == 400

    def test_non_http_url_returns_400(self, mock_table):
        from handler import create_short_url
        event = {"body": json.dumps({"url": "ftp://bad.com"})}
        resp = create_short_url(event, None)
        assert resp["statusCode"] == 400

    def test_invalid_json_returns_400(self, mock_table):
        from handler import create_short_url
        event = {"body": "not json"}
        resp = create_short_url(event, None)
        assert resp["statusCode"] == 400

    def test_custom_ttl_stored(self, mock_table):
        from handler import create_short_url
        event = {"body": json.dumps({"url": "https://example.com", "ttl_days": 7})}
        resp = create_short_url(event, None)
        assert resp["statusCode"] == 201
        body = json.loads(resp["body"])
        assert body["expires_in_days"] == 7


# ── redirect ──────────────────────────────────────────────────────────────────
class TestRedirect:
    def test_valid_code_redirects_301(self, mock_table):
        from handler import redirect
        mock_table.get_item.return_value = {
            "Item": {"short_code": "abc1234", "original_url": "https://example.com", "click_count": 0}
        }
        event = {"pathParameters": {"code": "abc1234"}}
        resp = redirect(event, None)
        assert resp["statusCode"] == 301
        assert resp["headers"]["Location"] == "https://example.com"
        mock_table.update_item.assert_called_once()

    def test_unknown_code_returns_404(self, mock_table):
        from handler import redirect
        mock_table.get_item.return_value = {}
        event = {"pathParameters": {"code": "zzzzzzz"}}
        resp = redirect(event, None)
        assert resp["statusCode"] == 404

    def test_missing_code_returns_400(self, mock_table):
        from handler import redirect
        event = {"pathParameters": {}}
        resp = redirect(event, None)
        assert resp["statusCode"] == 400


# ── get_stats ─────────────────────────────────────────────────────────────────
class TestGetStats:
    def test_returns_stats(self, mock_table):
        from handler import get_stats
        mock_table.get_item.return_value = {
            "Item": {
                "short_code": "abc1234",
                "original_url": "https://example.com",
                "click_count": 42,
                "created_at": "2024-01-01T00:00:00+00:00",
            }
        }
        event = {"pathParameters": {"code": "abc1234"}}
        resp = get_stats(event, None)
        assert resp["statusCode"] == 200
        body = json.loads(resp["body"])
        assert body["click_count"] == 42

    def test_unknown_code_returns_404(self, mock_table):
        from handler import get_stats
        mock_table.get_item.return_value = {}
        event = {"pathParameters": {"code": "zzzzzzz"}}
        resp = get_stats(event, None)
        assert resp["statusCode"] == 404

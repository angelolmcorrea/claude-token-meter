import json
import urllib.error
from datetime import datetime, timezone

import pytest

from claude_token_meter import usage_client as uc

# Trimmed real response from GET /api/oauth/usage
REAL = {
    "five_hour": {"utilization": 32.0, "resets_at": "2026-06-27T19:19:59.403995+00:00"},
    "seven_day": {"utilization": 45.0, "resets_at": "2026-07-01T06:59:59.404023+00:00"},
    "limits": [
        {"kind": "session", "percent": 32, "resets_at": "2026-06-27T19:19:59.403995+00:00"},
        {"kind": "weekly_all", "percent": 45, "resets_at": "2026-07-01T06:59:59.404023+00:00"},
    ],
}


def test_parse_usage_session_and_weekly():
    snap = uc.parse_usage(REAL)
    assert snap.status == "ok"
    assert snap.pct == 0.32
    assert snap.reset_at == datetime(2026, 6, 27, 19, 19, 59, 403995, tzinfo=timezone.utc)
    assert snap.weekly_pct == 0.45
    assert snap.weekly_reset_at == datetime(2026, 7, 1, 6, 59, 59, 404023, tzinfo=timezone.utc)


def test_parse_usage_missing_fields():
    snap = uc.parse_usage({})
    assert snap.pct == 0.0
    assert snap.reset_at is None
    assert snap.weekly_pct is None
    assert snap.status == "ok"


def test_parse_usage_clamps():
    snap = uc.parse_usage({"five_hour": {"utilization": 150.0}})
    assert snap.pct == 1.0


def test_read_token(tmp_path):
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-oat-abc"}}),
                     encoding="utf-8")
    assert uc.read_token(creds) == "sk-ant-oat-abc"


def test_read_token_missing_file(tmp_path):
    assert uc.read_token(tmp_path / "nope.json") is None


def test_read_token_no_oauth(tmp_path):
    creds = tmp_path / ".credentials.json"
    creds.write_text(json.dumps({"mcpOAuth": {}}), encoding="utf-8")
    assert uc.read_token(creds) is None


def test_get_snapshot_no_token(tmp_path, monkeypatch):
    monkeypatch.setattr(uc, "read_token", lambda p=None: None)
    snap = uc.get_snapshot()
    assert snap.status == "auth"
    assert snap.pct == 0.0


def test_get_snapshot_401_is_auth(monkeypatch):
    monkeypatch.setattr(uc, "read_token", lambda p=None: "tok")

    def boom(token, timeout=15.0):
        raise urllib.error.HTTPError(uc.ENDPOINT, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(uc, "fetch_usage", boom)
    assert uc.get_snapshot().status == "auth"


def test_get_snapshot_offline(monkeypatch):
    monkeypatch.setattr(uc, "read_token", lambda p=None: "tok")

    def boom(token, timeout=15.0):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(uc, "fetch_usage", boom)
    assert uc.get_snapshot().status == "offline"


def test_get_snapshot_ok(monkeypatch):
    monkeypatch.setattr(uc, "read_token", lambda p=None: "tok")
    monkeypatch.setattr(uc, "fetch_usage", lambda token, timeout=15.0: REAL)
    snap = uc.get_snapshot()
    assert snap.status == "ok"
    assert snap.pct == 0.32

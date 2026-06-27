"""Reads the REAL Claude usage from the same endpoint the CLI's /usage uses.

Zero token cost: this is a usage query, not a model call. It reads the
account's OAuth access token from ~/.claude/.credentials.json and GETs
https://api.anthropic.com/api/oauth/usage. We never refresh the token
ourselves — the Claude Code CLI keeps it fresh in that file; if it has
expired we just report an 'auth' status until the CLI runs again.
"""
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
HEADERS = {
    "anthropic-beta": "oauth-2025-04-20",
    "anthropic-version": "2023-06-01",
    "Content-Type": "application/json",
    "User-Agent": "claude-token-meter",
}


@dataclass
class UsageSnapshot:
    pct: float                      # 0..1 session (5h) utilization
    reset_at: datetime | None       # when the 5h window resets (UTC)
    weekly_pct: float | None        # 0..1 seven-day utilization, if present
    weekly_reset_at: datetime | None
    status: str                     # "ok" | "auth" | "offline" | "error"


def default_credentials_path() -> Path:
    return Path.home() / ".claude" / ".credentials.json"


def read_token(path: Path | None = None) -> str | None:
    path = Path(path) if path else default_credentials_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    oauth = data.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    return token if isinstance(token, str) and token else None


def _parse_iso(s) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_usage(data: dict) -> UsageSnapshot:
    fh = data.get("five_hour") or {}
    sd = data.get("seven_day") or {}
    pct = (fh.get("utilization") or 0) / 100.0
    weekly = sd.get("utilization")
    return UsageSnapshot(
        pct=max(0.0, min(1.0, pct)),
        reset_at=_parse_iso(fh.get("resets_at")),
        weekly_pct=(max(0.0, min(1.0, weekly / 100.0)) if weekly is not None else None),
        weekly_reset_at=_parse_iso(sd.get("resets_at")),
        status="ok",
    )


def fetch_usage(token: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(
        ENDPOINT, headers={**HEADERS, "Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _empty(status: str) -> UsageSnapshot:
    return UsageSnapshot(0.0, None, None, None, status)


def get_snapshot(credentials_path: Path | None = None, timeout: float = 15.0) -> UsageSnapshot:
    token = read_token(credentials_path)
    if not token:
        return _empty("auth")
    try:
        data = fetch_usage(token, timeout)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return _empty("auth")
        if e.code == 429:
            return _empty("ratelimited")
        return _empty("error")
    except (urllib.error.URLError, TimeoutError, OSError):
        return _empty("offline")
    except (json.JSONDecodeError, ValueError):
        return _empty("error")
    return parse_usage(data)

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import time


@dataclass
class TurnEvent:
    ts: datetime
    weighted: float


@dataclass
class ResetEvent:
    ts: datetime
    reset_at: datetime | None


@dataclass
class UsageSnapshot:
    window_start: datetime | None
    reset_at: datetime | None
    tokens_used: float
    cap: float
    pct: float
    is_estimate: bool
    reset_source: str
    newly_observed_cap: float | None


def weighted_tokens(usage: dict, weights: dict) -> float:
    return (
        usage.get("input_tokens", 0) * weights["input"]
        + usage.get("output_tokens", 0) * weights["output"]
        + usage.get("cache_creation_input_tokens", 0) * weights["cache_creation"]
        + usage.get("cache_read_input_tokens", 0) * weights["cache_read"]
    )


def parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _content_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, list):
        return " ".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    if isinstance(content, str):
        return content
    return ""


def iter_events(lines, weights, tz_name, now):
    """Parse JSONL lines into (turns, resets). Skips malformed lines."""
    turns, resets = [], []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = parse_ts(obj.get("timestamp", ""))
        if ts is None:
            continue
        if obj.get("error") == "rate_limit" or obj.get("apiErrorStatus") == 429:
            text = _content_text(obj.get("message", {}) or {})
            resets.append(ResetEvent(ts, parse_reset_text(text, tz_name, now)))
            continue
        message = obj.get("message")
        if isinstance(message, dict) and isinstance(message.get("usage"), dict):
            turns.append(TurnEvent(ts, weighted_tokens(message["usage"], weights)))
    return turns, resets


_RESET_RE = re.compile(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.IGNORECASE)

_ONE_DAY = timedelta(days=1)


def parse_reset_text(text: str, tz_name: str, now: datetime) -> datetime | None:
    m = _RESET_RE.search(text or "")
    if not m:
        return None
    hour = int(m.group(1)) % 12
    minute = int(m.group(2) or 0)
    if m.group(3).lower() == "pm":
        hour += 12
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now_local = now.astimezone(tz)
    candidate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now_local:
        candidate = candidate.replace(day=now_local.day) + _ONE_DAY
    return candidate.astimezone(timezone.utc)


def find_active_block(turns, window, now):
    """Return the start ts of the active 5h block, or None if idle/empty."""
    if not turns:
        return None
    ordered = sorted(turns, key=lambda t: t.ts)
    block_start = ordered[0].ts
    for t in ordered:
        if t.ts > block_start + window:
            block_start = t.ts
    if now > block_start + window:
        return None
    return block_start

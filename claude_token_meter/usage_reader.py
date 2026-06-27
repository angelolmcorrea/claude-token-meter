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


def parse_reset_text(text, tz_name, now):  # replaced in Task 4
    return None


_ONE_DAY = timedelta(days=1)

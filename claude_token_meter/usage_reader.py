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


def iter_events(lines, weights, tz_name):
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
            # anchor the reset to the EVENT's own time, not the current clock:
            # a reset announced earlier resolves relative to when it fired, so a
            # stale window's reset lands in the past and gets dropped downstream.
            resets.append(ResetEvent(ts, parse_reset_text(text, tz_name, ts)))
            continue
        message = obj.get("message")
        if isinstance(message, dict) and isinstance(message.get("usage"), dict):
            turns.append(TurnEvent(ts, weighted_tokens(message["usage"], weights)))
    return turns, resets


_RESET_RE = re.compile(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.IGNORECASE)


def parse_reset_text(text: str, tz_name: str, anchor: datetime) -> datetime | None:
    """Resolve "resets Xam/pm" to the first such local time at or after `anchor`."""
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
    anchor_local = anchor.astimezone(tz)
    candidate = anchor_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= anchor_local:
        next_date = anchor_local.date() + timedelta(days=1)
        candidate = anchor_local.replace(
            year=next_date.year, month=next_date.month, day=next_date.day,
            hour=hour, minute=minute, second=0, microsecond=0,
        )
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


def _block_start_for(ordered_turns, until_ts, window):
    bs = None
    for t in ordered_turns:
        if t.ts > until_ts:
            break
        if bs is None or t.ts > bs + window:
            bs = t.ts
    return bs


def calibrate_cap(turns, resets, window):
    """Most-recent observed cap: weighted sum of the block up to each 429."""
    if not resets:
        return None
    ordered = sorted(turns, key=lambda t: t.ts)
    best = None  # (reset_ts, cap)
    for r in sorted(resets, key=lambda x: x.ts):
        bs = _block_start_for(ordered, r.ts, window)
        if bs is None:
            continue
        cap = sum(t.weighted for t in ordered if bs <= t.ts <= r.ts)
        if cap > 0 and (best is None or r.ts > best[0]):
            best = (r.ts, cap)
    return best[1] if best else None


def resolve_reset(block_start, resets, window, now):
    future = [r.reset_at for r in resets if r.reset_at and r.reset_at > now]
    if future:
        # earliest future reset wins: that's when the current limit lifts
        return min(future), "logged"
    if block_start is not None:
        return block_start + window, "computed"
    return None, "idle"


def _recent_jsonl_files(claude_dir, lookback):
    root = Path(claude_dir) / "projects"
    if not root.exists():
        return []
    cutoff = time.time() - lookback.total_seconds()
    files = []
    for f in root.rglob("*.jsonl"):
        try:
            if f.stat().st_mtime >= cutoff:
                files.append(f)
        except OSError:
            continue
    return files


def _read_lines(files):
    for f in files:
        try:
            with f.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    yield line
        except OSError:
            continue


def read_snapshot(claude_dir, config, now) -> UsageSnapshot:
    window = timedelta(hours=config["window_hours"])
    lookback = timedelta(hours=config["lookback_hours"])
    weights = config["weights"]
    tz_name = config.get("timezone", "UTC")

    files = _recent_jsonl_files(claude_dir, lookback)
    turns, resets = iter_events(_read_lines(files), weights, tz_name)

    block_start = find_active_block(turns, window, now)
    reset_at, source = resolve_reset(block_start, resets, window, now)

    observed = calibrate_cap(turns, resets, window)
    persisted = config.get("calibrated_cap")
    if persisted is not None:
        cap = persisted
    elif observed is not None:
        cap = observed
    else:
        cap = config["default_cap_estimate"]
    is_estimate = persisted is None and observed is None

    if block_start is not None:
        window_start = block_start
    elif source == "logged" and reset_at is not None:
        window_start = reset_at - window
    else:
        window_start = None

    if window_start is None:
        return UsageSnapshot(None, reset_at if source == "logged" else None,
                             0.0, cap, 0.0, is_estimate,
                             "idle" if source != "logged" else source, observed)

    tokens_used = sum(t.weighted for t in turns if window_start <= t.ts <= now)
    pct = max(0.0, min(1.0, tokens_used / cap)) if cap > 0 else 0.0
    return UsageSnapshot(window_start, reset_at, tokens_used, cap, pct,
                         is_estimate, source, observed)

# claude-token-meter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a small always-on-top Windows widget that shows a one-line bar with the current Claude Code session-window token usage (% and time-to-reset), reading only local transcript files — zero token cost.

**Architecture:** Pure-logic core (`usage_reader.py`, no Qt) scans `~/.claude/projects/**/*.jsonl`, detects the active 5h session block, sums weighted tokens, auto-calibrates the 100% cap from logged `429` events, and resolves the reset time from the logged text (or `block_start + 5h`). A thin PySide6 widget (`widget.py`) only paints a `UsageSnapshot`. `main.py` wires them with a `QTimer`. Config (weights, cap, thresholds, position) lives in `%APPDATA%\claude-token-meter\config.json`.

**Tech Stack:** Python 3.11+ (stdlib `json`, `pathlib`, `datetime`, `zoneinfo`, `dataclasses`), PySide6, pytest. `tzdata` for IANA timezones on Windows.

**Layout note:** the spec wrote `src/claude_token_meter/`; this plan uses a **flat top-level package** `claude_token_meter/` so the tool runs with `pythonw -m claude_token_meter.main` from the repo root with no install step. This is an intentional simplification.

**Shared types (defined in Task 3, reused everywhere):**

```python
@dataclass
class TurnEvent:
    ts: datetime          # tz-aware UTC
    weighted: float

@dataclass
class ResetEvent:
    ts: datetime          # tz-aware UTC, when the 429 fired
    reset_at: datetime | None   # tz-aware, parsed from "resets 2:20am", else None

@dataclass
class UsageSnapshot:
    window_start: datetime | None
    reset_at: datetime | None
    tokens_used: float
    cap: float
    pct: float                  # 0.0..1.0 (clamped)
    is_estimate: bool           # True when cap fell back to default_cap_estimate
    reset_source: str           # "logged" | "computed" | "idle"
    newly_observed_cap: float | None  # cap detected from a 429 this scan, for main to persist
```

---

## Task 1: Project scaffolding

**Files:**
- Create: `claude_token_meter/__init__.py`
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `conftest.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create the package and test dirs with placeholder files**

`claude_token_meter/__init__.py`:
```python
"""claude-token-meter: passive local Claude Code session usage meter."""

__version__ = "0.1.0"
```

`tests/__init__.py`: (empty file)

`conftest.py`: (empty file — ensures repo root is on sys.path so `import claude_token_meter` works)

- [ ] **Step 2: Create `requirements.txt`**

```
PySide6>=6.6
tzdata>=2024.1
pytest>=8.0
```

- [ ] **Step 3: Create `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
config.local.json
```

- [ ] **Step 4: Create the venv and install deps**

Run:
```bash
cd /c/Cerberus/repos/claude-token-meter
py -3 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```
Expected: pip installs PySide6, tzdata, pytest without error.

- [ ] **Step 5: Verify pytest runs (no tests yet)**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `no tests ran` (exit code 5) — that is fine at this stage.

- [ ] **Step 6: Commit**

```bash
git add claude_token_meter/__init__.py tests/__init__.py conftest.py requirements.txt .gitignore
git commit -m "chore: scaffold claude_token_meter package and deps"
```

---

## Task 2: Config module

**Files:**
- Create: `claude_token_meter/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:
```python
import json
from pathlib import Path
from claude_token_meter import config as cfg


def test_load_creates_defaults(tmp_path):
    path = tmp_path / "config.json"
    c = cfg.load(path)
    assert c["refresh_seconds"] == 10
    assert c["window_hours"] == 5
    assert c["weights"]["cache_read"] == 0.1
    assert c["calibrated_cap"] is None
    assert c["autostart"] is True
    assert path.exists()  # written on first load


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    c = cfg.load(path)
    c["calibrated_cap"] = 12345.0
    cfg.save(c, path)
    again = cfg.load(path)
    assert again["calibrated_cap"] == 12345.0


def test_load_fills_missing_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"refresh_seconds": 3}), encoding="utf-8")
    c = cfg.load(path)
    assert c["refresh_seconds"] == 3          # user value kept
    assert c["window_hours"] == 5             # missing key backfilled
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: FAIL (module `config` has no attribute `load`).

- [ ] **Step 3: Write minimal implementation**

`claude_token_meter/config.py`:
```python
import json
import os
from copy import deepcopy
from pathlib import Path

DEFAULTS = {
    "weights": {"input": 1.0, "output": 1.0, "cache_creation": 1.0, "cache_read": 0.1},
    "calibrated_cap": None,
    "default_cap_estimate": 500000,
    "window_hours": 5,
    "lookback_hours": 6,
    "refresh_seconds": 10,
    "thresholds": {"amber": 0.60, "red": 0.85},
    "timezone": "America/Sao_Paulo",
    "window": {"x": None, "y": None, "opacity": 0.92},
    "autostart": True,
}


def default_config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "claude-token-meter" / "config.json"


def _merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: Path | None = None) -> dict:
    path = Path(path) if path else default_config_path()
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            user = {}
    else:
        user = {}
    merged = _merge(DEFAULTS, user)
    save(merged, path)
    return merged


def save(config: dict, path: Path | None = None) -> None:
    path = Path(path) if path else default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_token_meter/config.py tests/test_config.py
git commit -m "feat: config load/save with defaults and backfill"
```

---

## Task 3: Token weighting + JSONL line parsing

**Files:**
- Create: `claude_token_meter/usage_reader.py`
- Test: `tests/test_usage_reader.py`

- [ ] **Step 1: Write the failing test**

`tests/test_usage_reader.py`:
```python
from datetime import datetime, timezone
from claude_token_meter import usage_reader as ur

WEIGHTS = {"input": 1.0, "output": 1.0, "cache_creation": 1.0, "cache_read": 0.1}


def test_weighted_tokens():
    usage = {"input_tokens": 2, "cache_creation_input_tokens": 90,
             "cache_read_input_tokens": 100, "output_tokens": 8}
    # 2 + 8 + 90 + 100*0.1 = 110
    assert ur.weighted_tokens(usage, WEIGHTS) == 110.0


def test_weighted_tokens_missing_keys():
    assert ur.weighted_tokens({"output_tokens": 5}, WEIGHTS) == 5.0


def test_parse_ts_handles_z():
    ts = ur.parse_ts("2026-06-21T03:42:07.811Z")
    assert ts == datetime(2026, 6, 21, 3, 42, 7, 811000, tzinfo=timezone.utc)


def test_iter_events_splits_turns_and_resets():
    lines = [
        '{"type":"assistant","timestamp":"2026-06-21T00:00:00Z",'
        '"message":{"usage":{"output_tokens":10}}}',
        '{"timestamp":"2026-06-21T01:00:00Z","error":"rate_limit",'
        '"apiErrorStatus":429,"message":{"content":[{"type":"text",'
        '"text":"You\'ve hit your session limit · resets 3:00am (America/Sao_Paulo)"}]}}',
        'not json at all',
        '{"type":"user","timestamp":"2026-06-21T00:30:00Z"}',
    ]
    turns, resets = ur.iter_events(lines, WEIGHTS, "America/Sao_Paulo",
                                   ur.parse_ts("2026-06-21T02:00:00Z"))
    assert len(turns) == 1
    assert turns[0].weighted == 10.0
    assert len(resets) == 1
    assert resets[0].reset_at is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_usage_reader.py -v`
Expected: FAIL (no attribute `weighted_tokens`).

- [ ] **Step 3: Write minimal implementation**

`claude_token_meter/usage_reader.py`:
```python
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


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
```

Note: `parse_reset_text` is implemented in Task 4. Add a temporary stub at the bottom of the file so the import resolves now:
```python
def parse_reset_text(text, tz_name, now):  # replaced in Task 4
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_usage_reader.py -v`
Expected: 4 passed (the reset_at-is-not-None assertion passes only after Task 4 — for now change that last assertion to `assert resets[0].reset_at is None` to match the stub, then flip it back in Task 4).

- [ ] **Step 5: Commit**

```bash
git add claude_token_meter/usage_reader.py tests/test_usage_reader.py
git commit -m "feat: token weighting and JSONL event parsing"
```

---

## Task 4: Parse the reset text into a datetime

**Files:**
- Modify: `claude_token_meter/usage_reader.py` (replace the `parse_reset_text` stub)
- Test: `tests/test_usage_reader.py` (add cases)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_usage_reader.py`:
```python
def test_parse_reset_text_with_minutes():
    now = ur.parse_ts("2026-06-20T22:00:00-03:00")  # 22:00 local
    got = ur.parse_reset_text("resets 2:20am (America/Sao_Paulo)",
                              "America/Sao_Paulo", now)
    assert got is not None
    local = got.astimezone(ZoneInfoBR())
    assert (local.hour, local.minute) == (2, 20)
    assert got > now  # next future occurrence


def test_parse_reset_text_hour_only_pm():
    now = ur.parse_ts("2026-06-20T22:00:00-03:00")
    got = ur.parse_reset_text("resets 11pm", "America/Sao_Paulo", now)
    local = got.astimezone(ZoneInfoBR())
    assert (local.hour, local.minute) == (23, 0)


def test_parse_reset_text_unparseable():
    now = ur.parse_ts("2026-06-20T22:00:00Z")
    assert ur.parse_reset_text("limit reached, try later", "UTC", now) is None
```

Also add this import helper near the top of the test file:
```python
from zoneinfo import ZoneInfo

def ZoneInfoBR():
    return ZoneInfo("America/Sao_Paulo")
```

And flip the last assertion in `test_iter_events_splits_turns_and_resets` back to:
```python
    assert resets[0].reset_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_usage_reader.py -k reset_text -v`
Expected: FAIL (stub returns None).

- [ ] **Step 3: Replace the stub with the real implementation**

In `claude_token_meter/usage_reader.py`, replace the temporary `parse_reset_text` stub with:
```python
import re

_RESET_RE = re.compile(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.IGNORECASE)


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
```

Add near the imports:
```python
from datetime import timedelta
_ONE_DAY = timedelta(days=1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_usage_reader.py -v`
Expected: all passed (reset-text cases + the flipped iter_events assertion).

- [ ] **Step 5: Commit**

```bash
git add claude_token_meter/usage_reader.py tests/test_usage_reader.py
git commit -m "feat: parse 'resets Xam/pm' reset text to a future datetime"
```

---

## Task 5: Active block detection

**Files:**
- Modify: `claude_token_meter/usage_reader.py`
- Test: `tests/test_usage_reader.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_usage_reader.py`:
```python
from datetime import timedelta

def _turn(iso, w=1.0):
    return ur.TurnEvent(ur.parse_ts(iso), w)


def test_find_active_block_simple():
    turns = [_turn("2026-06-21T00:00:00Z"), _turn("2026-06-21T01:00:00Z")]
    now = ur.parse_ts("2026-06-21T02:00:00Z")
    start = ur.find_active_block(turns, timedelta(hours=5), now)
    assert start == ur.parse_ts("2026-06-21T00:00:00Z")


def test_find_active_block_picks_latest_after_gap():
    turns = [_turn("2026-06-21T00:00:00Z"),   # old block
             _turn("2026-06-21T07:00:00Z")]   # > 5h later -> new block
    now = ur.parse_ts("2026-06-21T08:00:00Z")
    start = ur.find_active_block(turns, timedelta(hours=5), now)
    assert start == ur.parse_ts("2026-06-21T07:00:00Z")


def test_find_active_block_idle_returns_none():
    turns = [_turn("2026-06-21T00:00:00Z")]
    now = ur.parse_ts("2026-06-21T06:00:00Z")  # > 5h after start
    assert ur.find_active_block(turns, timedelta(hours=5), now) is None


def test_find_active_block_empty():
    now = ur.parse_ts("2026-06-21T06:00:00Z")
    assert ur.find_active_block([], timedelta(hours=5), now) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_usage_reader.py -k active_block -v`
Expected: FAIL (no attribute `find_active_block`).

- [ ] **Step 3: Write the implementation**

Append to `claude_token_meter/usage_reader.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_usage_reader.py -k active_block -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_token_meter/usage_reader.py tests/test_usage_reader.py
git commit -m "feat: detect the active 5h session block"
```

---

## Task 6: Cap calibration and reset resolution

**Files:**
- Modify: `claude_token_meter/usage_reader.py`
- Test: `tests/test_usage_reader.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_usage_reader.py`:
```python
def test_calibrate_cap_sums_block_up_to_reset():
    turns = [_turn("2026-06-21T00:00:00Z", 30.0),
             _turn("2026-06-21T00:30:00Z", 70.0),
             _turn("2026-06-21T06:00:00Z", 999.0)]  # next block, ignored
    resets = [ur.ResetEvent(ur.parse_ts("2026-06-21T01:00:00Z"), None)]
    cap = ur.calibrate_cap(turns, resets, timedelta(hours=5))
    assert cap == 100.0


def test_calibrate_cap_none_when_no_resets():
    turns = [_turn("2026-06-21T00:00:00Z", 30.0)]
    assert ur.calibrate_cap(turns, [], timedelta(hours=5)) is None


def test_resolve_reset_prefers_future_logged():
    now = ur.parse_ts("2026-06-21T02:00:00Z")
    block_start = ur.parse_ts("2026-06-21T00:00:00Z")
    logged = ur.parse_ts("2026-06-21T05:30:00Z")
    resets = [ur.ResetEvent(now, logged)]
    reset_at, source = ur.resolve_reset(block_start, resets, timedelta(hours=5), now)
    assert reset_at == logged
    assert source == "logged"


def test_resolve_reset_falls_back_to_computed():
    now = ur.parse_ts("2026-06-21T02:00:00Z")
    block_start = ur.parse_ts("2026-06-21T00:00:00Z")
    reset_at, source = ur.resolve_reset(block_start, [], timedelta(hours=5), now)
    assert reset_at == ur.parse_ts("2026-06-21T05:00:00Z")
    assert source == "computed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_usage_reader.py -k "calibrate or resolve_reset" -v`
Expected: FAIL (no attributes).

- [ ] **Step 3: Write the implementation**

Append to `claude_token_meter/usage_reader.py`:
```python
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
        return min(future), "logged"
    if block_start is not None:
        return block_start + window, "computed"
    return None, "idle"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_usage_reader.py -k "calibrate or resolve_reset" -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add claude_token_meter/usage_reader.py tests/test_usage_reader.py
git commit -m "feat: cap calibration from 429s and reset resolution"
```

---

## Task 7: read_snapshot orchestration (file IO)

**Files:**
- Modify: `claude_token_meter/usage_reader.py`
- Test: `tests/test_usage_reader.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_usage_reader.py`:
```python
import json as _json

def _write_jsonl(path, rows):
    path.write_text("\n".join(_json.dumps(r) for r in rows), encoding="utf-8")


def test_read_snapshot_active_window(tmp_path):
    proj = tmp_path / "projects" / "p1"
    proj.mkdir(parents=True)
    rows = [
        {"type": "assistant", "timestamp": "2026-06-21T00:00:00Z",
         "message": {"usage": {"output_tokens": 40}}},
        {"type": "assistant", "timestamp": "2026-06-21T01:00:00Z",
         "message": {"usage": {"output_tokens": 60}}},
    ]
    _write_jsonl(proj / "s.jsonl", rows)
    config = {
        "weights": WEIGHTS, "calibrated_cap": 200.0, "default_cap_estimate": 500000,
        "window_hours": 5, "lookback_hours": 6, "timezone": "UTC",
    }
    now = ur.parse_ts("2026-06-21T02:00:00Z")
    snap = ur.read_snapshot(tmp_path, config, now)
    assert snap.tokens_used == 100.0
    assert snap.cap == 200.0
    assert snap.pct == 0.5
    assert snap.is_estimate is False
    assert snap.reset_source == "computed"
    assert snap.reset_at == ur.parse_ts("2026-06-21T05:00:00Z")


def test_read_snapshot_idle(tmp_path):
    (tmp_path / "projects").mkdir()
    config = {"weights": WEIGHTS, "calibrated_cap": None, "default_cap_estimate": 500000,
              "window_hours": 5, "lookback_hours": 6, "timezone": "UTC"}
    now = ur.parse_ts("2026-06-21T02:00:00Z")
    snap = ur.read_snapshot(tmp_path, config, now)
    assert snap.reset_source == "idle"
    assert snap.pct == 0.0


def test_read_snapshot_estimate_flag(tmp_path):
    proj = tmp_path / "projects" / "p1"
    proj.mkdir(parents=True)
    _write_jsonl(proj / "s.jsonl", [
        {"type": "assistant", "timestamp": "2026-06-21T01:30:00Z",
         "message": {"usage": {"output_tokens": 50}}}])
    config = {"weights": WEIGHTS, "calibrated_cap": None, "default_cap_estimate": 1000,
              "window_hours": 5, "lookback_hours": 6, "timezone": "UTC"}
    now = ur.parse_ts("2026-06-21T02:00:00Z")
    snap = ur.read_snapshot(tmp_path, config, now)
    assert snap.is_estimate is True
    assert snap.cap == 1000
    assert snap.pct == 0.05
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_usage_reader.py -k read_snapshot -v`
Expected: FAIL (no attribute `read_snapshot`).

- [ ] **Step 3: Write the implementation**

Append to `claude_token_meter/usage_reader.py`:
```python
from pathlib import Path
import time


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
    turns, resets = iter_events(_read_lines(files), weights, tz_name, now)

    block_start = find_active_block(turns, window, now)
    reset_at, source = resolve_reset(block_start, resets, window, now)

    observed = calibrate_cap(turns, resets, window)
    cap = config.get("calibrated_cap") or observed or config["default_cap_estimate"]
    is_estimate = not (config.get("calibrated_cap") or observed)

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_usage_reader.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add claude_token_meter/usage_reader.py tests/test_usage_reader.py
git commit -m "feat: read_snapshot orchestration with mtime-filtered file scan"
```

---

## Task 8: Autostart (Windows Startup shortcut)

**Files:**
- Create: `claude_token_meter/autostart.py`
- Test: `tests/test_autostart.py`

- [ ] **Step 1: Write the failing test**

`tests/test_autostart.py`:
```python
from pathlib import Path
from claude_token_meter import autostart


def test_shortcut_path_in_given_dir(tmp_path):
    p = autostart.shortcut_path(tmp_path)
    assert p == tmp_path / "claude-token-meter.lnk"


def test_is_enabled_reflects_file(tmp_path):
    assert autostart.is_enabled(tmp_path) is False
    (tmp_path / "claude-token-meter.lnk").write_text("x", encoding="utf-8")
    assert autostart.is_enabled(tmp_path) is True


def test_disable_removes_file(tmp_path):
    lnk = tmp_path / "claude-token-meter.lnk"
    lnk.write_text("x", encoding="utf-8")
    autostart.disable(tmp_path)
    assert not lnk.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_autostart.py -v`
Expected: FAIL (no module attribute).

- [ ] **Step 3: Write the implementation**

`claude_token_meter/autostart.py`:
```python
import os
import subprocess
import sys
from pathlib import Path

SHORTCUT_NAME = "claude-token-meter.lnk"


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path(directory: Path | None = None) -> Path:
    return (Path(directory) if directory else startup_dir()) / SHORTCUT_NAME


def is_enabled(directory: Path | None = None) -> bool:
    return shortcut_path(directory).exists()


def disable(directory: Path | None = None) -> None:
    p = shortcut_path(directory)
    if p.exists():
        p.unlink()


def enable(directory: Path | None = None) -> None:
    """Create a .lnk that launches the meter with pythonw (no console flash)."""
    target = str(Path(sys.executable).with_name("pythonw.exe"))
    workdir = str(Path(__file__).resolve().parent.parent)
    args = "-m claude_token_meter.main"
    lnk = str(shortcut_path(directory))
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
        "$s.TargetPath='%s';$s.Arguments='%s';"
        "$s.WorkingDirectory='%s';$s.Save()" % (lnk, target, args, workdir)
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_autostart.py -v`
Expected: 3 passed. (Path/state helpers are tested; the COM `.lnk` creation in `enable()` is verified manually on Windows in Task 11.)

- [ ] **Step 5: Commit**

```bash
git add claude_token_meter/autostart.py tests/test_autostart.py
git commit -m "feat: Windows Startup shortcut enable/disable"
```

---

## Task 9: The PySide6 widget

**Files:**
- Create: `claude_token_meter/widget.py`

No automated test (presentation only); verified manually in Task 11.

- [ ] **Step 1: Write the widget**

`claude_token_meter/widget.py`:
```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from PySide6.QtCore import Qt, QPoint, QRectF
from PySide6.QtGui import QColor, QPainter, QBrush, QFont
from PySide6.QtWidgets import QWidget, QMenu

WIDTH, HEIGHT = 300, 34
GREEN = QColor("#3FB950")
AMBER = QColor("#D29922")
RED = QColor("#F85149")
BG = QColor(20, 22, 26, 235)
TRACK = QColor(255, 255, 255, 28)
TEXT = QColor("#E6EDF3")


class MeterWidget(QWidget):
    def __init__(self, config, on_quit, on_recalibrate, on_toggle_autostart):
        super().__init__()
        self._config = config
        self._on_quit = on_quit
        self._on_recalibrate = on_recalibrate
        self._on_toggle_autostart = on_toggle_autostart
        self._snapshot = None
        self._drag_offset = None

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WIDTH, HEIGHT)
        self.setWindowOpacity(config["window"].get("opacity", 0.92))

        pos = config.get("window", {})
        if pos.get("x") is not None and pos.get("y") is not None:
            self.move(pos["x"], pos["y"])

    def update_snapshot(self, snapshot):
        self._snapshot = snapshot
        self.update()  # trigger repaint

    def _color(self, pct):
        t = self._config["thresholds"]
        if pct >= t["red"]:
            return RED
        if pct >= t["amber"]:
            return AMBER
        return GREEN

    def _reset_label(self, snap, now):
        if snap is None or snap.reset_source == "idle" or snap.reset_at is None:
            return "ocioso"
        delta = snap.reset_at - now
        mins = max(0, int(delta.total_seconds() // 60))
        if mins >= 60:
            return f"reset {mins // 60}h{mins % 60:02d}"
        return f"reset {mins}m"

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, WIDTH, HEIGHT)
        p.setBrush(QBrush(BG))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect, 8, 8)

        snap = self._snapshot
        now = datetime.now(timezone.utc)
        pct = snap.pct if snap else 0.0

        bar = QRectF(8, HEIGHT - 11, WIDTH - 16, 5)
        p.setBrush(QBrush(TRACK))
        p.drawRoundedRect(bar, 2.5, 2.5)
        if pct > 0:
            fill = QRectF(bar.x(), bar.y(), bar.width() * pct, bar.height())
            p.setBrush(QBrush(self._color(pct)))
            p.drawRoundedRect(fill, 2.5, 2.5)

        prefix = "~" if (snap and snap.is_estimate) else ""
        label = f"{prefix}{int(pct * 100)}%   {self._reset_label(snap, now)}"
        p.setPen(TEXT)
        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        p.drawText(QRectF(10, 3, WIDTH - 20, 16), Qt.AlignLeft | Qt.AlignVCenter, label)

    # --- dragging ---
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.RightButton:
            self._menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _e):
        if self._drag_offset is not None:
            self._drag_offset = None
            self._config["window"]["x"] = self.x()
            self._config["window"]["y"] = self.y()

    def _menu(self, global_pos):
        m = QMenu()
        m.addAction("Recalibrar teto", self._on_recalibrate)
        m.addAction("Iniciar com o Windows", self._on_toggle_autostart)
        m.addSeparator()
        m.addAction("Sair", self._on_quit)
        m.exec(global_pos)
```

Note: the widget stashes the new x/y in `config["window"]` on release; `main.py` persists the config to disk each tick (Task 10), so no file write happens inside the widget.

- [ ] **Step 2: Quick import check**

Run: `.venv/Scripts/python.exe -c "import claude_token_meter.widget"`
Expected: no output, exit 0 (PySide6 imports cleanly).

- [ ] **Step 3: Commit**

```bash
git add claude_token_meter/widget.py
git commit -m "feat: one-line always-on-top meter widget"
```

---

## Task 10: main.py wiring

**Files:**
- Create: `claude_token_meter/main.py`

- [ ] **Step 1: Write main**

`claude_token_meter/main.py`:
```python
import sys
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from claude_token_meter import config as cfg
from claude_token_meter import usage_reader as ur
from claude_token_meter import autostart
from claude_token_meter.widget import MeterWidget


def claude_dir() -> Path:
    return Path.home() / ".claude"


def main():
    config = cfg.load()
    app = QApplication(sys.argv)

    def recalibrate():
        config["calibrated_cap"] = None
        cfg.save(config)

    def toggle_autostart():
        if autostart.is_enabled():
            autostart.disable()
            config["autostart"] = False
        else:
            autostart.enable()
            config["autostart"] = True
        cfg.save(config)

    widget = MeterWidget(config, app.quit, recalibrate, toggle_autostart)
    widget.show()

    if config.get("autostart") and not autostart.is_enabled():
        autostart.enable()

    def tick():
        now = datetime.now(timezone.utc)
        snap = ur.read_snapshot(claude_dir(), config, now)
        if snap.newly_observed_cap and snap.newly_observed_cap != config.get("calibrated_cap"):
            config["calibrated_cap"] = snap.newly_observed_cap
            cfg.save(config)
        # persist any drag move
        if (config["window"]["x"], config["window"]["y"]) != (widget.x(), widget.y()):
            config["window"]["x"], config["window"]["y"] = widget.x(), widget.y()
            cfg.save(config)
        widget.update_snapshot(snap)

    tick()
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(config["refresh_seconds"] * 1000)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Import check**

Run: `.venv/Scripts/python.exe -c "import claude_token_meter.main"`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add claude_token_meter/main.py
git commit -m "feat: wire reader + widget with a 10s QTimer"
```

---

## Task 11: Runner, README, and manual smoke test

**Files:**
- Create: `iniciar.bat`
- Create: `README.md`

- [ ] **Step 1: Create `iniciar.bat`**

`iniciar.bat`:
```bat
@echo off
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m claude_token_meter.main
```

- [ ] **Step 2: Create `README.md`**

`README.md`:
```markdown
# claude-token-meter

Janelinha always-on-top (Windows) que mostra, numa barra de uma linha, o
consumo da janela de sessao atual do Claude Code (% + tempo pra resetar).

100% offline e passivo: le apenas os transcripts locais em
`~/.claude/projects/**/*.jsonl`. Nao chama a API nem nenhum modelo — custo
em tokens: zero.

## Rodar

```
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
iniciar.bat
```

Arrasta com o mouse pra reposicionar. Clique-direito: recalibrar teto,
iniciar com o Windows, sair.

## Como a % e calculada

A barra mostra os tokens ponderados usados na janela de 5h sobre um teto.
O teto (100%) **se auto-calibra**: quando o Claude Code loga um limite de
sessao batido (429), o total acumulado naquele instante vira o teto. Antes
da primeira batida, a barra mostra `~NN%` (estimativa). E uma aproximacao
calibrada, nao uma medicao exata — boa pra "estou perto de estourar?".

Config em `%APPDATA%\claude-token-meter\config.json` (pesos, thresholds de
cor, intervalo, timezone, posicao).
```

- [ ] **Step 3: Run the full test suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all tests pass.

- [ ] **Step 4: Manual smoke test**

Run: `iniciar.bat`
Expected: a small bar appears, stays on top, shows a `%` and `reset`/`ocioso`. Drag it; right-click shows the menu. Confirm a `claude-token-meter.lnk` appears in `shell:startup` (Win+R → `shell:startup`).

- [ ] **Step 5: Commit**

```bash
git add iniciar.bat README.md
git commit -m "docs: runner script and README"
```

---

## Self-review notes

- **Spec coverage:** data source (Task 7), weighting (Task 3), 5h block (Task 5), cap auto-calibration (Task 6), reset from logged text (Task 4) + computed fallback (Task 6), config schema (Task 2), widget behavior/colors/drag/menu (Task 9), autostart v1 (Tasks 8 + 10), mtime-filtered performance (Task 7), error tolerance for malformed lines (Task 3/7), timezone display (Task 4/9), tests (Tasks 2-8), runner/README (Task 11). All spec sections map to a task.
- **Estimate flag:** `is_estimate` is True only when both persisted and freshly-observed caps are absent (Task 7), matching spec section 5.
- **Type consistency:** `UsageSnapshot`, `TurnEvent`, `ResetEvent` defined once (Task 3) and reused; `read_snapshot(claude_dir, config, now)`, `find_active_block(turns, window, now)`, `calibrate_cap(turns, resets, window)`, `resolve_reset(block_start, resets, window, now)` signatures are consistent across tasks and the `main.py` caller.

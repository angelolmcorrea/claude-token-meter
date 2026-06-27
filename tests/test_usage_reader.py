from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from claude_token_meter import usage_reader as ur


def ZoneInfoBR():
    return ZoneInfo("America/Sao_Paulo")

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
    turns, resets = ur.iter_events(lines, WEIGHTS, "America/Sao_Paulo")
    assert len(turns) == 1
    assert turns[0].weighted == 10.0
    assert len(resets) == 1
    assert resets[0].reset_at is not None


def test_iter_events_reset_anchors_to_event_ts():
    # 429 fired at 04:00 UTC saying "resets 5am" -> 05:00 the SAME day,
    # not rolled forward relative to a much-later 'now'.
    lines = ['{"timestamp":"2026-06-21T04:00:00Z","error":"rate_limit",'
             '"apiErrorStatus":429,"message":{"content":[{"type":"text",'
             '"text":"resets 5am (UTC)"}]}}']
    turns, resets = ur.iter_events(lines, WEIGHTS, "UTC")
    assert resets[0].reset_at == ur.parse_ts("2026-06-21T05:00:00Z")


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


def test_resolve_reset_picks_earliest_future():
    now = ur.parse_ts("2026-06-21T02:00:00Z")
    block_start = ur.parse_ts("2026-06-21T00:00:00Z")
    early = ur.parse_ts("2026-06-21T04:30:00Z")
    late = ur.parse_ts("2026-06-21T06:00:00Z")
    resets = [ur.ResetEvent(now, late), ur.ResetEvent(now, early)]
    reset_at, source = ur.resolve_reset(block_start, resets, timedelta(hours=5), now)
    assert reset_at == early
    assert source == "logged"


def test_resolve_reset_logged_without_active_block():
    now = ur.parse_ts("2026-06-21T02:00:00Z")
    future = ur.parse_ts("2026-06-21T05:00:00Z")
    reset_at, source = ur.resolve_reset(None, [ur.ResetEvent(now, future)],
                                        timedelta(hours=5), now)
    assert reset_at == future
    assert source == "logged"


def test_read_snapshot_post_limit_window(tmp_path):
    proj = tmp_path / "projects" / "p1"
    proj.mkdir(parents=True)
    _write_jsonl(proj / "s.jsonl", [
        {"timestamp": "2026-06-21T01:30:00Z", "error": "rate_limit",
         "apiErrorStatus": 429, "message": {"content": [{"type": "text",
          "text": "You've hit your session limit · resets 5am (UTC)"}]}}])
    config = {"weights": WEIGHTS, "calibrated_cap": None, "default_cap_estimate": 500000,
              "window_hours": 5, "lookback_hours": 6, "timezone": "UTC"}
    now = ur.parse_ts("2026-06-21T02:00:00Z")
    snap = ur.read_snapshot(tmp_path, config, now)
    assert snap.reset_source == "logged"
    assert snap.reset_at == ur.parse_ts("2026-06-21T05:00:00Z")
    assert snap.window_start == ur.parse_ts("2026-06-21T00:00:00Z")
    assert snap.tokens_used == 0.0


def test_read_snapshot_ignores_stale_logged_reset(tmp_path):
    proj = tmp_path / "projects" / "p1"
    proj.mkdir(parents=True)
    _write_jsonl(proj / "s.jsonl", [
        # stale 429 from an earlier window (its 5am reset already passed by `now`)
        {"timestamp": "2026-06-21T04:00:00Z", "error": "rate_limit",
         "apiErrorStatus": 429, "message": {"content": [{"type": "text",
          "text": "resets 5am (UTC)"}]}},
        # a fresh window of activity well after that reset
        {"type": "assistant", "timestamp": "2026-06-21T09:00:00Z",
         "message": {"usage": {"output_tokens": 30}}},
        {"type": "assistant", "timestamp": "2026-06-21T10:00:00Z",
         "message": {"usage": {"output_tokens": 30}}},
    ])
    config = {"weights": WEIGHTS, "calibrated_cap": 1000.0, "default_cap_estimate": 500000,
              "window_hours": 5, "lookback_hours": 6, "timezone": "UTC"}
    now = ur.parse_ts("2026-06-21T11:00:00Z")
    snap = ur.read_snapshot(tmp_path, config, now)
    assert snap.reset_source == "computed"
    assert snap.reset_at == ur.parse_ts("2026-06-21T14:00:00Z")
    assert snap.window_start == ur.parse_ts("2026-06-21T09:00:00Z")

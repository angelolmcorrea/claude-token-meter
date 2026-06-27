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
    turns, resets = ur.iter_events(lines, WEIGHTS, "America/Sao_Paulo",
                                   ur.parse_ts("2026-06-21T02:00:00Z"))
    assert len(turns) == 1
    assert turns[0].weighted == 10.0
    assert len(resets) == 1
    assert resets[0].reset_at is not None


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

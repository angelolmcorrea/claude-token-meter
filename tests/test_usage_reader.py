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
    assert resets[0].reset_at is None

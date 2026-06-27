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

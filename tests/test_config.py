import json
from claude_token_meter import config as cfg


def test_load_creates_defaults(tmp_path):
    path = tmp_path / "config.json"
    c = cfg.load(path)
    assert c["refresh_seconds"] == 60
    assert c["thresholds"]["amber"] == 0.60
    assert c["credentials_path"] is None
    assert c["autostart"] is True
    assert path.exists()  # written on first load


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    c = cfg.load(path)
    c["window"]["x"] = 100
    cfg.save(c, path)
    again = cfg.load(path)
    assert again["window"]["x"] == 100


def test_load_fills_missing_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"refresh_seconds": 5}), encoding="utf-8")
    c = cfg.load(path)
    assert c["refresh_seconds"] == 5            # user value kept
    assert c["thresholds"]["red"] == 0.85       # missing key backfilled

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

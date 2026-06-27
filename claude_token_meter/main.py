import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from claude_token_meter import config as cfg
from claude_token_meter import usage_client as uc
from claude_token_meter import autostart
from claude_token_meter.widget import MeterWidget


def _credentials_path(config) -> Path | None:
    cp = config.get("credentials_path")
    return Path(cp) if cp else None


def main():
    config = cfg.load()
    app = QApplication(sys.argv)

    def toggle_autostart():
        if autostart.is_enabled():
            autostart.disable()
            config["autostart"] = False
        else:
            autostart.enable()
            config["autostart"] = True
        cfg.save(config)

    widget = MeterWidget(config, app.quit, toggle_autostart)
    widget.show()

    if config.get("autostart") and not autostart.is_enabled():
        autostart.enable()

    creds = _credentials_path(config)
    state = {"last_ok": None}

    def tick():
        snap = uc.get_snapshot(creds)
        if snap.status == "ok":
            state["last_ok"] = snap
            display = snap
        elif snap.status in ("offline", "ratelimited") and state["last_ok"] is not None:
            # transient: keep showing the last good value instead of blanking out
            display = state["last_ok"]
        else:
            display = snap  # expired/error, or nothing good yet -> show the state
        # persist any drag move
        if (config["window"]["x"], config["window"]["y"]) != (widget.x(), widget.y()):
            config["window"]["x"], config["window"]["y"] = widget.x(), widget.y()
            cfg.save(config)
        widget.update_snapshot(display)

    tick()
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(config["refresh_seconds"] * 1000)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

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

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

    def tick():
        snap = uc.get_snapshot(creds)
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

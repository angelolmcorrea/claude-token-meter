import logging
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

ICON_PATH = Path(__file__).parent / "assets" / "icon.ico"

from claude_token_meter import config as cfg
from claude_token_meter import geometry as geo
from claude_token_meter import usage_client as uc
from claude_token_meter import autostart
from claude_token_meter import status as st
from claude_token_meter.widget import MeterWidget

log = logging.getLogger("claude_token_meter")


def _setup_logging() -> None:
    """Log minimo em %APPDATA%/claude-token-meter/meter.log — evidencia de
    quando a janela e fechada/ressuscitada (o processo roda sob pythonw,
    entao sem isto qualquer morte e silenciosa)."""
    path = cfg.default_config_path().parent / "meter.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def _credentials_path(config) -> Path | None:
    cp = config.get("credentials_path")
    return Path(cp) if cp else None


def main():
    _setup_logging()
    config = cfg.load()
    app = QApplication(sys.argv)
    # so o "Sair" do menu encerra; fechar a janela (WM_CLOSE de fora) nao
    app.setQuitOnLastWindowClosed(False)
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    log.info("iniciado")
    app.aboutToQuit.connect(lambda: log.info("encerrando (event loop terminou)"))

    def toggle_autostart():
        if autostart.is_enabled():
            autostart.disable()
            config["autostart"] = False
        else:
            autostart.enable()
            config["autostart"] = True
        cfg.save(config)

    widget = MeterWidget(config, app.quit, toggle_autostart, autostart.is_enabled)
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

    def _screen_rects():
        return [
            (g.x(), g.y(), g.width(), g.height())
            for g in (s.availableGeometry() for s in app.screens())
        ]

    # poll rapido e barato (le so um arquivo local) pra bolinha reagir ~na hora,
    # desacoplado do poll da API de uso (que fica em refresh_seconds)
    def status_tick():
        widget.update_status(st.read_status())
        # watchdog da janela: terceiros mandam WM_CLOSE (instalador, taskkill
        # sem /f) ou o monitor da janela desliga — reexibe/reposiciona.
        # Nao reexibe durante o "Sair" (senao brigaria com o encerramento).
        if widget._quitting:
            return
        if not widget.isVisible():
            log.warning("janela sumiu (fechada por fora) — reexibindo")
            widget.show()
        screens = _screen_rects()
        fg = widget.frameGeometry()
        if screens and not geo.rect_visible((fg.x(), fg.y(), fg.width(), fg.height()), screens):
            nx, ny = geo.fallback_pos(screens, fg.width(), fg.height())
            log.warning(
                "janela fora das telas em (%s,%s) — movendo pra (%s,%s)",
                fg.x(), fg.y(), nx, ny,
            )
            widget.move(nx, ny)

    status_tick()
    status_timer = QTimer()
    status_timer.timeout.connect(status_tick)
    status_timer.start(config.get("status_poll_seconds", 1) * 1000)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

"""Regressao do bug em que o 'Sair' do menu nao encerrava: o app.quit()
entrega um QCloseEvent a janela e o closeEvent (imune a fechamento externo)
vetava o proprio quit. Tambem cobre o feedback (checkmark) do autostart.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from claude_token_meter.widget import MeterWidget

CONFIG = {
    "thresholds": {"amber": 0.6, "red": 0.85},
    "window": {"x": 100, "y": 100, "opacity": 0.92},
}


@pytest.fixture
def app():
    a = QApplication.instance() or QApplication([])
    a.setQuitOnLastWindowClosed(False)
    return a


def _click_menu_item(app, widget, prefix):
    """Abre o menu real (m.exec, loop aninhado) e dispara o item cujo texto
    comeca com `prefix`, exatamente como um clique do usuario."""
    def trigger():
        menu = app.activePopupWidget()
        assert menu is not None, "menu de contexto nao abriu"
        action = next(a for a in menu.actions() if a.text().startswith(prefix))
        action.trigger()
    QTimer.singleShot(50, trigger)
    widget._menu(widget.mapToGlobal(widget.rect().center()))


def test_sair_encerra_o_app(app):
    widget = MeterWidget(CONFIG, app.quit, lambda: None)
    widget.show()

    # watchdog identico em espirito ao main.py: reexibe se sumir
    watch = QTimer()
    watch.timeout.connect(lambda: widget._quitting or widget.isVisible() or widget.show())
    watch.start(20)

    QTimer.singleShot(10, lambda: _click_menu_item(app, widget, "Sair"))
    # rede de seguranca: se travar (bug), forca saida com codigo != 0
    QTimer.singleShot(2000, lambda: app.exit(99))

    rc = app.exec()
    assert rc == 0, "o 'Sair' nao encerrou o app (closeEvent vetou o quit)"


def test_autostart_item_reflete_estado(app):
    estado = {"on": True}
    widget = MeterWidget(
        CONFIG, app.quit, lambda: None,
        is_autostart_enabled=lambda: estado["on"],
    )
    widget.show()

    capturado = {}

    def inspect():
        menu = app.activePopupWidget()
        action = next(a for a in menu.actions() if a.text().startswith("Iniciar"))
        capturado["checkable"] = action.isCheckable()
        capturado["checked"] = action.isChecked()
        menu.close()

    QTimer.singleShot(50, inspect)
    widget._menu(widget.mapToGlobal(widget.rect().center()))

    assert capturado["checkable"] is True
    assert capturado["checked"] is True

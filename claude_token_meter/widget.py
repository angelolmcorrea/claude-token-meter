from datetime import datetime, timezone

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QBrush, QFont
from PySide6.QtWidgets import QWidget, QMenu

WIDTH, HEIGHT = 300, 34
GREEN = QColor("#3FB950")
AMBER = QColor("#D29922")
RED = QColor("#F85149")
BG = QColor(20, 22, 26, 235)
TRACK = QColor(255, 255, 255, 28)
TEXT = QColor("#E6EDF3")
MUTED = QColor("#8B949E")

# bolinhas de estado da sessao (estilo controles de janela do macOS):
# vermelho=trabalhando, amarelo=aguardando confirmacao, verde=livre.
_DOT_R = 3.5           # raio
_DOT_GAP = 11.0        # distancia entre centros
_DOT_RIGHT = 10.0      # margem a direita ate o centro do ultimo dot
_DOT_DIM_ALPHA = 60    # alpha dos dots inativos
_STATE_COLOR = {"working": RED, "waiting": AMBER, "free": GREEN}

_STATUS_WORD = {
    "auth": "expirado",
    "offline": "offline",
    "error": "erro",
    "ratelimited": "aguardando",
}
_STATUS_TIP = {
    "auth": "Token expirado — rode o Claude Code pra renovar",
    "offline": "Sem conexao com a API de uso",
    "error": "Erro ao consultar o uso",
    "ratelimited": "A API limitou as consultas — tentando de novo em breve",
}


class MeterWidget(QWidget):
    def __init__(self, config, on_quit, on_toggle_autostart):
        super().__init__()
        self._config = config
        self._on_quit = on_quit
        self._on_toggle_autostart = on_toggle_autostart
        self._snapshot = None
        self._status = None  # "working" | "waiting" | "free" | None
        self._drag_offset = None

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WIDTH, HEIGHT)
        self.setWindowOpacity(config["window"].get("opacity", 0.92))

        pos = config.get("window", {})
        if pos.get("x") is not None and pos.get("y") is not None:
            self.move(pos["x"], pos["y"])

    def update_snapshot(self, snapshot):
        self._snapshot = snapshot
        if snapshot is None:
            self.setToolTip("")
        elif snapshot.status != "ok":
            self.setToolTip(_STATUS_TIP.get(snapshot.status, ""))
        elif snapshot.weekly_pct is not None:
            self.setToolTip(
                f"Sessao: {int(snapshot.pct * 100)}%  ·  "
                f"Semanal: {int(snapshot.weekly_pct * 100)}%"
            )
        else:
            self.setToolTip(f"Sessao: {int(snapshot.pct * 100)}%")
        self.update()  # trigger repaint

    def update_status(self, state):
        if state != self._status:
            self._status = state
            self.update()

    def _color(self, pct):
        t = self._config["thresholds"]
        if pct >= t["red"]:
            return RED
        if pct >= t["amber"]:
            return AMBER
        return GREEN

    def _reset_label(self, snap, now):
        if snap is None:
            return "--"
        if snap.status != "ok":
            return _STATUS_WORD.get(snap.status, "--")
        if snap.reset_at is None:
            return ""
        delta = snap.reset_at - now
        mins = max(0, int(delta.total_seconds() // 60))
        if mins >= 60:
            return f"reset {mins // 60}h{mins % 60:02d}"
        return f"reset {mins}m"

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, WIDTH, HEIGHT)
        p.setBrush(QBrush(BG))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect, 8, 8)

        snap = self._snapshot
        now = datetime.now(timezone.utc)
        ok = bool(snap and snap.status == "ok")
        pct = snap.pct if ok else 0.0

        bar = QRectF(8, HEIGHT - 11, WIDTH - 16, 5)
        p.setBrush(QBrush(TRACK))
        p.drawRoundedRect(bar, 2.5, 2.5)
        if pct > 0:
            fill = QRectF(bar.x(), bar.y(), bar.width() * pct, bar.height())
            p.setBrush(QBrush(self._color(pct)))
            p.drawRoundedRect(fill, 2.5, 2.5)

        if ok:
            label = f"{int(pct * 100)}%   {self._reset_label(snap, now)}"
            p.setPen(TEXT)
        else:
            label = self._reset_label(snap, now)
            p.setPen(MUTED)
        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        # reserva a faixa da direita pras 3 bolinhas
        dots_span = _DOT_GAP * 2 + _DOT_R * 2 + _DOT_RIGHT + 6
        p.drawText(
            QRectF(10, 3, WIDTH - 10 - dots_span, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            label,
        )
        self._draw_status_dots(p)

    def _draw_status_dots(self, p):
        cy = 10.5
        # da direita pra esquerda: verde, amarelo, vermelho (ordem macOS invertida)
        cx_right = WIDTH - _DOT_RIGHT
        order = ("working", "waiting", "free")  # esquerda -> direita
        cxs = [cx_right - _DOT_GAP * (2 - i) for i in range(3)]
        p.setPen(Qt.NoPen)
        for state, cx in zip(order, cxs):
            base = _STATE_COLOR[state]
            if state == self._status:
                col = base
            else:
                col = QColor(base)
                col.setAlpha(_DOT_DIM_ALPHA)
            p.setBrush(QBrush(col))
            p.drawEllipse(QRectF(cx - _DOT_R, cy - _DOT_R, _DOT_R * 2, _DOT_R * 2))

    # --- dragging ---
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif e.button() == Qt.RightButton:
            self._menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _e):
        if self._drag_offset is not None:
            self._drag_offset = None
            self._config["window"]["x"] = self.x()
            self._config["window"]["y"] = self.y()

    def _menu(self, global_pos):
        m = QMenu()
        m.addAction("Iniciar com o Windows", self._on_toggle_autostart)
        m.addSeparator()
        m.addAction("Sair", self._on_quit)
        m.exec(global_pos)

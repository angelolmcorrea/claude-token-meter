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


class MeterWidget(QWidget):
    def __init__(self, config, on_quit, on_recalibrate, on_toggle_autostart):
        super().__init__()
        self._config = config
        self._on_quit = on_quit
        self._on_recalibrate = on_recalibrate
        self._on_toggle_autostart = on_toggle_autostart
        self._snapshot = None
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
        self.update()  # trigger repaint

    def _color(self, pct):
        t = self._config["thresholds"]
        if pct >= t["red"]:
            return RED
        if pct >= t["amber"]:
            return AMBER
        return GREEN

    def _reset_label(self, snap, now):
        if snap is None or snap.reset_source == "idle" or snap.reset_at is None:
            return "ocioso"
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
        pct = snap.pct if snap else 0.0

        bar = QRectF(8, HEIGHT - 11, WIDTH - 16, 5)
        p.setBrush(QBrush(TRACK))
        p.drawRoundedRect(bar, 2.5, 2.5)
        if pct > 0:
            fill = QRectF(bar.x(), bar.y(), bar.width() * pct, bar.height())
            p.setBrush(QBrush(self._color(pct)))
            p.drawRoundedRect(fill, 2.5, 2.5)

        prefix = "~" if (snap and snap.is_estimate) else ""
        label = f"{prefix}{int(pct * 100)}%   {self._reset_label(snap, now)}"
        p.setPen(TEXT)
        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        p.drawText(QRectF(10, 3, WIDTH - 20, 16), Qt.AlignLeft | Qt.AlignVCenter, label)

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
        m.addAction("Recalibrar teto", self._on_recalibrate)
        m.addAction("Iniciar com o Windows", self._on_toggle_autostart)
        m.addSeparator()
        m.addAction("Sair", self._on_quit)
        m.exec(global_pos)

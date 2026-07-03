"""Geometria pura da janela vs telas (sem PySide6, pra ser testavel).

Existe por causa do bug "widget some depois de um tempo": a janela pode ser
fechada por WM_CLOSE de terceiros ou ficar fora de tela quando um monitor
(ex.: o secundario em coordenada negativa) desliga. O watchdog no main usa
estas funcoes pra decidir quando reexibir/reposicionar.
"""

Rect = tuple[int, int, int, int]  # x, y, w, h


def rect_visible(rect: Rect, screens: list[Rect], min_px: int = 8) -> bool:
    """True se ao menos min_px x min_px do rect intersecta alguma tela."""
    x, y, w, h = rect
    for sx, sy, sw, sh in screens:
        ix = min(x + w, sx + sw) - max(x, sx)
        iy = min(y + h, sy + sh) - max(y, sy)
        if ix >= min_px and iy >= min_px:
            return True
    return False


def fallback_pos(screens: list[Rect], w: int, h: int, margin: int = 16) -> tuple[int, int]:
    """Posicao segura: canto superior direito da primeira tela (primaria)."""
    sx, sy, sw, sh = screens[0]
    return sx + sw - w - margin, sy + margin

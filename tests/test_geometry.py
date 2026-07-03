from claude_token_meter.geometry import fallback_pos, rect_visible

PRIMARY = (0, 0, 1920, 1040)          # availableGeometry da tela primaria
SECOND_LEFT = (-1920, 0, 1920, 1040)  # monitor secundario a esquerda (coords negativas)


def test_rect_dentro_da_primaria_e_visivel():
    assert rect_visible((100, 100, 300, 34), [PRIMARY]) is True


def test_rect_no_monitor_negativo_e_visivel():
    # posicao real do widget do Rod: x=-695 (monitor da esquerda)
    assert rect_visible((-695, 596, 300, 34), [PRIMARY, SECOND_LEFT]) is True


def test_rect_no_monitor_negativo_some_quando_monitor_desliga():
    # mesmo rect, mas so a primaria presente -> fora de tela
    assert rect_visible((-695, 596, 300, 34), [PRIMARY]) is False


def test_rect_totalmente_fora_e_invisivel():
    assert rect_visible((5000, 5000, 300, 34), [PRIMARY]) is False


def test_sliver_menor_que_minimo_nao_conta_como_visivel():
    # so 4px dentro da tela (min_px default = 8)
    assert rect_visible((-296, 100, 300, 34), [PRIMARY]) is False


def test_borda_com_sobreposicao_suficiente_e_visivel():
    # 20px dentro da tela
    assert rect_visible((-280, 100, 300, 34), [PRIMARY]) is True


def test_fallback_cai_dentro_da_primeira_tela():
    x, y = fallback_pos([PRIMARY, SECOND_LEFT], 300, 34)
    assert rect_visible((x, y, 300, 34), [PRIMARY]) is True
    # canto superior direito, com margem
    assert x + 300 <= PRIMARY[0] + PRIMARY[2]
    assert y >= PRIMARY[1]

# Barra semanal no widget — design

**Data:** 2026-07-03 · **Decisão do Rod:** opção "duas barras" (escolhida entre duas barras / só texto / clique alterna).

## O que

Mostrar o uso **semanal** (`seven_day`, que o `usage_client` já traz no snapshot e hoje
só aparece no tooltip) como uma **segunda barra** no widget, abaixo da barra da sessão.

## Como

- `HEIGHT` 34 → 42. Linha de texto e bolinhas de estado ficam onde estão.
- Barra da **sessão**: 5px (como hoje). Barra da **semana**: 3,5px, logo abaixo —
  mais fina de propósito, pra hierarquia visual (sessão é o número de ação imediata).
- Mesma régua de cor pras duas: `thresholds` do config (verde < amber < red),
  cada barra colorida pelo **próprio** pct.
- `weekly_pct` ausente (API sem `seven_day`): trilho da semana desenhado vazio —
  o widget não muda de tamanho nem "pisca".
- Tooltip continua como está (já mostra os dois percentuais).

## O que NÃO muda

- Zero chamada extra na API (mesmo GET de sempre — princípio ZERO token).
- `main.py`, `usage_client.py`, config e hooks intocados.
- Sem teste unitário novo: mudança 100% de apresentação em `widget.py`
  (decisão registrada no CLAUDE.md do repo). Suíte existente precisa seguir verde.

## Verificação

Relançar o widget e conferir visualmente (screenshot da região da janela):
duas barras, cores certas, texto/bolinhas intactos, altura 42px.

# CLAUDE.md — claude-token-meter

Medidor de uso da janela de sessão do Claude Code: barra de uma linha, always-on-top, no Windows.

## Stack

- **Python 3.11+** (stdlib: `json`, `urllib`, `datetime`), **PySide6** (GUI), **pytest**.
- Pacote **flat** `claude_token_meter/` na raiz — roda com `python -m claude_token_meter.main`, **sem install** (o `conftest.py` na raiz põe o pacote no path).

## Comandos

- Setup: `py -3 -m venv .venv` → `.venv\Scripts\python -m pip install -r requirements.txt`
- Testes: `.venv\Scripts\python -m pytest -q`
- Rodar: `iniciar.bat` (chama `pythonw -m claude_token_meter.main`)

## Princípios invioláveis deste projeto

- **ZERO token.** É consulta de **uso**, nunca chamada de modelo. A fonte é `GET https://api.anthropic.com/api/oauth/usage` com o token OAuth de `~/.claude/.credentials.json` (headers `anthropic-beta: oauth-2025-04-20`, `anthropic-version: 2023-06-01`).
- **Nunca renovar o token** — o CLI mantém fresco; em 401/403 → status `expirado`.
- **Educado com a API:** `refresh_seconds >= 60`; tratar **429** como transitório (`aguardando`) e **manter o último valor bom** em falhas passageiras.
- **Sem reconstruir o % por soma de tokens locais** — isso foi a v0.1 e era impreciso (o `cache_read` dominava). Decisão registrada na seção 14 da spec.

## TDD e organização

- `usage_client.py` é a **lógica testável** (rede via urllib) — teste com **mocks** de `read_token`/`fetch_usage`, **nunca** chamando a rede real nos testes; use a resposta real como fixture.
- `widget.py` é **fino de propósito** (só apresentação, sem lógica) — não tem teste unitário.
- TDD: teste falhando → implementa → passa → commit pequeno.

## Como agir

Comunicação em **português**. **Propor antes de criar**; esperar "sim". **Bugfix não vira refactor.** Sem otimismo. **Sem emojis** em código.

Docs no repo: `docs/superpowers/specs/` e `docs/superpowers/plans/`. Vault: `Cerberus/02_CLIENTES/PROJETOS_PARTICULARES/PRODUTOS/06_CLAUDE_TOKEN_METER/`.

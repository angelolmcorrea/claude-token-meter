# claude-token-meter

Janelinha always-on-top (Windows) que mostra, numa barra de uma linha, o
consumo da janela de sessao atual do Claude Code (% + tempo pra resetar).

**Le o numero REAL** — a mesma fonte que o comando `/usage` do Claude Code
usa: o endpoint `GET /api/oauth/usage` da Anthropic, autenticado com o token
OAuth que ja esta no seu `~/.claude/.credentials.json`. O `%` bate exato com
o que o app mostra.

**Custo em tokens: zero.** E uma consulta de uso, nao uma chamada de modelo.
Precisa de rede e do seu login do Claude Code; nunca renova o token sozinho
(o proprio CLI mantem ele fresco no arquivo) — se expirar, a barra mostra
"expirado" ate voce rodar o Claude Code de novo.

## Rodar

```
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
iniciar.bat
```

Arrasta com o mouse pra reposicionar. Clique-direito: iniciar com o Windows,
sair. Passa o mouse por cima pra ver o uso semanal no tooltip.

## O que a barra mostra

- `NN%` + `reset 4h28` — utilizacao da janela de sessao de 5h e quanto falta
  pra resetar (campo `five_hour` do endpoint).
- Cores: verde / ambar (>=60%) / vermelho (>=85%) — thresholds configuraveis.
- Estados sem dado: `expirado` (token venceu), `offline` (sem rede), `erro`.
- Tooltip: sessao + uso semanal (`seven_day`).

Config em `%APPDATA%\claude-token-meter\config.json` (intervalo de refresh,
thresholds de cor, timezone, posicao, caminho do credentials).

## Privacidade

O medidor le o token OAuth de `~/.claude/.credentials.json` e o envia apenas
para `api.anthropic.com` (o mesmo destino do proprio Claude Code), via HTTPS,
so no header Authorization. Nada e gravado nem enviado pra outro lugar.

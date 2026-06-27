# claude-token-meter

Janelinha always-on-top (Windows) que mostra, numa barra de uma linha, o
consumo da janela de sessao atual do Claude Code (% + tempo pra resetar).

100% offline e passivo: le apenas os transcripts locais em
`~/.claude/projects/**/*.jsonl`. Nao chama a API nem nenhum modelo — custo
em tokens: zero.

## Rodar

```
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
iniciar.bat
```

Arrasta com o mouse pra reposicionar. Clique-direito: recalibrar teto,
iniciar com o Windows, sair.

## Como a % e calculada

A barra mostra os tokens ponderados usados na janela de 5h sobre um teto.
O teto (100%) **se auto-calibra**: quando o Claude Code loga um limite de
sessao batido (429), o total acumulado naquele instante vira o teto. Antes
da primeira batida, a barra mostra `~NN%` (estimativa). E uma aproximacao
calibrada, nao uma medicao exata — boa pra "estou perto de estourar?".

Config em `%APPDATA%\claude-token-meter\config.json` (pesos, thresholds de
cor, intervalo, timezone, posicao).

# Spec — claude-token-meter

> Design validado com Angelo em 2026-06-27. Status: aprovado, aguardando review do arquivo antes do plano de implementação.

## 1. Objetivo

Uma janelinha sempre visível (always-on-top, frameless, arrastável) no Windows que mostra, numa **barra de uma linha**, quanto da janela de sessão atual do Claude Code já foi consumida e quanto tempo falta pra resetar. A barra muda de cor com o "calor" (verde → âmbar → vermelho).

Formato na tela:

```
[############------]  62%  reset 1h42
```

**Restrição central:** o medidor é 100% passivo e offline. Ele NUNCA chama a API nem nenhum modelo do Claude — só lê arquivos locais e faz conta. Consumo de tokens do próprio medidor: zero.

## 2. Não-objetivos (YAGNI nesta versão)

- Limite **semanal** do Claude (só a janela de sessão de 5h por enquanto).
- Gráficos históricos / dashboards.
- Empacotamento em `.exe` (roda via Python + venv, padrão do Transcritor).
- Multiplataforma (só Windows).

## 3. Fonte de dados

Os transcripts locais do Claude Code em `~/.claude/projects/**/*.jsonl` (no Windows: `C:\Users\<user>\.claude\projects\`). **Todos os projetos**, porque o limite de sessão do Claude é da conta inteira, não de uma conversa.

Cada linha é um JSON. Os dois tipos de linha que interessam:

**a) Turno do assistant** — tem uso de tokens:
```json
{
  "type": "assistant",
  "timestamp": "2026-06-21T03:42:07.811Z",
  "sessionId": "...",
  "message": {
    "usage": {
      "input_tokens": 2,
      "cache_creation_input_tokens": 90,
      "cache_read_input_tokens": 179298,
      "output_tokens": 436
    }
  }
}
```

**b) Limite de sessão batido** — 429 com o horário de reset em texto:
```json
{
  "timestamp": "2026-06-21T03:42:07.811Z",
  "error": "rate_limit",
  "isApiErrorMessage": true,
  "apiErrorStatus": 429,
  "message": { "content": [ { "type": "text",
    "text": "You've hit your session limit · resets 2:20am (America/Sao_Paulo)" } ] }
}
```

Observação confirmada na exploração: o horário de reset ("resets 2:20am") **não é alinhado à hora cheia** — é exatamente 5h depois do primeiro uso da janela (2:20 = primeiro uso às 21:20).

## 4. Modelo da janela de sessão

1. Carrega as linhas dos arquivos com `mtime` dentro de `lookback_hours` (default 6h — cobre a janela de 5h com folga). Para cada arquivo lê só o necessário; ignora linha malformada.
2. Junta dois conjuntos ordenados por timestamp: **turnos** (com `usage`) e **eventos de reset** (429 com horário parseado).
3. **Detecta o bloco ativo** (estilo "5h fixas a partir do primeiro uso):
   - Varre turnos em ordem crescente. `block_start` = ts do primeiro turno do bloco. Enquanto o próximo turno tiver ts ≤ `block_start + window_hours`, ele pertence ao bloco. Quando um turno passa disso, abre novo bloco nesse ts.
   - **Bloco ativo** = último bloco, se `now ≤ block_start + window_hours`. Senão não há sessão ativa (estado "ocioso").
   - `reset_at = block_start + window_hours`.
   - **Override autoritativo:** se existe um evento de reset (429) com horário futuro (> now), ele manda — `reset_at` = horário logado e `block_start = reset_at - window_hours`.
4. `tokens_used` = soma ponderada do `usage` de todos os turnos com ts em `[block_start, now]`.

## 5. Cálculo da porcentagem (o ponto delicado)

**Ponderação dos tokens.** `weighted(usage) = input*wi + output*wo + cache_creation*wc + cache_read*wr`, com pesos configuráveis. Default: `wi=wo=wc=1.0`, `wr=0.1` (o `cache_read` é enorme e barato; peso baixo evita ele dominar a barra).

**Teto (100%) — auto-calibrado.** Não temos o limite real do plano localmente, mas o 429 entrega ele de graça: no instante em que um evento "session limit" dispara, a soma ponderada acumulada do bloco até ali ≈ o teto efetivo.
- A cada varredura, para cada evento de reset encontrado, calcula a soma ponderada do bloco dele até o ts do evento → **teto observado**. Persiste o **mais recente** em `config.calibrated_cap` (sobrevive a restart e a sair da janela de `mtime`).
- `pct = tokens_used / calibrated_cap` (clamp 0..1).

**Antes da primeira calibração.** Usa `default_cap_estimate` e marca a barra como aproximada — prefixo `~` no número (ex: `~48%`) e tooltip "estimativa até a 1ª calibração". Override manual de `calibrated_cap` sempre disponível no config.

**Limitação honesta (documentar no README):** como numerador e teto usam a mesma fórmula, a % no momento do 429 fica certa (~100%), e a escala global é invariante. Mas o **formato da curva no meio da janela** depende de os pesos baterem com a métrica real do Claude — que é desconhecida. Então a barra é uma **aproximação calibrada**, não uma medição exata. É bom o suficiente pra "estou perto de estourar?", que é o objetivo.

## 6. Arquitetura (módulos isolados)

```
src/claude_token_meter/
  usage_reader.py   # logica pura, SEM Qt — varre JSONL -> UsageSnapshot
  config.py         # carrega/salva JSON de config em %APPDATA%
  autostart.py      # cria/remove atalho na pasta Startup do Windows
  widget.py         # janela PySide6 (barra + label + menu); sem logica de negocio
  main.py           # QTimer chama o reader a cada refresh_seconds e atualiza o widget
```

- **`usage_reader.py`** — interface: `read_snapshot(claude_dir, config, now) -> UsageSnapshot`. `UsageSnapshot = {window_start, reset_at, tokens_used, cap, pct, is_estimate, reset_source ("logged"|"computed"|"idle")}`. É o módulo testável de verdade. Depende só de stdlib (`json`, `pathlib`, `datetime`, `zoneinfo`).
- **`config.py`** — `load() -> Config`, `save(config)`. Arquivo em `%APPDATA%\claude-token-meter\config.json`. Cria com defaults se não existe.
- **`autostart.py`** — `is_enabled()`, `enable()`, `disable()`. Cria/remove um `.lnk` em `shell:startup` apontando pra `pythonw.exe -m claude_token_meter.main`.
- **`widget.py`** — `MeterWidget(QWidget)`: recebe um `UsageSnapshot` e redesenha. Sem QTimer, sem leitura de arquivo — só apresentação. Facilita trocar a fonte.
- **`main.py`** — wiring: cria QApplication, widget, config, e um QTimer de `refresh_seconds`. Cada tick: `read_snapshot` → `widget.update_snapshot(...)`.

## 7. Config (schema JSON)

```json
{
  "weights": { "input": 1.0, "output": 1.0, "cache_creation": 1.0, "cache_read": 0.1 },
  "calibrated_cap": null,
  "default_cap_estimate": 500000,
  "window_hours": 5,
  "lookback_hours": 6,
  "refresh_seconds": 10,
  "thresholds": { "amber": 0.60, "red": 0.85 },
  "timezone": "America/Sao_Paulo",
  "window": { "x": null, "y": null, "opacity": 0.92 },
  "autostart": true
}
```

`default_cap_estimate` (500000 ponderado) é só um chute inicial; não é crítico porque se auto-corrige no primeiro 429. `timezone` é usado pra exibir o countdown no horário local e pra interpretar o "resets 2:20am".

## 8. Comportamento do widget

- **Janela:** `FramelessWindowHint | WindowStaysOnTopHint | Tool` (o `Tool` tira da barra de tarefas). Fundo translúcido arredondado (~300×34px). Opacidade de `config.window.opacity`.
- **Desenho:** retângulo de fundo + preenchimento da barra colorido pelo threshold + texto sobreposto `NN%  reset 1h42` (com `~` se `is_estimate`).
- **Cores:** `pct < amber` → verde; `amber ≤ pct < red` → âmbar; `pct ≥ red` → vermelho. Thresholds do config.
- **Countdown:** `≥1h` → `reset 1h42`; `<1h` → `reset 42m`; sem sessão ativa → `ocioso` (barra vazia/cinza).
- **Arrastar:** mousePress/mouseMove movem a janela; ao soltar, salva `window.x/y` no config.
- **Menu (clique-direito):** Recalibrar (limpa `calibrated_cap` pra redetectar), Resetar posição, "Iniciar com o Windows" (toggle via `autostart.py`), Opacidade (+/−), Sair.
- **Tooltip (hover):** detalhe — tokens ponderados usados, teto, reset absoluto (ex: "reseta às 02:20"), e fonte do reset (logado/estimado).
- Roda via `pythonw` (sem console).

## 9. Parsing do texto de reset

Regex robusto pra `resets (\d{1,2})(:(\d{2}))?\s*(am|pm)` e a timezone entre parênteses, cobrindo `resets 2:20am` e `resets 11pm`. Resolve pra a próxima ocorrência futura daquele horário local. Se o parse falhar, cai no cálculo `block_start + 5h` (degrada com elegância).

## 10. Performance e robustez

- **Não varre os ~220 arquivos a cada tick:** filtra por `mtime` dentro de `lookback_hours` (sobram só os da janela ativa). Custo por tick: abrir um punhado de arquivos pequenos.
- Linha malformada / arquivo travado por escrita concorrente → pula a linha e segue.
- Sem `~/.claude/projects` (ou vazio) → estado "ocioso", sem erro.
- Timestamps são UTC (`Z`); converte pro `config.timezone` só na exibição.

## 11. Testes

- `usage_reader.py` é puro → testes com pytest e fixtures de `.jsonl` em `tests/fixtures/`:
  - janela única simples (soma e pct corretos);
  - duas janelas separadas por gap > 5h (pega só a ativa);
  - evento 429 → calibra o teto a partir da soma até o evento;
  - `cache_read` gigante → confirma que o peso baixo segura a barra;
  - texto de reset variando (`2:20am`, `11pm`) → reset_at certo;
  - sem turnos na janela → estado idle.
- `widget.py` fica fino de propósito (sem lógica), então não tem teste unitário; validação visual manual.

## 12. Layout do projeto e como roda

```
claude-token-meter/
  src/claude_token_meter/{__init__,usage_reader,config,autostart,widget,main}.py
  tests/{test_usage_reader.py, fixtures/*.jsonl}
  docs/superpowers/specs/2026-06-27-claude-token-meter-design.md
  requirements.txt        # PySide6 (+ tzdata se necessário)
  iniciar.bat             # ativa venv e roda via pythonw
  README.md
```

Setup: `python -m venv .venv` → `pip install -r requirements.txt` → `iniciar.bat` (chama `pythonw -m claude_token_meter.main`). Início automático com o Windows: ligado por default no v1 (`autostart.enable()` na primeira execução se `config.autostart`), e toggle no menu.

## 13. Vault

Produto do cliente interno `PROJETOS_PARTICULARES`. O ponteiro no vault (README sob `02_CLIENTES/PROJETOS_PARTICULARES/PRODUTOS/`) fica pra depois, com aval do Angelo — não criar estrutura no vault agora.

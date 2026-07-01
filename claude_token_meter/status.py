"""Estado da sessao do Claude Code, alimentado por hooks.

O medidor e um processo separado e nao sabe o que o Claude esta fazendo.
Os hooks do Claude Code gravam o estado aqui; o widget faz poll e pinta.
Modulo leve de proposito: sem PySide6, pra poder ser usado tambem no hook.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

STATES = ("working", "waiting", "free")


def default_status_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "claude-token-meter" / "status.json"


def write_status(state: str, path: Path | None = None) -> None:
    if state not in STATES:
        raise ValueError(f"estado invalido: {state!r} (use um de {STATES})")
    path = Path(path) if path else default_status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"state": state, "ts": datetime.now(timezone.utc).isoformat()}
    # escrita atomica: grava em .tmp e renomeia, pra o poll nunca ler pela metade
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


def read_status(path: Path | None = None) -> str | None:
    path = Path(path) if path else default_status_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    state = data.get("state") if isinstance(data, dict) else None
    return state if state in STATES else None

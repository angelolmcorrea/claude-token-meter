import json
import os
from copy import deepcopy
from pathlib import Path

DEFAULTS = {
    "refresh_seconds": 60,
    "thresholds": {"amber": 0.60, "red": 0.85},
    "timezone": "America/Sao_Paulo",
    "credentials_path": None,  # None -> ~/.claude/.credentials.json
    "window": {"x": None, "y": None, "opacity": 0.92},
    "autostart": True,
}


def default_config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "claude-token-meter" / "config.json"


def _merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: Path | None = None) -> dict:
    path = Path(path) if path else default_config_path()
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            user = {}
    else:
        user = {}
    merged = _merge(DEFAULTS, user)
    save(merged, path)
    return merged


def save(config: dict, path: Path | None = None) -> None:
    path = Path(path) if path else default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")

import os
import subprocess
import sys
from pathlib import Path

SHORTCUT_NAME = "claude-token-meter.lnk"


def startup_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path(directory: Path | None = None) -> Path:
    return (Path(directory) if directory else startup_dir()) / SHORTCUT_NAME


def is_enabled(directory: Path | None = None) -> bool:
    return shortcut_path(directory).exists()


def disable(directory: Path | None = None) -> None:
    p = shortcut_path(directory)
    if p.exists():
        p.unlink()


def enable(directory: Path | None = None) -> None:
    """Create a .lnk that launches the meter with pythonw (no console flash)."""
    target = str(Path(sys.executable).with_name("pythonw.exe"))
    workdir = str(Path(__file__).resolve().parent.parent)
    args = "-m claude_token_meter.main"
    lnk = str(shortcut_path(directory))
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');"
        "$s.TargetPath='%s';$s.Arguments='%s';"
        "$s.WorkingDirectory='%s';$s.Save()" % (lnk, target, args, workdir)
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)

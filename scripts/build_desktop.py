"""Build the desktop shell's project core: a frozen, console-less-by-parent `launcher.py --serve`.

The core is a PyInstaller one-folder build (no per-launch extraction, one process) placed in
``build/desktop-core/horizon-studio-core/``. The Tauri release config bundles that folder as
``core/`` next to the shell executable (see desktop/tauri.release.conf.json).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORE_NAME = "horizon-studio-core"
CORE_DIST = ROOT / "build" / "desktop-core"


def core_command(root: Path, separator: str) -> list[str]:
    """PyInstaller arguments; every runtime file comes from studio.BUNDLED_FILES."""
    from studio import BUNDLED_FILES
    data = []
    for relative in BUNDLED_FILES:
        target = Path(relative).parent.as_posix()
        data += ["--add-data", f"{root / relative}{separator}{'.' if target == '.' else target}"]
    return [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console",
        "--name", CORE_NAME, "--distpath", str(root / "build" / "desktop-core"),
        "--workpath", str(root / "build" / "desktop-core-work"), "--specpath", str(root / "build"),
        *data,
        # The core never opens a window: the Tk launcher stays in the legacy executable only.
        "--hidden-import", "mod_doctor", "--exclude-module", "tkinter",
        "--icon", str(root / "desktop" / "icons" / "icon.ico"),
        str(root / "launcher.py"),
    ]


def core_executable(dist: Path = CORE_DIST) -> Path:
    return dist / CORE_NAME / (CORE_NAME + (".exe" if sys.platform == "win32" else ""))


def build() -> Path:
    subprocess.run(core_command(ROOT, ";" if sys.platform == "win32" else ":"), cwd=ROOT, check=True)
    output = core_executable()
    if not output.is_file():
        raise RuntimeError(f"PyInstaller did not produce {output}")
    print("Built", output, flush=True)
    return output


if __name__ == "__main__":
    build()

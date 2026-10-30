"""Generate a portable, single-file Windows executable using PyInstaller."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def executable_name(version: str) -> str:
    return f"HorizonStudio-{version}-Windows-x64"


def command(root: Path, version: str, separator: str) -> list[str]:
    """PyInstaller arguments; every runtime file comes from studio.BUNDLED_FILES."""
    from studio import BUNDLED_FILES
    data = []
    for relative in BUNDLED_FILES:
        target = Path(relative).parent.as_posix()
        data += ["--add-data", f"{root / relative}{separator}{'.' if target == '.' else target}"]
    data += ["--add-data", f"{root / 'assets' / 'horizon-studio.ico'}{separator}assets"]
    return [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", executable_name(version), "--distpath", str(root / "dist"), "--workpath", str(root / "build"),
        "--specpath", str(root), *data,
        "--hidden-import", "mod_doctor", "--hidden-import", "tkinter",
        "--icon", str(root / "assets" / "horizon-studio.ico"),
        str(root / "launcher.py"),
    ]


def build() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not version or not all(part.isdecimal() for part in version.split(".")) or len(version.split(".")) != 3:
        raise ValueError("VERSION must contain a numeric semantic version, e.g. 0.5.0")
    name = executable_name(version)
    print("Building", name, flush=True)
    subprocess.run(command(ROOT, version, ";" if sys.platform == "win32" else ":"), cwd=ROOT, check=True)
    output = ROOT / "dist" / f"{name}.exe"
    if sys.platform == "win32" and not output.is_file():
        raise RuntimeError(f"PyInstaller did not produce {output}")
    print("Build completed", output, flush=True)


if __name__ == "__main__":
    build()

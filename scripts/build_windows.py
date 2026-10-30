"""Package Horizon Studio as a standalone Windows x64 application."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def build() -> None:
    root = Path(__file__).resolve().parent.parent
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if len(version.split(".")) != 3 or not all(part.isdecimal() for part in version.split(".")):
        raise ValueError("VERSION must contain a numeric semantic version (e.g. 0.5.0)")
    name = f"HorizonStudio-{version}-Windows-x64"
    sep = ";" if sys.platform == "win32" else ":"
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", name, "--distpath", str(root / "dist"), "--workpath", str(root / "build"),
        "--specpath", str(root),
        "--add-data", f"{root / 'index.html'}{sep}.",
        "--add-data", f"{root / 'i18n.js'}{sep}.",
        "--add-data", f"{root / 'VERSION'}{sep}.",
        "--add-data", f"{root / 'assets' / 'horizon-studio.ico'}{sep}assets",
        "--hidden-import", "mod_doctor", "--hidden-import", "tkinter",
        "--icon", str(root / "assets" / "horizon-studio.ico"),
        str(root / "launcher.py"),
    ]
    subprocess.run(command, cwd=root, check=True)
    output = root / "dist" / f"{name}.exe"
    if sys.platform == "win32" and not output.is_file():
        raise RuntimeError(f"PyInstaller did not produce {output}")
    print("Built", output)


if __name__ == "__main__":
    build()

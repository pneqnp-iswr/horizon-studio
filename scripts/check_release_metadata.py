"""CI guard for stale marketing/release metadata vs the canonical VERSION file."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_release_metadata(root: Path = ROOT) -> list[str]:
    version_file = root / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return [f"Invalid VERSION: {version!r}"]
    major_minor = ".".join(version.split(".")[:2])
    checks = (
        ("RELEASE_NOTES.md", f"# Horizon Studio {version} "),
        ("CHANGELOG.md", f"## {version} "),
        ("docs/FEATURE_MATRIX.md", f"# Capability matrix — Horizon Studio {major_minor}"),
        ("README.md", f"badge/version-{version}-blue"),
        ("README.md", f"Version **{major_minor} "),
        ("README.ru.md", f"Версия **{major_minor} "),
    )
    errors = []
    for relative_path, needle in checks:
        data = (root / relative_path).read_text(encoding="utf-8")
        if needle not in data:
            errors.append(f"{relative_path}: missing {needle!r} (VERSION={version})")
    return errors


def main() -> int:
    errors = check_release_metadata()
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    print("Release metadata consistent with VERSION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

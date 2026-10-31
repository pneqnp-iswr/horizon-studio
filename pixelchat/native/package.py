"""Reproducible, source-only PixelChat .hnmod bundle, following Horizon's native tool.

This tool DOES NOT compile or verify the mod in a game. Never confuse a package
with a successful Horizon mixin application or in-game runtime smoke test.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import tomllib
import zipfile

NATIVE = Path(__file__).resolve().parent
BUNDLE = NATIVE / "mixins" / "pixelchat_hud"


def make_package(native: Path = NATIVE) -> tuple[str, bytes]:
    bundle = native / "mixins" / "pixelchat_hud"
    spec = json.loads((native / "compatibility.json").read_text(encoding="utf-8"))
    parsed = tomllib.loads((bundle / "horizon-mixin.toml").read_text(encoding="utf-8"))
    mod_id, version = parsed["mod"]["id"], parsed["mod"]["version"]
    if mod_id != "pixelchat_hud":
        raise ValueError("Unexpected native module ID")
    if spec.get("horizon_revision") != parsed["compatibility"].get("horizon_revision"):
        raise ValueError("Horizon revision mismatch between manifests")
    if spec.get("hooks") != 1 or spec.get("game") != "26.3":
        raise ValueError("Unsupported native hook version or game")
    if not isinstance(spec.get("horizon_mixins_revision"), str) or len(spec["horizon_mixins_revision"]) != 40:
        raise ValueError("Missing pinned horizon-mixins revision")

    meta = {
        "schema": 1, "id": mod_id, "version": version,
        "game": spec["game"], "horizon": spec["horizon_revision"],
        "mixins": spec["horizon_mixins_revision"], "hooks": spec["hooks"],
    }
    content = {"horizon-native.json": (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode()}
    for file in sorted(bundle.iterdir()):
        if file.suffix in {".rs", ".toml"} and file.is_file():
            content[f"mixins/{mod_id}/{file.name}"] = file.read_bytes()
    if len(content) < 3 or f"mixins/{mod_id}/horizon-mixin.toml" not in content:
        raise ValueError("Missing mixin content")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(content.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return f"{mod_id}-{version}.hnmod", buffer.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build source-only, unverified Horizon PixelChat native bundle")
    parser.add_argument("--output", type=Path, help="Custom .hnmod output path")
    args = parser.parse_args()
    name, package = make_package()
    dest = args.output or NATIVE / "target" / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(package)
    print(json.dumps({"path": str(dest), "sha256": hashlib.sha256(package).hexdigest(),
                      "bytes": len(package), "runtime_verified": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

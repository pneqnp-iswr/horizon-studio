"""Horizon IDE-001: read-only compatibility probe for the existing local Horizon client.

This is NOT a game launch, a proof of working .hmod content, or a proof that a
native renderer can be embedded into Tauri. It checks only the documented launch
interface using the Preview Bridge's exact version validator.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from studio_core.preview_bridge import BridgeError, PreviewBridge, discover

SCHEMA = "horizon-studio.ide-preflight/1"


def report(ctl: str | None = None, *, locate=discover, bridge_type=PreviewBridge) -> dict:
    """Return machine-readable compatibility without starting a world.

    `locate` and `bridge_type` are injectable for fake-process tests.
    """
    result = {
        "schema": SCHEMA,
        "status": "blocked",
        "launch_api": None,
        "installation": None,
        "checks": {
            "client_discovered": "not_checked",
            "launch_api_compatible": "not_checked",
            "game_load": "not_tested",
            "playable_embedded_viewport": "not_tested",
        },
        "notes": [
            "This probe does not launch a game, access saved worlds, download game assets or authenticate users.",
            "A compatible Launch API does not prove a .hmod loads or that native 3D rendering can be embedded.",
        ],
        "error": None,
    }
    # The user explicitly selected a path. Do not silently fall back to a
    # different game on PATH if the selection is misspelled.
    if ctl is not None and not Path(ctl).is_file():
        result["error"] = {"code": "NOT_FOUND", "message": "Selected horizon-ctl file does not exist"}
        result["checks"]["client_discovered"] = "failed"
        return result
    try:
        found = locate(ctl)
        if found.get("game") is None:
            raise BridgeError("VERSION_UNKNOWN", "The horizon-client executable is not beside horizon-ctl")
        result["checks"]["client_discovered"] = "passed"
        result["installation"] = {"ctl": found["ctl"][-1], "game": found["game"][-1]}
        engine = bridge_type(found["ctl"], found["game"])
        details = engine.check_version()
        result["launch_api"] = details
        result["checks"]["launch_api_compatible"] = "passed"
        result["status"] = "compatible_for_preview"
    except BridgeError as exc:
        result["checks"]["launch_api_compatible"] = "failed" if result["checks"]["client_discovered"] == "passed" else "not_checked"
        if result["checks"]["client_discovered"] == "not_checked":
            result["checks"]["client_discovered"] = "failed"
        result["error"] = {"code": exc.code, "message": str(exc)}
    except (OSError, TypeError, ValueError, KeyError) as exc:
        result["error"] = {"code": "PROBE_ERROR", "message": str(exc)}
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check the selected local Horizon installation; do not launch the game")
    parser.add_argument("--ctl", help="Existing horizon-ctl path (otherwise use HORIZON_CTL or PATH)")
    parser.add_argument("--json", action="store_true", help="Print the full machine-readable report")
    args = parser.parse_args(argv)
    output = report(args.ctl)
    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("Horizon IDE preflight:", output["status"])
        if output["launch_api"]:
            print("Launch API:", output["launch_api"]["launch_api"])
        if output["error"]:
            print(output["error"]["code"] + ": " + output["error"]["message"], file=sys.stderr)
        print("Actual game load: NOT TESTED; playable one-window viewport: NOT TESTED")
    return 0 if output["status"] == "compatible_for_preview" else 1


if __name__ == "__main__":
    raise SystemExit(main())

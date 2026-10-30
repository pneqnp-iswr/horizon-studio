"""Assemble inspectable evidence from a pinned, genuinely executed Horizon validator.

Does not prove that Horizon game client loaded the mod.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
import re
import sys


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def attest(checker: Path, checker_revision: str, official_result: Path) -> dict:
    if not re.fullmatch(r"[a-f0-9]{40}", checker_revision):
        raise ValueError("Checker revision must be a pinned 40-character commit SHA")
    if not checker.is_file():
        raise ValueError("Official checker executable not found")
    data = json.loads(official_result.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Validator evidence must be a JSON object")
    if data.get("stage") != "official" or data.get("ok") is not True:
        raise ValueError("Official checker did not report a passing result")
    if data.get("declared_validator_revision") != checker_revision:
        raise ValueError("Evidence was generated for a different declared revision")
    if data.get("exit_code") != 0:
        raise ValueError("Official checker exited unsuccessfully")
    report = data.get("report")
    if not isinstance(report, dict) or report.get("ok") is not True:
        raise ValueError("Missing official checker success report")
    facts = report.get("report")
    if not isinstance(facts, dict) or facts.get("sha256") != data.get("sha256"):
        raise ValueError("Package digest not corroborated by official checker")
    if facts.get("size") != data.get("size") or facts.get("kind") != "mod":
        raise ValueError("Package kind or size does not match official evidence")
    command = data.get("command")
    if not isinstance(command, list) or not command or Path(command[0]).resolve() != checker.resolve():
        raise ValueError("Evidence command does not match the checked executable")
    return {
        "schema": "horizon-studio.official-compat/1",
        "stage": "official",
        "passed": True,
        "engine_source_repo": "https://github.com/horizon-rust/horizon",
        "declared_checkout_sha": checker_revision,
        "checker_binary_sha256": digest(checker),
        "checked_mod_sha256": data["sha256"],
        "checked_mod_bytes": data["size"],
        "checker_report": facts,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "in_game_tested": False,
        "notes": "Checkout revision verified by CI; no game-client execution. "
                 "Binary digest identifies this CI-built checker.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Attest a successful official Horizon check")
    parser.add_argument("--checker", type=Path, required=True)
    parser.add_argument("--checker-revision", required=True)
    parser.add_argument("--official-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        proof = attest(args.checker, args.checker_revision, args.official_result)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Official attestation FAILED: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Official check evidence written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

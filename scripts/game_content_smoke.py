"""Opt-in, evidence-gated game CONTENT-LOAD probe for Horizon Studio.

This is NOT a gameplay demonstration, nor does it download or license Horizon.
The user explicitly provides an authorized local game executable and data folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from horizon_cli import load_project
from studio import hmod_zip


CONTENT_LOG = re.compile(r"Horizon: content from ([0-9]+) mod\(s\) in ([^\r\n]+)")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def authorized_fixture(project: dict, package: bytes, evidence: dict) -> bool:
    """Ensure the exact package received a successful official static check."""
    if not isinstance(evidence, dict) or evidence.get("stage") != "official" or evidence.get("ok") is not True:
        return False
    if evidence.get("exit_code") != 0:
        return False
    facts = (evidence.get("report") or {}).get("report")
    if not isinstance(facts, dict):
        return False
    return (facts.get("sha256") == sha256(package)
            and evidence.get("sha256") == sha256(package)
            and evidence.get("size") == len(package)
            and facts.get("size") == len(package)
            and facts.get("kind") == "mod"
            and facts.get("api") == "0.2"
            and facts.get("id") == project.get("id"))


def assess_content_load(log: str, project_id: str, workdir: Path, exit_code: int | None,
                        timed_out: bool) -> dict:
    """Require genuine mod resource files under the resource root named by game logs.

    A generic '1 mod loaded' line alone is insufficient to establish the
    specific Studio mod was loaded. This does not exercise gameplay behavior.
    """
    missing = f"Horizon: mod {project_id} content not loaded:"
    if missing in log:
        return {"ok": False, "status": "rejected", "reason": "Game rejected the Studio mod's content"}
    if timed_out:
        return {"ok": False, "status": "indeterminate", "reason": "Game launch timed out"}
    if exit_code != 0:
        return {"ok": False, "status": "failed", "reason": f"Game process exited with code {exit_code}"}
    for found in CONTENT_LOG.finditer(log):
        if int(found.group(1)) < 1:
            continue
        root = Path(found.group(2).strip())
        if not root.is_absolute():
            root = workdir / root
        # Only a controlled workspace/installed game is readable; no copying
        # resources and no assumptions about broader game installation paths.
        try:
            target = root.resolve() / "data" / project_id
            if target.is_dir() and any(target.rglob("*.json")):
                return {"ok": True, "status": "content_loaded",
                        "reason": "Game load log and generated namespace files corroborated"}
        except OSError:
            pass
    return {"ok": False, "status": "indeterminate",
            "reason": "No corroborated game resource-root log and namespace content files"}


def smoke(game: Path, project_path: Path, official_evidence: Path, workdir: Path,
          game_log: Path, timeout: int, confirmed: bool) -> dict:
    """Run the game only after explicit authorization and matching official evidence."""
    if not confirmed:
        raise ValueError("Explicit --confirm-authorized is required before executing a game")
    if not 10 <= timeout <= 3600:
        raise ValueError("Game startup timeout must be 10..3600 seconds")
    if not game.is_file() or not workdir.is_dir():
        raise ValueError("An existing game executable and game working directory are required")
    project = load_project(project_path)
    package = hmod_zip(project)
    evidence = json.loads(official_evidence.read_text(encoding="utf-8"))
    if not authorized_fixture(project, package, evidence):
        raise ValueError("The exact package has no matching successful official .hmod check evidence")
    before = None
    if game_log.exists():
        stat = game_log.stat()
        before = (stat.st_mtime_ns, stat.st_size)
    with tempfile.TemporaryDirectory(prefix="horizon-studio-game-smoke-") as temporary:
        archive = Path(temporary) / (project["id"] + ".hmod")
        archive.write_bytes(package)
        argv = [str(game.resolve()), "--dev-mod", str(archive)]
        timed_out = False
        started = time.time_ns()
        try:
            completed = subprocess.run(argv, cwd=workdir, capture_output=True, text=True,
                                       errors="replace", timeout=timeout, check=False,
                                       stdin=subprocess.DEVNULL)
            exit_code = completed.returncode
            captured = (completed.stdout or "") + "\n" + (completed.stderr or "")
        except subprocess.TimeoutExpired as exc:
            exit_code = None
            timed_out = True
            captured = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            captured += "\n"
            captured += (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        if game_log.is_file():
            current = game_log.stat()
            if ((current.st_mtime_ns, current.st_size) != before and current.st_mtime_ns >= started):
                # Log is local evidence only, not uploaded automatically.
                captured += "\n" + game_log.read_text(encoding="utf-8", errors="replace")[-2_000_000:]
        assessed = assess_content_load(captured, project["id"], workdir, exit_code, timed_out)
        return {
            "schema": "horizon-studio.game-content-smoke/1",
            "stage": "game_content_load",
            **assessed,
            "game_executable_sha256": hashlib.sha256(game.read_bytes()).hexdigest(),
            "mod_id": project["id"],
            "mod_sha256": sha256(package),
            "official_evidence_sha256": hashlib.sha256(official_evidence.read_bytes()).hexdigest(),
            "game_exit_code": exit_code,
            "game_timed_out": timed_out,
            "in_game_behavior_verified": False,
            "gameplay_or_rendering_verified": False,
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Opt-in real-game CONTENT LOAD probe; never automatic")
    parser.add_argument("--game", type=Path, required=True, help="Authorized local Horizon executable")
    parser.add_argument("--project", type=Path, required=True, help="Horizon Studio project")
    parser.add_argument("--official-evidence", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True, help="Existing game working directory")
    parser.add_argument("--game-log", type=Path, required=True, help="Actual game's latest.log path")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-authorized", action="store_true")
    args = parser.parse_args(argv)
    try:
        proof = smoke(args.game, args.project, args.official_evidence, args.workdir,
                      args.game_log, args.timeout, args.confirm_authorized)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"Game content smoke FAIL: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Game content smoke: {proof['status']} — {proof['reason']}")
    print(f"Evidence: {args.output}")
    return 0 if proof["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

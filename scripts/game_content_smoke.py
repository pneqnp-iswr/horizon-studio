"""Opt-in, evidence-gated game CONTENT-LOAD probe for Horizon Studio.

This is NOT a gameplay demonstration, nor does it download or license Horizon.
The user explicitly provides an authorized local game executable and data folder.

Launch contract, read from the Horizon client source at the audited revision
d2186eb9aa022a64a8b26e6989a04e44fba99ee7 (re-check when the engine moves):

* ``--dev-mod PATH`` loads a content mod that is always on (game.rs).
* ``--home DIR`` sends the log to ``DIR/logs/latest.log`` (main.rs, logging.rs);
  Horizon's own messages are also printed on stderr.
* ``--frames N`` ends the run after N frames, ``--timeout-seconds S`` bounds a
  frame-limited run, ``--smoke-report PATH`` writes a JSON report with an
  ``error`` field on exit (game.rs ``write_report``).
* ``game/mods.rs`` logs ``Horizon: content from N mod(s) in <root>`` after it
  built ``<cwd>/.horizon-cache/mod-content``, and
  ``Horizon: mod <id> content not loaded: <reason>`` when it refused a mod.
* ``mod_content::build`` copies every mod file into that root byte for byte,
  except merged tag JSON and the ``data/<mod-id>/horizon/`` declarations.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from horizon_cli import load_project  # noqa: E402
from studio import hmod_zip  # noqa: E402

AUDITED_ENGINE_SHA = "d2186eb9aa022a64a8b26e6989a04e44fba99ee7"
CONTENT_LOG = re.compile(r"Horizon: content from ([0-9]+) mod\(s\) in ([^\r\n]+)")
MAX_LOG_CHARS = 2_000_000
# Time the harness allows on top of the game's own --timeout-seconds before
# it stops the process itself (startup, report writing, shutdown).
KILL_GRACE_SECONDS = 60


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


def verbatim_files(package: bytes, mod_id: str) -> dict[str, bytes]:
    """Package files the game copies unchanged into its content resource root."""
    declarations = f"data/{mod_id}/horizon/"
    result = {}
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        for name in archive.namelist():
            if name.endswith("/") or not name.startswith(("assets/", "data/")):
                continue
            if name.startswith(declarations):
                continue
            if name.startswith("data/") and "/tags/" in name and name.endswith(".json"):
                continue
            result[name] = archive.read(name)
    return result


def _compare_root(root: Path, expected: dict[str, bytes]) -> tuple[int, list[str]]:
    matched, problems = 0, []
    for name, content in sorted(expected.items()):
        try:
            if (root / name).read_bytes() == content:
                matched += 1
            else:
                problems.append(f"{name}: different bytes")
        except OSError:
            problems.append(f"{name}: missing")
    return matched, problems


def assess_content_load(log: str, project_id: str, workdir: Path, expected: dict[str, bytes],
                        exit_code: int | None, timed_out: bool, report: dict | None) -> dict:
    """Classify one game run from its log, exit status, smoke report and resource root.

    ``content_loaded`` needs the game's own content line AND every file it
    should have copied from this exact package, byte for byte, under the root
    that line names. It says nothing about gameplay or rendering.
    """
    if f"Horizon: mod {project_id} content not loaded:" in log:
        return {"ok": False, "status": "rejected", "reason": "Game refused the Studio mod's content"}
    if timed_out:
        return {"ok": False, "status": "indeterminate",
                "reason": "Game did not exit within the harness time limit"}
    if exit_code != 0:
        detail = report.get("error") if isinstance(report, dict) else None
        return {"ok": False, "status": "failed",
                "reason": f"Game process exited with code {exit_code}" + (f": {detail}" if detail else "")}
    if not isinstance(report, dict):
        return {"ok": False, "status": "indeterminate",
                "reason": "Game wrote no readable --smoke-report; a clean run cannot be confirmed"}
    if report.get("error"):
        return {"ok": False, "status": "failed", "reason": f"Game reported an error: {report['error']}"}
    if not expected:
        return {"ok": False, "status": "indeterminate",
                "reason": "Package has no files the game copies verbatim; nothing to corroborate"}
    best = None
    for found in CONTENT_LOG.finditer(log):
        if int(found.group(1)) < 1:
            continue
        root = Path(found.group(2).strip())
        if not root.is_absolute():
            root = workdir / root
        matched, problems = _compare_root(root, expected)
        if not problems:
            return {"ok": True, "status": "content_loaded", "resource_root": str(root),
                    "corroborated_files": matched,
                    "reason": "Game content line and byte-identical mod files in its resource root"}
        if best is None or matched > best[0]:
            best = (matched, problems, root)
    if best is None:
        return {"ok": False, "status": "indeterminate",
                "reason": "Game log has no 'Horizon: content from N mod(s)' line"}
    matched, problems, root = best
    return {"ok": False, "status": "indeterminate", "resource_root": str(root),
            "corroborated_files": matched,
            "reason": f"{len(problems)} of {len(expected)} mod files not found unchanged in the resource root",
            "problems": problems[:20]}


def _text(stream) -> str:
    if isinstance(stream, bytes):
        return stream.decode("utf-8", errors="replace")
    return stream or ""


def smoke(game: Path, project_path: Path, official_evidence: Path, workdir: Path, *,
          frames: int = 300, timeout: int = 300, resources: Path | None = None,
          confirmed: bool = False) -> dict:
    """Run the game only after explicit authorization and matching official evidence."""
    if not confirmed:
        raise ValueError("Explicit --confirm-authorized is required before executing a game")
    if not 10 <= timeout <= 3600:
        raise ValueError("Game timeout must be 10..3600 seconds")
    if not 1 <= frames <= 1_000_000:
        raise ValueError("Frame count must be 1..1000000")
    if not game.is_file() or not workdir.is_dir():
        raise ValueError("An existing game executable and game working directory are required")
    if resources is not None and not resources.is_dir():
        raise ValueError("--resources must be an existing prepared-resources folder")
    project = load_project(project_path)
    package = hmod_zip(project)
    evidence_bytes = official_evidence.read_bytes()
    evidence = json.loads(evidence_bytes.decode("utf-8"))
    if not authorized_fixture(project, package, evidence):
        raise ValueError("The exact package has no matching successful official .hmod check evidence")
    with tempfile.TemporaryDirectory(prefix="horizon-studio-game-smoke-") as temporary:
        folder = Path(temporary)
        archive = folder / (project["id"] + ".hmod")
        archive.write_bytes(package)
        home = folder / "home"
        report_path = folder / "smoke-report.json"
        argv = [str(game.resolve()), "--dev-mod", str(archive), "--home", str(home),
                "--frames", str(frames), "--timeout-seconds", str(timeout),
                "--smoke-report", str(report_path)]
        if resources is not None:
            argv += ["--resources", str(resources.resolve())]
        timed_out = False
        try:
            completed = subprocess.run(argv, cwd=workdir, capture_output=True, text=True,
                                       errors="replace", timeout=timeout + KILL_GRACE_SECONDS,
                                       check=False, stdin=subprocess.DEVNULL)
            exit_code = completed.returncode
            captured = _text(completed.stdout) + "\n" + _text(completed.stderr)
        except subprocess.TimeoutExpired as exc:
            exit_code = None
            timed_out = True
            captured = _text(exc.stdout) + "\n" + _text(exc.stderr)
        log_file = home / "logs" / "latest.log"
        if log_file.is_file():
            # Local evidence only; never uploaded automatically.
            captured += "\n" + log_file.read_text(encoding="utf-8", errors="replace")[-MAX_LOG_CHARS:]
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            report = None
        expected = verbatim_files(package, project["id"])
        assessed = assess_content_load(captured, project["id"], workdir, expected,
                                       exit_code, timed_out, report)
        return {
            "schema": "horizon-studio.game-content-smoke/2",
            "stage": "game_content_load",
            **assessed,
            "command": argv[:1] + ["--dev-mod", "<mod>.hmod", "--home", "<temporary>", "--frames", str(frames),
                                   "--timeout-seconds", str(timeout), "--smoke-report", "<temporary>"]
                       + (["--resources", str(resources.resolve())] if resources is not None else []),
            "launch_contract_engine_sha": AUDITED_ENGINE_SHA,
            "game_executable_sha256": sha256(game.read_bytes()),
            "mod_id": project["id"],
            "mod_sha256": sha256(package),
            "official_evidence_sha256": sha256(evidence_bytes),
            "game_exit_code": exit_code,
            "game_timed_out": timed_out,
            "game_smoke_report": report if isinstance(report, dict) else None,
            "in_game_behavior_verified": False,
            "gameplay_or_rendering_verified": False,
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Opt-in real-game CONTENT LOAD probe; never automatic")
    parser.add_argument("--game", type=Path, required=True, help="Authorized local horizon-client executable")
    parser.add_argument("--project", type=Path, required=True, help="Horizon Studio project")
    parser.add_argument("--official-evidence", type=Path, required=True,
                        help="JSON written by 'horizon_cli.py verify --evidence' for the same project")
    parser.add_argument("--workdir", type=Path, required=True,
                        help="Existing game working directory (the game builds .horizon-cache here)")
    parser.add_argument("--resources", type=Path, help="Prepared resources folder, if not the game's default")
    parser.add_argument("--frames", type=int, default=300, help="Frames before the game exits by itself")
    parser.add_argument("--timeout", type=int, default=300, help="Game's own --timeout-seconds (10..3600)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-authorized", action="store_true")
    args = parser.parse_args(argv)
    try:
        proof = smoke(args.game, args.project, args.official_evidence, args.workdir,
                      frames=args.frames, timeout=args.timeout, resources=args.resources,
                      confirmed=args.confirm_authorized)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Game content smoke FAIL: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Game content smoke: {proof['status']} — {proof['reason']}")
    print(f"Evidence: {args.output}")
    return 0 if proof["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

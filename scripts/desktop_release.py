#!/usr/bin/env python3
"""Release candidates for the Horizon Studio desktop application (stdlib only).

    desktop_release.py manifest --version X --commit SHA --installer PATH --portable-zip PATH
                                --gate NAME=RESULT ... --smoke DIR --signing PATH --out PATH
    desktop_release.py checksums --dist DIR FILE ...
    desktop_release.py verify --dist DIR --manifest PATH

The desktop build is a preview until the gates in docs/adr/0002-desktop-shell.md pass. This script
never publishes anything: it records what one CI run built and proved, and `release_ready` stays
false while any parity gate is missing. The released product remains the verified 0.7 EXE
(scripts/release.py, windows-release.yml).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release import ReleaseError, SEMVER, SHA1, checksums, sha256_file  # noqa: E402

SCHEMA = "horizon-studio.desktop-manifest/1"
SHELL = "HorizonStudio.exe"
CORE = "core/horizon-studio-core.exe"
# Proven in the run that builds the candidate; every one must succeed for a manifest to exist.
BUILD_GATES = ("rust-tests", "core-smoke", "portable-smoke", "zip-launch", "install-uninstall", "desktop-e2e")
# docs/adr/0002-desktop-shell.md: all must hold before a desktop build may replace the 0.7 EXE.
PARITY_GATES = {
    "desktop-e2e": "Every 0.7 workflow passes on the shell's own window (desktop E2E on Windows)",
    "release-pipeline": "windows-release.yml builds, gates and publishes the desktop artifacts with API verification",
    "signing-decision": "A recorded code-signing decision the installer can state honestly",
    "migration-note": "A user-visible note on moving from the 0.7 EXE",
}
SIGNATURE_STATES = {"Valid", "NotSigned", "HashMismatch", "NotTrusted", "UnknownError", "NotSupportedFileFormat", "Incompatible"}
PORTABLE_NOTE = (f"Portable folder in a ZIP: extract the whole archive and run {SHELL}; it needs the core/ folder "
                 "next to it. It is not a single-file executable.")


def _artifact(path: Path, kind: str) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ReleaseError(f"Missing {kind} {path}")
    return {"name": path.name, "kind": kind, "size": path.stat().st_size, "sha256": sha256_file(path)}


def portable_contents(path: Path) -> dict:
    """Checks the portable ZIP's layout and returns what it holds."""
    with zipfile.ZipFile(path) as archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        tops = {name.split("/", 1)[0] for name in names}
        if len(tops) != 1:
            raise ReleaseError(f"The portable ZIP must hold one folder, found {sorted(tops)}")
        top = tops.pop()
        for required in (SHELL, CORE):
            if f"{top}/{required}" not in names:
                raise ReleaseError(f"The portable ZIP has no {required}")
        bad = [name for name in names if name.startswith("/") or ".." in name.split("/") or "\\" in name]
        if bad:
            raise ReleaseError(f"Unsafe paths in the portable ZIP: {bad[:3]}")
        return {"folder": top, "files": len(names),
                "uncompressed_size": sum(info.file_size for info in archive.infolist())}


def smoke_results(folder: Path) -> list[dict]:
    """The packaged smoke runs of this build (scripts/desktop_probe.py metrics)."""
    runs = []
    for path in sorted(Path(folder).glob("*.metrics.json")):
        metrics = json.loads(path.read_text(encoding="utf-8"))
        report = metrics.get("report") or {}
        shell = report.get("shell") or {}
        if shell.get("test_build"):
            raise ReleaseError(f"{path.name}: a test build (cargo feature e2e) was smoke-tested as a package")
        if metrics.get("ok") is not True:
            raise ReleaseError(f"{path.name}: smoke run failed")
        timings = report.get("timings_ms") or {}
        runs.append({"label": metrics["label"], "editor_ready_ms": timings.get("editor_ready"),
                     "core_stop_ms": timings.get("core_stop"), "window": report.get("window"),
                     "tree_rss_mb": (metrics.get("memory") or {}).get("total_rss_mb")})
    if not runs:
        raise ReleaseError("No packaged smoke runs were recorded")
    return runs


def signing_status(report: dict, names: list[str]) -> dict:
    """Authenticode status per file, from Get-AuthenticodeSignature. Never claims more than it says."""
    files = {}
    for name in names:
        status = (report.get(name) or {}).get("status")
        if status not in SIGNATURE_STATES:
            raise ReleaseError(f"No Authenticode status recorded for {name}")
        files[name] = status
    if all(status == "Valid" for status in files.values()):
        overall = "signed"
    elif all(status == "NotSigned" for status in files.values()):
        overall = "unsigned"
    else:
        overall = "mixed"
    return {"overall": overall, "files": files}


def build_manifest(version: str, commit: str, installer: Path, portable_zip: Path, gates: dict[str, str],
                   smoke: list[dict], signing: dict, parity: dict[str, bool]) -> dict:
    if not SEMVER.fullmatch(version):
        raise ReleaseError(f"Invalid version {version!r}")
    if not SHA1.fullmatch(commit):
        raise ReleaseError("Commit must be a full 40-character SHA")
    missing = [gate for gate in BUILD_GATES if gates.get(gate) != "success"]
    if missing:
        raise ReleaseError(f"Build gates did not all succeed: {missing}")
    unknown = sorted(set(parity) - set(PARITY_GATES))
    if unknown:
        raise ReleaseError(f"Unknown parity gates {unknown}")
    portable = _artifact(portable_zip, "portable-zip")
    portable["contents"] = portable_contents(portable_zip)
    portable["note"] = PORTABLE_NOTE
    parity_state = {gate: {"passed": bool(parity.get(gate)), "requirement": text} for gate, text in PARITY_GATES.items()}
    ready = all(item["passed"] for item in parity_state.values()) and signing["overall"] in ("signed", "unsigned")
    return {
        "schema": SCHEMA,
        "channel": "preview",
        "base_version": version,
        "build": f"preview-{commit[:7]}",
        "git_commit": commit,
        "built_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "artifacts": [_artifact(installer, "nsis-installer"), portable],
        "gates": dict(sorted(gates.items())),
        "smoke": smoke,
        "signing": signing,
        "parity": parity_state,
        "release_ready": ready,
        "limitations": [
            "Preview build: the released product is the verified 0.7 EXE until every parity gate passes.",
            "Unsigned builds make Windows SmartScreen warn; compare SHA-256 with SHA256SUMS.txt."
            if signing["overall"] != "signed" else "Signed with Authenticode; verify the publisher in the file properties.",
            "Loading Studio mods in the Horizon game has not been verified (HS-002).",
        ],
    }


def verify(dist: Path, manifest_path: Path) -> list[str]:
    """Problems that make the files in `dist` differ from the manifest and SHA256SUMS.txt (empty when exact)."""
    dist = Path(dist)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    problems = []
    if manifest.get("schema") != SCHEMA:
        problems.append(f"Unexpected manifest schema {manifest.get('schema')!r}")
    sums_path = dist / "SHA256SUMS.txt"
    sums = {}
    if sums_path.is_file():
        for line in sums_path.read_text(encoding="ascii").splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
            if not match:
                problems.append(f"Malformed checksum line {line!r}")
                continue
            sums[match.group(2)] = match.group(1)
    else:
        problems.append("SHA256SUMS.txt is missing")
    for item in manifest.get("artifacts", []):
        path = dist / item["name"]
        if not path.is_file():
            problems.append(f"{item['name']} is missing")
            continue
        actual = sha256_file(path)
        if actual != item["sha256"] or path.stat().st_size != item["size"]:
            problems.append(f"{item['name']} differs from the manifest")
        if sums.get(item["name"]) != actual:
            problems.append(f"{item['name']} differs from SHA256SUMS.txt")
        if item["kind"] == "portable-zip":
            try:
                portable_contents(path)
            except (ReleaseError, zipfile.BadZipFile) as exc:
                problems.append(str(exc))
    if manifest_path.name in sums and sums[manifest_path.name] != sha256_file(manifest_path):
        problems.append(f"{manifest_path.name} differs from SHA256SUMS.txt")
    if manifest.get("release_ready") and not all(g.get("passed") for g in manifest.get("parity", {}).values()):
        problems.append("release_ready is set while a parity gate has not passed")
    if manifest.get("signing", {}).get("overall") == "signed" and any(
            status != "Valid" for status in manifest["signing"].get("files", {}).values()):
        problems.append("Signing is claimed for files without a valid signature")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Horizon Studio desktop release candidates (never publishes)")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("manifest")
    for flag in ("--version", "--commit"):
        p.add_argument(flag, required=True)
    for flag in ("--installer", "--portable-zip", "--smoke", "--signing", "--out"):
        p.add_argument(flag, type=Path, required=True)
    p.add_argument("--gate", action="append", default=[], help="NAME=RESULT proven in this run")
    p.add_argument("--parity", action="append", default=[], help="a parity gate (ADR 0002) that has passed")
    p = sub.add_parser("checksums"); p.add_argument("--dist", type=Path, required=True); p.add_argument("files", nargs="+")
    p = sub.add_parser("verify"); p.add_argument("--dist", type=Path, required=True); p.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "manifest":
            gates = dict(item.split("=", 1) for item in args.gate)
            report = json.loads(args.signing.read_text(encoding="utf-8"))
            signing = signing_status(report, [args.installer.name, SHELL, CORE])
            manifest = build_manifest(args.version, args.commit, args.installer, args.portable_zip, gates,
                                      smoke_results(args.smoke), signing, {name: True for name in args.parity})
            args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(manifest, indent=2))
        elif args.command == "checksums":
            text = checksums(args.dist, args.files)
            (args.dist / "SHA256SUMS.txt").write_text(text, encoding="ascii", newline="\n")
            print(text, end="")
        else:
            problems = verify(args.dist, args.manifest)
            if problems:
                raise ReleaseError("; ".join(problems))
            print(f"{args.dist}: every artifact matches {args.manifest.name} and SHA256SUMS.txt")
    except (ReleaseError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"DESKTOP RELEASE GATE FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

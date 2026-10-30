#!/usr/bin/env python3
"""Release gates and GitHub publication for Horizon Studio Windows builds (stdlib only).

    release.py check-notes  --version X --notes FILE
    release.py manifest     --version X --exe PATH --commit SHA --tag vX --gate NAME=RESULT ... --smoke-report PATH --out PATH
    release.py checksums    --dist DIR FILE ...
    release.py publish      --repo OWNER/NAME --version X --commit SHA --dist DIR --notes FILE
    release.py verify       --repo OWNER/NAME --version X [--commit SHA] [--legacy]
    release.py repair-notes --repo OWNER/NAME --version X --notes FILE

Rules (docs/RELEASING.md): a release is created as a draft, every asset is uploaded and
re-read through the API, and only then published. Published assets and tags are never
replaced, moved or deleted; any mismatch stops the run with an explanation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

SEMVER = re.compile(r"\d+\.\d+\.\d+")
SHA1 = re.compile(r"[0-9a-f]{40}")


class ReleaseError(RuntimeError):
    pass


def exe_name(version: str) -> str:
    return f"HorizonStudio-{version}-Windows-x64.exe"


def is_legacy(version: str) -> bool:
    """Releases before 0.7.0 were published without build-manifest.json."""
    return tuple(int(part) for part in version.split(".")) < (0, 7, 0)


def asset_names(version: str, legacy: bool = False) -> tuple[str, ...]:
    """Assets every release carries; releases before 0.7.0 had no build manifest."""
    return (exe_name(version), "SHA256SUMS.txt") + (() if legacy else ("build-manifest.json",))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# -- release notes ---------------------------------------------------------------

def check_notes(text: str, version: str) -> list[str]:
    """Problems that would publish another version's notes (empty when consistent)."""
    problems = []
    first = text.lstrip("﻿").splitlines()[0] if text.strip() else ""
    if not first.startswith(f"# Horizon Studio {version} "):
        problems.append(f"Title must start with '# Horizon Studio {version} ', found {first[:60]!r}")
    for found in sorted(set(re.findall(r"HorizonStudio-(\d+\.\d+\.\d+)-Windows", text)) - {version}):
        problems.append(f"Mentions the executable of version {found}")
    for found in sorted(set(re.findall(r"Horizon Studio (\d+\.\d+\.\d+)", text)) - {version}):
        problems.append(f"Mentions Horizon Studio {found}")
    if exe_name(version) not in text:
        problems.append(f"Does not name the executable {exe_name(version)}")
    return problems


# -- build outputs -----------------------------------------------------------------

def build_manifest(version: str, exe: Path, commit: str, tag: str, gates: dict[str, str],
                   smoke: dict | None) -> dict:
    """Provenance for one build, assembled from the files and results of this run."""
    if not SEMVER.fullmatch(version):
        raise ReleaseError(f"Invalid version {version!r}")
    if tag != f"v{version}":
        raise ReleaseError(f"Tag {tag} does not match version {version}")
    if not SHA1.fullmatch(commit):
        raise ReleaseError("Commit must be a full 40-character SHA")
    if Path(exe).name != exe_name(version) or not Path(exe).is_file():
        raise ReleaseError(f"Expected built executable {exe_name(version)}")
    failed = {name: result for name, result in gates.items() if result != "success"}
    if not gates or failed:
        raise ReleaseError(f"Release gates did not all succeed: {failed or 'none recorded'}")
    if not isinstance(smoke, dict) or smoke.get("ok") is not True or smoke.get("version") != version:
        raise ReleaseError("Frozen smoke test report is missing, failed or for another version")
    try:
        pyinstaller = importlib.metadata.version("pyinstaller")
    except importlib.metadata.PackageNotFoundError:
        pyinstaller = None
    return {
        "schema": "horizon-studio.build-manifest/1",
        "app_version": version,
        "git_tag": tag,
        "git_commit": commit,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "pyinstaller": pyinstaller,
        "executable": {"name": Path(exe).name, "size": Path(exe).stat().st_size, "sha256": sha256_file(exe)},
        "built_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "gates": dict(sorted(gates.items())),
        "smoke_test": smoke.get("checks", {}),
        "signing": "unsigned",
        "limitations": [
            "Unsigned: Windows SmartScreen may warn; compare SHA-256 with SHA256SUMS.txt.",
            "Loading Studio mods in the Horizon game has not been verified (HS-002).",
            "Official static checks cover the bundled examples only.",
        ],
    }


def checksums(dist: Path, names: list[str]) -> str:
    return "".join(f"{sha256_file(Path(dist) / name)}  {name}\n" for name in names)


# -- GitHub API --------------------------------------------------------------------

class GitHub:
    """Minimal GitHub REST client (GITHUB_TOKEN); tests replace it with a double."""

    def __init__(self, repo: str, token: str, api: str = "https://api.github.com"):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise ReleaseError("--repo must be OWNER/NAME")
        self.repo, self.token, self.api = repo, token, api

    def _call(self, method: str, url: str, body=None, content_type="application/json", accept="application/vnd.github+json"):
        data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": accept, "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": content_type} if data is not None else {})})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read()
                return json.loads(raw) if raw and accept.endswith("json") else raw
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise ReleaseError(f"{method} {url} failed: {exc.code} {exc.read()[:300]!r}") from exc

    def find_release(self, tag: str) -> dict | None:
        # The list (unlike /releases/tags/) also returns drafts left by an interrupted run.
        for release in self._call("GET", f"{self.api}/repos/{self.repo}/releases?per_page=100") or []:
            if release["tag_name"] == tag:
                return release
        return None

    def tag_commit(self, tag: str) -> str | None:
        ref = self._call("GET", f"{self.api}/repos/{self.repo}/git/ref/tags/{tag}")
        if not ref:
            return None
        target = ref["object"]
        if target["type"] == "tag":  # annotated tag
            target = self._call("GET", target["url"])["object"]
        return target["sha"]

    def create_draft(self, tag: str, commit: str, name: str, body: str, prerelease: bool) -> dict:
        return self._call("POST", f"{self.api}/repos/{self.repo}/releases", {
            "tag_name": tag, "target_commitish": commit, "name": name, "body": body,
            "draft": True, "prerelease": prerelease, "make_latest": "false"})

    def upload(self, release: dict, path: Path) -> dict:
        base = release["upload_url"].split("{", 1)[0]
        url = f"{base}?name={urllib.parse.quote(path.name)}"
        return self._call("POST", url, path.read_bytes(), content_type="application/octet-stream")

    def update(self, release: dict, **fields) -> dict:
        return self._call("PATCH", f"{self.api}/repos/{self.repo}/releases/{release['id']}", fields)

    def release(self, release_id: int) -> dict:
        return self._call("GET", f"{self.api}/repos/{self.repo}/releases/{release_id}")

    def asset_bytes(self, asset: dict) -> bytes:
        try:  # published assets of a public repository: no credentials needed
            with urllib.request.urlopen(asset["browser_download_url"], timeout=120) as response:
                return response.read()
        except urllib.error.URLError:
            pass

        class DropAuth(urllib.request.HTTPRedirectHandler):
            # The API redirects to storage on another host; never forward the token there.
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                new = super().redirect_request(req, fp, code, msg, headers, newurl)
                if new is not None:
                    new.headers.pop("Authorization", None)
                return new

        request = urllib.request.Request(asset["url"], headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/octet-stream"})
        with urllib.request.build_opener(DropAuth).open(request, timeout=120) as response:
            return response.read()

    def asset_sha256(self, asset: dict) -> str:
        digest = asset.get("digest") or ""
        return digest.split(":", 1)[1] if digest.startswith("sha256:") else sha256_bytes(self.asset_bytes(asset))

    def reachable(self, url: str) -> bool:
        # Storage URLs are signed for GET only (HEAD answers 401), so fetch the first byte.
        request = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status in (200, 206) and len(response.read()) >= 1
        except urllib.error.URLError:
            return False


# -- publication -------------------------------------------------------------------

def _consistent(gh, release: dict, version: str, legacy: bool) -> list[str]:
    """Problems with an existing release's assets, judged only from the release itself."""
    problems = []
    assets = {a["name"]: a for a in release.get("assets", [])}
    for name in asset_names(version, legacy):
        if name not in assets:
            problems.append(f"missing asset {name}")
        elif assets[name].get("state") != "uploaded":
            problems.append(f"asset {name} is {assets[name].get('state')}")
    if problems:
        return problems
    exe = assets[exe_name(version)]
    exe_sha = gh.asset_sha256(exe)
    sums = gh.asset_bytes(assets["SHA256SUMS.txt"]).decode("utf-8", "replace")
    if f"{exe_sha}  {exe['name']}" not in sums:
        problems.append("SHA256SUMS.txt does not match the published executable")
    if not legacy:
        manifest = json.loads(gh.asset_bytes(assets["build-manifest.json"]))
        if manifest.get("app_version") != version or manifest.get("executable", {}).get("sha256") != exe_sha:
            problems.append("build-manifest.json does not describe the published executable")
        if f"{gh.asset_sha256(assets['build-manifest.json'])}  build-manifest.json" not in sums:
            problems.append("SHA256SUMS.txt does not match build-manifest.json")
    return problems


def verify(gh, version: str, commit: str | None = None, legacy: bool | None = None) -> dict:
    """Read-only check of a published release through the API."""
    tag = f"v{version}"
    legacy = is_legacy(version) if legacy is None else legacy
    release = gh.find_release(tag)
    if release is None:
        raise ReleaseError(f"No GitHub release {tag}")
    if release.get("draft"):
        raise ReleaseError(f"Release {tag} is still a draft")
    problems = _consistent(gh, release, version, legacy)
    problems += [f"release notes: {p}" for p in check_notes(release.get("body") or "", version)]
    tag_sha = gh.tag_commit(tag)
    if tag_sha is None:
        problems.append(f"tag {tag} does not exist")
    elif commit and tag_sha != commit:
        problems.append(f"tag {tag} points to {tag_sha}, expected {commit}")
    exe = next((a for a in release["assets"] if a["name"] == exe_name(version)), None)
    if exe and not gh.reachable(exe["browser_download_url"]):
        problems.append("executable download URL is not reachable")
    if problems:
        raise ReleaseError(f"Release {tag} failed verification: " + "; ".join(problems))
    return {"tag": tag, "commit": tag_sha, "url": release["html_url"], "prerelease": release["prerelease"],
            "executable": {"name": exe["name"], "size": exe["size"], "sha256": gh.asset_sha256(exe),
                           "download": exe["browser_download_url"]}}


def publish(gh, version: str, commit: str, dist: Path, notes: str, prerelease: bool = True) -> dict:
    tag = f"v{version}"
    if not SHA1.fullmatch(commit):
        raise ReleaseError("Commit must be a full 40-character SHA")
    problems = check_notes(notes, version)
    if problems:
        raise ReleaseError("Release notes are not for this version: " + "; ".join(problems))
    local = {name: Path(dist) / name for name in asset_names(version)}
    for path in local.values():
        if not path.is_file():
            raise ReleaseError(f"Build output {path.name} is missing")
    tag_sha = gh.tag_commit(tag)
    if tag_sha and tag_sha != commit:
        raise ReleaseError(f"Tag {tag} already points to {tag_sha}, not {commit}; tags are never moved")
    release = gh.find_release(tag)
    if release and not release.get("draft") and not _consistent(gh, release, version, legacy=False):
        result = verify(gh, version, commit)
        result["status"] = "already verified"  # an earlier run published it; never replace assets
        return result
    if release and not release.get("draft"):
        raise ReleaseError(f"Published release {tag} is incomplete or inconsistent "
                           f"({'; '.join(_consistent(gh, release, version, legacy=False))}); "
                           "published releases are not repaired automatically - see docs/RELEASING.md")
    if release is None:
        release = gh.create_draft(tag, commit, f"Horizon Studio {tag} — Windows", notes, prerelease)
    elif release.get("target_commitish") != commit:
        raise ReleaseError(f"Draft release {tag} targets {release.get('target_commitish')}, not {commit}")
    existing = {a["name"]: a for a in release.get("assets", [])}
    for name, path in local.items():
        if name in existing:
            if gh.asset_sha256(existing[name]) != sha256_file(path):
                raise ReleaseError(f"Draft already holds a different {name}; resolve the draft manually")
            continue
        gh.upload(release, path)
    release = gh.release(release["id"])
    uploaded = {a["name"]: a for a in release["assets"]}
    for name, path in local.items():
        asset = uploaded.get(name)
        if not asset or asset.get("state") != "uploaded" or asset["size"] != path.stat().st_size \
                or gh.asset_sha256(asset) != sha256_file(path):
            raise ReleaseError(f"Uploaded {name} does not match the build output; the release stays a draft")
    gh.update(release, draft=False, body=notes, make_latest="false")
    result = verify(gh, version, commit)
    result["status"] = "published"
    return result


def repair_notes(gh, version: str, notes: str) -> dict:
    """Replace only the description of an existing release; assets and tag are untouched."""
    problems = check_notes(notes, version)
    if problems:
        raise ReleaseError("Notes are not for this version: " + "; ".join(problems))
    release = gh.find_release(f"v{version}")
    if release is None or release.get("draft"):
        raise ReleaseError(f"No published release v{version} to repair")
    if exe_name(version) not in {a["name"] for a in release.get("assets", [])}:
        raise ReleaseError(f"Release v{version} has no {exe_name(version)}; refusing to describe a missing binary")
    gh.update(release, body=notes)
    return {"tag": f"v{version}", "status": "notes updated", "url": release["html_url"]}


# -- command line ------------------------------------------------------------------

def _github(args) -> GitHub:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise ReleaseError("GITHUB_TOKEN is required")
    return GitHub(args.repo, token)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Horizon Studio release gates and publication")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check-notes"); p.add_argument("--version", required=True); p.add_argument("--notes", type=Path, required=True)
    p = sub.add_parser("manifest")
    for flag in ("--version", "--commit", "--tag"):
        p.add_argument(flag, required=True)
    p.add_argument("--exe", type=Path, required=True); p.add_argument("--smoke-report", type=Path, required=True)
    p.add_argument("--gate", action="append", default=[], help="NAME=RESULT from the workflow's needs context")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("checksums"); p.add_argument("--dist", type=Path, required=True); p.add_argument("files", nargs="+")
    for name in ("publish", "verify", "repair-notes"):
        p = sub.add_parser(name)
        p.add_argument("--repo", required=True); p.add_argument("--version", required=True)
        if name == "publish":
            p.add_argument("--commit", required=True); p.add_argument("--dist", type=Path, required=True)
        if name in ("publish", "repair-notes"):
            p.add_argument("--notes", type=Path, required=True)
        if name == "verify":
            p.add_argument("--commit"); p.add_argument("--legacy", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not SEMVER.fullmatch(args.version if hasattr(args, 'version') else '0.0.0'):
            raise ReleaseError('--version must look like 1.2.3')
        if args.command == "check-notes":
            problems = check_notes(args.notes.read_text(encoding="utf-8"), args.version)
            if problems:
                raise ReleaseError("; ".join(problems))
            print(f"{args.notes} describes {args.version}")
        elif args.command == "manifest":
            gates = dict(item.split("=", 1) for item in args.gate)
            smoke = json.loads(args.smoke_report.read_text(encoding="utf-8")) if args.smoke_report.is_file() else None
            manifest = build_manifest(args.version, args.exe, args.commit, args.tag, gates, smoke)
            args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(manifest, indent=2))
        elif args.command == "checksums":
            text = checksums(args.dist, args.files)
            (args.dist / "SHA256SUMS.txt").write_text(text, encoding="ascii", newline="\n")
            print(text, end="")
        else:
            gh = _github(args)
            if args.command == "publish":
                result = publish(gh, args.version, args.commit, args.dist, args.notes.read_text(encoding="utf-8"))
            elif args.command == "verify":
                result = verify(gh, args.version, args.commit, True if args.legacy else None)
            else:
                result = repair_notes(gh, args.version, args.notes.read_text(encoding="utf-8"))
            print(json.dumps(result, indent=2))
    except (ReleaseError, OSError, ValueError) as exc:
        print(f"RELEASE GATE FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

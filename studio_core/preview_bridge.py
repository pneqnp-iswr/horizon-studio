"""HS-023: the Preview Bridge — a Studio project in a real Horizon client, through ``horizon-ctl``.

What it drives is upstream's own agent-control tool (``horizon-ctl``, shipped beside the game; audited
at Horizon ``3c1d4b39``: ``launch``, ``wait-for``, ``state``, ``screenshot``, ``give``, ``inventory``,
``logs``, ``quit``; ``--socket PATH``; the game's ``--launch-api`` reply). Rules:

* Only an installation the person already has: ``horizon-ctl`` and the ``horizon-client`` beside it.
  Studio never downloads game files, never handles accounts or sessions and never bypasses the
  launcher's ownership gate.
* Nothing starts without the person's explicit approval of that session.
* Every session is isolated: a fresh game folder (its own test world) and home folder under
  ``~/.horizon-studio/preview/<id>``; personal saves are never opened or modified.
* The Studio package goes in with the game's ``--dev-mod``; it is a content ``.hmod`` (no code runs).
* A screenshot proves a frame was drawn, nothing more. ``game-load`` is recorded only when the
  game itself confirms the project's content (a project item given and found in the inventory).
* The session always ends: ``quit`` (saves and exits), then the game's process is stopped if needed.

It works without AI; ``horizon_cli.py preview`` and the AI Creator (HS-024) use the same class.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import uuid
from pathlib import Path

EVIDENCE_SCHEMA = "horizon-studio.preview-evidence/1"
LAUNCH_API_MAJOR = 0
LAUNCH_API_MIN = (0, 1, 0)
REQUIRED_OPTIONS = ("--game-dir", "--home")
WORLD = "StudioPreview"
PNG = b"\x89PNG\r\n\x1a\n"
CLIENT = "horizon-client.exe" if sys.platform == "win32" else "horizon-client"
CTL = "horizon-ctl.exe" if sys.platform == "win32" else "horizon-ctl"


class BridgeError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def discover(explicit: str | None = None, environ=os.environ) -> dict:
    """Finds ``horizon-ctl`` (explicit path, ``HORIZON_CTL``, then ``PATH``) and the game beside it."""
    candidates = [explicit, environ.get("HORIZON_CTL"), shutil.which(CTL)]
    ctl = next((Path(c) for c in candidates if c and Path(c).is_file()), None)
    if ctl is None:
        raise BridgeError("NOT_FOUND", "horizon-ctl was not found: install Horizon with its launcher, then point Studio "
                                       "at horizon-ctl (it ships beside the game) or set HORIZON_CTL")
    game = ctl.with_name(CLIENT)
    return {"ctl": [str(ctl.resolve())], "game": [str(game.resolve())] if game.is_file() else None}


def _version_tuple(text: str):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(text))
    return tuple(int(part) for part in match.groups()) if match else None


class PreviewBridge:
    """One isolated preview session. ``ctl`` and ``game`` are command prefixes (tests use fakes)."""

    def __init__(self, ctl: list[str], game: list[str] | None, root: Path | None = None, *,
                 run=subprocess.run, timeout: float = 300):
        self.ctl, self.game, self.run_process, self.timeout = list(ctl), (list(game) if game else None), run, timeout
        self.root = Path(root) if root else Path.home() / ".horizon-studio" / "preview"
        self.session: dict | None = None
        self.launch_api: dict | None = None
        self.log: list[dict] = []

    # -- plumbing ---------------------------------------------------------------
    def _call(self, args: list[str], timeout: float | None = None) -> dict:
        if self.session is None:
            raise BridgeError("NO_SESSION", "No preview session is running")
        command = [*self.ctl, "--socket", self.session["socket"], *args]
        try:
            done = self.run_process(command, capture_output=True, text=True, timeout=timeout or self.timeout,
                                    env={**os.environ, "HORIZON_CONTROL": self.session["socket"],
                                         "HORIZON_HOME": self.session["home"]})
        except subprocess.TimeoutExpired as exc:
            raise BridgeError("TIMEOUT", f"horizon-ctl {args[0]} timed out") from exc
        line = (done.stdout or "").strip().splitlines()[-1:] or ["{}"]
        try:
            reply = json.loads(line[0])
        except json.JSONDecodeError:
            reply = {"error": (done.stdout or done.stderr or "").strip()[:500] or "no reply"}
        self.log.append({"command": args[0], "exit": done.returncode, "at": _now()})
        if done.returncode != 0 or (isinstance(reply, dict) and "error" in reply):
            message = reply.get("error") if isinstance(reply, dict) else str(reply)
            raise BridgeError({1: "GAME_ERROR", 2: "USAGE", 3: "UNREACHABLE"}.get(done.returncode, "GAME_ERROR"),
                              f"horizon-ctl {args[0]}: {message}")
        return reply

    # -- steps ------------------------------------------------------------------
    def check_version(self) -> dict:
        """The game's Launch API must be 0.x (at least 0.1.0) and take every option Studio passes."""
        if not self.game:
            raise BridgeError("VERSION_UNKNOWN", "No horizon-client beside horizon-ctl, so its Launch API cannot be "
                                                 "checked; Studio does not start a game it cannot check")
        done = self.run_process([*self.game, "--launch-api"], capture_output=True, text=True, timeout=60)
        try:
            reply = json.loads(done.stdout)
        except (json.JSONDecodeError, TypeError):
            raise BridgeError("VERSION_UNKNOWN", "horizon-client --launch-api did not answer with JSON") from None
        version = _version_tuple(reply.get("launch_api", ""))
        if version is None or version[0] != LAUNCH_API_MAJOR or version < LAUNCH_API_MIN:
            raise BridgeError("VERSION_UNSUPPORTED", f"Launch API {reply.get('launch_api')!r} is not supported "
                                                     f"(Studio speaks {LAUNCH_API_MAJOR}.x from {'.'.join(map(str, LAUNCH_API_MIN))})")
        offered = {option.get("name") for option in reply.get("options", []) if isinstance(option, dict)}
        missing = [name for name in REQUIRED_OPTIONS if name not in offered]
        if missing:
            raise BridgeError("VERSION_UNSUPPORTED", f"This build does not take {', '.join(missing)}")
        self.launch_api = {"launch_api": reply["launch_api"], "horizon": reply.get("horizon"),
                           "minecraft": reply.get("minecraft")}
        return self.launch_api

    def start(self, hmod: Path, *, approved: bool, seed: int = 0, width: int = 1280, height: int = 720) -> dict:
        """Launches the game in a fresh isolated folder with the package and waits until the world is loaded."""
        if not approved:
            raise BridgeError("APPROVAL_REQUIRED", "Starting Horizon needs the person's approval for this session")
        hmod = Path(hmod)
        if not hmod.is_file() or hmod.suffix != ".hmod":
            raise BridgeError("BAD_PACKAGE", f"{hmod} is not a .hmod package")
        if self.launch_api is None:
            self.check_version()
        session_id = uuid.uuid4().hex[:12]
        folder = self.root / session_id
        game_dir, home = folder / "game", folder / "home"
        game_dir.mkdir(parents=True)
        home.mkdir()
        socket = folder / ("horizon-control.json" if sys.platform == "win32" else "control.sock")
        self.session = {"id": session_id, "folder": str(folder), "game_dir": str(game_dir), "home": str(home),
                        "socket": str(socket), "hmod": str(hmod), "hmod_sha256": _sha256(hmod), "seed": seed,
                        "started_at": _now(), "pid": None, "ended": False}
        args = ["launch", "--world", WORLD, "--seed", str(seed), "--wait"]
        if self.game:
            args += ["--game", self.game[-1]]
        # Everything after the launch options goes to the game (horizon-ctl launch).
        args += ["--game-dir", str(game_dir), "--home", str(home), "--width", str(width), "--height", str(height),
                 "--offscreen", "--dev-mod", str(hmod)]
        try:
            launched = self._call(args)
            self.session["pid"] = launched.get("pid")
            self.session["version"] = launched.get("version")
            self._call(["wait-for", "loaded", "--timeout", "120"], timeout=150)
        except BridgeError:
            self.end()
            raise
        return dict(self.session)

    def state(self) -> dict:
        return self._call(["state"])

    def screenshot(self, path: Path) -> dict:
        path = Path(path)
        self._call(["screenshot", str(path)])
        data = path.read_bytes() if path.is_file() else b""
        if not data.startswith(PNG):
            raise BridgeError("BAD_SCREENSHOT", "The game did not write a PNG")
        return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def verify_items(self, items: list[str]) -> dict:
        """Asks the game itself whether the project's items exist: give one, then look in the inventory."""
        found = {}
        for item in items:
            try:
                self._call(["give", item, "1"])
                inventory = json.dumps(self._call(["inventory"]))
                found[item] = item in inventory
            except BridgeError as exc:
                found[item] = False
                self.log.append({"command": "verify", "item": item, "refused": exc.code})
        return {"checked": list(items), "found": found, "all_found": bool(items) and all(found.values())}

    def end(self) -> dict:
        """Saves and quits; stops the game's process if it does not exit. Safe to call twice."""
        if self.session is None or self.session["ended"]:
            return {"ended": True}
        outcome = "quit"
        try:
            self._call(["quit"], timeout=60)
        except BridgeError as exc:
            outcome = f"quit failed ({exc.code})"
            pid = self.session.get("pid")
            if isinstance(pid, int) and pid > 0:
                try:
                    os.kill(pid, signal.SIGTERM)  # TerminateProcess on Windows
                    outcome += "; stopped the game process"
                except OSError:
                    outcome += "; the game process was already gone"
        self.session["ended"] = True
        self.session["ended_at"] = _now()
        self.session["end"] = outcome
        return {"ended": True, "how": outcome}

    def evidence(self, *, screenshot: dict | None, state: dict | None, content: dict | None) -> dict:
        """What this session established, at the level it actually reached."""
        if self.session is None:
            raise BridgeError("NO_SESSION", "No preview session to report")
        level = "game-load" if content and content.get("all_found") else "launched"
        return {
            "schema": EVIDENCE_SCHEMA,
            "level": level,
            "launch_api": self.launch_api,
            "horizon_version": self.session.get("version"),
            "session": {k: self.session.get(k) for k in ("id", "game_dir", "home", "seed", "started_at", "ended_at", "end")},
            "world": WORLD,
            "package": {"path": self.session["hmod"], "sha256": self.session["hmod_sha256"]},
            "screenshot": screenshot,
            "state": {k: state.get(k) for k in ("screen", "dimension", "game_mode", "position") if k in state} if state else None,
            "content": content,
            "notes": [
                "A screenshot shows that a frame was drawn; it is not, by itself, proof that the mod loaded.",
                "game-load is recorded only when the game confirms the project's items." if level == "game-load"
                else "The project's content was not confirmed by the game in this session.",
                "Gameplay, events and multiplayer were not verified.",
            ],
            "commands": self.log,
        }

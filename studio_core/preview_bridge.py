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
  game itself confirms the project's content (PB-001, :meth:`PreviewBridge.verify_items`): an item
  the package defines, given once, appears in a real inventory slot under its exact id with exactly
  one more than before, the slot totals agree with the game's own counts, and a control item the
  package does not define is refused by the same game. ``give``'s own reply is never trusted.
* The session always ends: ``quit`` (saves and exits), then the game's process is stopped if needed.

It works without AI; ``horizon_cli.py preview`` and the AI Creator (HS-024) use the same class.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
import tomllib
import uuid
import zipfile
from pathlib import Path

from studio_core.storage import atomic_write_bytes

EVIDENCE_SCHEMA = "horizon-studio.preview-evidence/1"
LAUNCH_API_MAJOR = 0
LAUNCH_API_MIN = (0, 1, 0)
REQUIRED_OPTIONS = ("--game-dir", "--home")
WORLD = "StudioPreview"
PNG = b"\x89PNG\r\n\x1a\n"
CLIENT = "horizon-client.exe" if sys.platform == "win32" else "horizon-client"
CTL = "horizon-ctl.exe" if sys.platform == "win32" else "horizon-ctl"
ITEM_ID = re.compile(r"[a-z0-9_.-]+:[a-z0-9_./-]+")
# The inventory reply of horizon-ctl at 3c1d4b39 (crates/horizon-client/src/game/agent.rs, inventory_value):
# hotbar 0-8, main 9-35, armor 500-503, offhand 504, plus carried and counts.
INVENTORY_GROUPS = (("hotbar", range(0, 9)), ("main", range(9, 36)), ("armor", range(500, 504)))
MAX_CHECKED_ITEMS = 16


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


def _is_png(data: bytes) -> bool:
    """A PNG signature followed by an IHDR chunk with a non-zero size."""
    if len(data) < 33 or not data.startswith(PNG) or data[12:16] != b"IHDR":
        return False
    width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    return width > 0 and height > 0


def package_items(hmod: Path) -> tuple[str, set[str]]:
    """The mod id and the item ids a content package defines (item model definitions and Horizon item
    data); the only ids the Preview Bridge will ask the game to confirm."""
    try:
        with zipfile.ZipFile(hmod) as archive:
            names = archive.namelist()
            manifest = tomllib.loads(archive.read("horizon-mod.toml").decode("utf-8"))
    except (OSError, KeyError, zipfile.BadZipFile, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise BridgeError("BAD_PACKAGE", f"{hmod} is not a readable .hmod package: {exc}") from None
    mod_id = manifest.get("id")
    if not isinstance(mod_id, str) or not re.fullmatch(r"[a-z0-9_.-]+", mod_id):
        raise BridgeError("BAD_PACKAGE", "The package manifest has no valid id")
    items = set()
    for prefix in (f"assets/{mod_id}/items/", f"data/{mod_id}/horizon/item/"):
        for name in names:
            if name.startswith(prefix) and name.endswith(".json") and "/" not in name[len(prefix):]:
                items.add(f"{mod_id}:{name[len(prefix):-5]}")
    return mod_id, items


def _stack(value, where: str):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise BridgeError("MALFORMED_INVENTORY", f"{where} is not a stack")
    item, count = value.get("item"), value.get("count")
    if item is None:
        return None
    if not isinstance(item, str) or not ITEM_ID.fullmatch(item):
        raise BridgeError("MALFORMED_INVENTORY", f"{where} has no valid item id")
    if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= 2**31 - 1:
        raise BridgeError("MALFORMED_INVENTORY", f"{where} has no valid count")
    return item, count


def parse_inventory(reply) -> dict:
    """``{"slots": {slot: (item, count)}, "carried": (item, count) | None, "counts": {...}}`` from the
    upstream inventory reply. Missing groups, wrong lengths, slots out of place, duplicates and counts
    that disagree with the slots are refused: an ambiguous answer never confirms anything."""
    if not isinstance(reply, dict):
        raise BridgeError("MALFORMED_INVENTORY", "The inventory is not a JSON object")
    slots: dict[int, tuple[str, int]] = {}
    expected = [(group, list(numbers)) for group, numbers in INVENTORY_GROUPS] + [("offhand", [504])]
    for group, numbers in expected:
        entries = reply.get(group)
        entries = [entries] if group == "offhand" else entries
        if not isinstance(entries, list) or len(entries) != len(numbers):
            raise BridgeError("MALFORMED_INVENTORY", f"inventory.{group} must have {len(numbers)} slots")
        for number, entry in zip(numbers, entries):
            if not isinstance(entry, dict) or entry.get("slot") != number or isinstance(entry.get("slot"), bool):
                raise BridgeError("MALFORMED_INVENTORY", f"inventory.{group}: expected slot {number}")
            stack = _stack(entry, f"slot {number}")
            if stack is not None:
                slots[number] = stack
    carried = _stack(reply.get("carried"), "the carried stack")
    counts = reply.get("counts")
    if not isinstance(counts, dict) or not all(isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)
                                               for k, v in counts.items()):
        raise BridgeError("MALFORMED_INVENTORY", "inventory.counts must map item ids to numbers")
    sums: dict[str, int] = {}
    for item, count in [*slots.values(), *([carried] if carried else [])]:
        sums[item] = sums.get(item, 0) + count
    if {k: v for k, v in counts.items() if v} != sums:
        raise BridgeError("AMBIGUOUS_INVENTORY", "The game's item counts disagree with its slots")
    return {"slots": slots, "carried": carried, "counts": sums}


def total(inventory: dict, item: str) -> int:
    return inventory["counts"].get(item, 0)


def _version_tuple(text: str):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(text))
    return tuple(int(part) for part in match.groups()) if match else None


class PreviewBridge:
    """One isolated preview session. ``ctl`` and ``game`` are command prefixes (tests use fakes)."""

    def __init__(self, ctl: list[str], game: list[str] | None, root: Path | None = None, *,
                 run=subprocess.run, timeout: float = 300, sleep=time.sleep):
        self.ctl, self.game, self.run_process, self.timeout = list(ctl), (list(game) if game else None), run, timeout
        self.sleep = sleep
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
                              f"horizon-ctl {args[0]}: {str(message)[:500]}")
        if not isinstance(reply, dict):
            raise BridgeError("MALFORMED_REPLY", f"horizon-ctl {args[0]} did not answer with a JSON object")
        return reply

    # -- steps ------------------------------------------------------------------
    def check_version(self) -> dict:
        """The game's Launch API must be 0.x (at least 0.1.0) and take every option Studio passes."""
        if not self.game:
            raise BridgeError("VERSION_UNKNOWN", "No horizon-client beside horizon-ctl, so its Launch API cannot be "
                                                 "checked; Studio does not start a game it cannot check")
        try:
            done = self.run_process([*self.game, "--launch-api"], capture_output=True, text=True, timeout=60)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise BridgeError("VERSION_UNKNOWN", f"horizon-client --launch-api did not answer: {exc}") from None
        try:
            reply = json.loads(done.stdout)
        except (json.JSONDecodeError, TypeError):
            raise BridgeError("VERSION_UNKNOWN", "horizon-client --launch-api did not answer with JSON") from None
        if not isinstance(reply, dict) or done.returncode != 0:
            raise BridgeError("VERSION_UNKNOWN", "horizon-client --launch-api did not answer with a JSON object")
        version = _version_tuple(reply.get("launch_api", ""))
        if version is None or version[0] != LAUNCH_API_MAJOR or version < LAUNCH_API_MIN:
            raise BridgeError("VERSION_UNSUPPORTED", f"Launch API {reply.get('launch_api')!r} is not supported "
                                                     f"(Studio speaks {LAUNCH_API_MAJOR}.x from {'.'.join(map(str, LAUNCH_API_MIN))})")
        options = reply.get("options")
        if not isinstance(options, list):
            raise BridgeError("VERSION_UNSUPPORTED", "The Launch API reply lists no options")
        offered = {option.get("name") for option in options if isinstance(option, dict)}
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
        if self.session is not None and not self.session["ended"]:
            raise BridgeError("SESSION_ACTIVE", "A preview session is still running; end it first")
        hmod = Path(hmod)
        if not hmod.is_file() or hmod.suffix != ".hmod":
            raise BridgeError("BAD_PACKAGE", f"{hmod} is not a .hmod package")
        mod_id, items = package_items(hmod)
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
                        "mod_id": mod_id, "package_items": sorted(items), "approved_at": _now(),
                        "started_at": _now(), "pid": None, "ended": False, "shots": 0}
        args = ["launch", "--world", WORLD, "--seed", str(seed), "--wait"]
        if self.game:
            args += ["--game", self.game[-1]]
        # Everything after the launch options goes to the game (horizon-ctl launch).
        args += ["--game-dir", str(game_dir), "--home", str(home), "--width", str(width), "--height", str(height),
                 "--offscreen", "--dev-mod", str(hmod)]
        try:
            launched = self._call(args)
            pid = launched.get("pid")
            self.session["pid"] = pid if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0 else None
            version = launched.get("version")
            self.session["version"] = version if isinstance(version, str) else None
            self._call(["wait-for", "loaded", "--timeout", "120"], timeout=150)
        except BridgeError:
            self.end()
            raise
        return dict(self.session)

    def state(self) -> dict:
        return self._call(["state"])

    def screenshot(self, copy_to: Path | None = None) -> dict:
        """The game writes the next frame into the session folder (never a caller's path); a valid PNG
        may then be copied to ``copy_to``. A partial or invalid file is removed, not reported."""
        if self.session is None:
            raise BridgeError("NO_SESSION", "No preview session is running")
        self.session["shots"] += 1
        shot = Path(self.session["folder"]) / "screenshots" / f"shot-{self.session['shots']:03d}.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._call(["screenshot", str(shot)])
            data = shot.read_bytes() if shot.is_file() else b""
            if not _is_png(data):
                raise BridgeError("BAD_SCREENSHOT", "The game did not write a PNG")
        except BridgeError:
            shot.unlink(missing_ok=True)
            raise
        result = {"path": str(shot), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if copy_to is not None:
            atomic_write_bytes(Path(copy_to), data)
            result["copy"] = str(Path(copy_to))
        return result

    def inventory(self) -> dict:
        """The player's inventory, checked against the upstream schema; anything else is refused."""
        return parse_inventory(self._call(["inventory"]))

    def verify_items(self, items: list[str] | None = None, *, attempts: int = 20, interval: float = 0.25) -> dict:
        """PB-001: asks the game itself whether the package's items exist.

        For each item: read the inventory, ``give`` one, then read the inventory again (polling,
        because a single-player give runs on the integrated server and reaches the client later)
        until exactly one more of that exact id sits in real slots and the game's own counts agree.
        A control item the package does not define must be refused by ``give``; if the game accepts
        it, no item counts as confirmed. Items outside the package are never checked."""
        if self.session is None or self.session["ended"]:
            raise BridgeError("NO_SESSION", "No preview session is running")
        package = set(self.session["package_items"])
        wanted = list(dict.fromkeys(items if items is not None else sorted(package)[:MAX_CHECKED_ITEMS]))
        if len(wanted) > MAX_CHECKED_ITEMS:
            raise BridgeError("TOO_MANY_ITEMS", f"Check at most {MAX_CHECKED_ITEMS} items per session")
        control_id = f"{self.session['mod_id']}:studio_absent_{self.session['id']}"
        control = {"item": control_id, "refused": False}
        try:
            self._call(["give", control_id, "1"])
            control["reason"] = "the game accepted an item the package does not define"
        except BridgeError as exc:
            control["refused"] = exc.code == "GAME_ERROR"
            control["reason"] = exc.code
        checks = []
        for item in wanted:
            check = {"item": item, "in_package": item in package, "confirmed": False}
            checks.append(check)
            if not check["in_package"]:
                check["reason"] = "NOT_IN_PACKAGE"
                continue
            try:
                before = self.inventory()
                check["before"] = total(before, item)
                given = self._call(["give", item, "1"])
                check["give_reply"] = {k: given[k] for k in ("ok", "given") if k in given}
                for attempt in range(max(1, attempts)):
                    after = self.inventory()
                    now = total(after, item)
                    if now != check["before"]:
                        break
                    if attempt + 1 < attempts:
                        self.sleep(interval)
                check["after"] = now
                check["slots"] = [slot for slot, (name, _count) in sorted(after["slots"].items()) if name == item]
                if now - check["before"] != 1:
                    check["reason"] = "NOT_IN_INVENTORY" if now == check["before"] else "WRONG_QUANTITY"
                elif not check["slots"]:
                    check["reason"] = "NOT_IN_SLOTS"
                else:
                    check["confirmed"] = True
            except BridgeError as exc:
                check["reason"] = exc.code
                self.log.append({"command": "verify", "item": item, "refused": exc.code})
        confirmed = bool(checks) and control["refused"] and all(c["confirmed"] for c in checks)
        return {"checked": wanted, "found": {c["item"]: c["confirmed"] for c in checks}, "control": control,
                "checks": checks, "all_found": confirmed}

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
                owned = self.owns(pid)
                if owned is False:
                    outcome += "; the reported process is not this session's game, so it was not stopped"
                elif owned is None:
                    outcome += "; the game process was already gone"
                else:
                    try:
                        os.kill(pid, signal.SIGTERM)  # TerminateProcess on Windows
                        outcome += "; stopped the game process"
                    except OSError:
                        outcome += "; the game process was already gone"
        self.session["ended"] = True
        self.session["ended_at"] = _now()
        self.session["end"] = outcome
        return {"ended": True, "how": outcome}

    def owns(self, pid: int) -> bool | None:
        """Whether ``pid`` is still this session's game: its command line names this session's own
        game folder. ``None`` when no such process exists. Never stops a recycled process id."""
        game_dir = self.session["game_dir"] if self.session else None
        command = self.command_line(pid)
        if command is None:
            return None
        return bool(game_dir) and game_dir in command

    @staticmethod
    def command_line(pid: int) -> str | None:
        if sys.platform.startswith("linux"):
            try:
                return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
            except OSError:
                return None
        if sys.platform == "win32":
            query = f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine"
            args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", query]
        else:
            args = ["ps", "-p", str(int(pid)), "-o", "command="]
        try:
            done = subprocess.run(args, capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return done.stdout.strip() or None

    def evidence(self, *, screenshot: dict | None, state: dict | None, content: dict | None) -> dict:
        """What this session established, at the level it actually reached, bound to the package,
        the game build and this session."""
        if self.session is None:
            raise BridgeError("NO_SESSION", "No preview session to report")
        package = Path(self.session["hmod"])
        unchanged = not package.is_file() or _sha256(package) == self.session["hmod_sha256"]
        level = "game-load" if (content and content.get("all_found") is True and unchanged
                                and self.session.get("version") and self.launch_api) else "launched"
        binding = {"package_sha256": self.session["hmod_sha256"], "horizon_version": self.session.get("version"),
                   "launch_api": (self.launch_api or {}).get("launch_api"), "session": self.session["id"],
                   "world": WORLD, "seed": self.session["seed"]}
        record = {
            "schema": EVIDENCE_SCHEMA,
            "level": level,
            "binding": binding,
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
                "game-load is recorded only when the game confirms the package's items in real inventory slots "
                "and refuses a control item the package does not define." if level == "game-load"
                else "The project's content was not confirmed by the game in this session.",
                "Gameplay, events and multiplayer were not verified.",
            ] + ([] if unchanged else ["The package changed during the session, so nothing it showed counts."]),
            "commands": self.log,
        }
        record["digest"] = hashlib.sha256(json.dumps({k: record[k] for k in ("binding", "level", "content")},
                                                     sort_keys=True).encode("utf-8")).hexdigest()
        return record

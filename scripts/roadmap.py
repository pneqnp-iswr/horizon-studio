#!/usr/bin/env python3
"""Validate docs/roadmap/roadmap.json and render the roadmap images and tables from it.

    python scripts/roadmap.py           # regenerate SVGs and the marked Markdown sections
    python scripts/roadmap.py --check   # fail if the data is invalid or any output is stale

The JSON file is the single source of truth. Phase states are derived from
milestone states, and milestone states are only as strong as their evidence:
nothing here turns green because some unrelated CI job did.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pixelart import PALETTE as P, Canvas, hex_rgb  # noqa: E402

DATA = ROOT / "docs" / "roadmap" / "roadmap.json"
RELEASES = ROOT / "docs" / "releases" / "releases.json"
ASSETS = ROOT / "assets" / "roadmap"
REPO_URL = "https://github.com/pneqnp-iswr/horizon-studio/"
SCHEMA = "horizon-studio.roadmap/2"
PREVIOUS_SCHEMA = "horizon-studio.roadmap/1"

MILESTONE_STATUSES = ("done", "partial", "in_progress", "planned", "blocked")
VERIFICATION_STATUSES = ("verified", "in_progress", "blocked", "planned")
# desktop-smoke: the real desktop application started, reported ready and shut down cleanly in CI.
# desktop-e2e: functional scenarios drove the real desktop window (not a separate browser).
EVIDENCE_LEVELS = ("unit", "official-static", "browser-e2e", "desktop-smoke", "desktop-e2e", "game-load", "gameplay", "docs")
TRACKS = {"studio": "HS", "pixelchat": "PC"}
CONTRACT_STATUSES = ("available", "missing")
GOVERNANCE = ("summary", "summary_ru", "deliverable", "deliverable_ru")
ICONS = ("forge", "core", "editor", "nodes", "creature", "portal", "gear", "plug", "summit")
STARTED = ("done", "partial", "in_progress", "blocked")
LABELS = {
    "en": {"done": "Done", "partial": "Partially verified", "in_progress": "In progress", "planned": "Planned",
           "blocked": "Blocked", "verified": "Verified"},
    "ru": {"done": "Готово", "partial": "Частично проверено", "in_progress": "В работе", "planned": "Запланировано",
           "blocked": "Заблокировано", "verified": "Подтверждено"},
}


class RoadmapError(ValueError):
    pass


# -- validation ----------------------------------------------------------------

def _evidence_errors(where: str, items, require_level: bool) -> list[str]:
    errors = []
    if not isinstance(items, list):
        return [f"{where}: evidence must be a list"]
    for index, item in enumerate(items):
        label = f"{where}: evidence[{index}]"
        if not isinstance(item, dict) or not isinstance(item.get("ref"), str) or not item["ref"].strip():
            errors.append(f"{label} needs a non-empty ref")
            continue
        if require_level and item.get("level") not in EVIDENCE_LEVELS:
            errors.append(f"{label} has unsupported level {item.get('level')!r}")
        url = item.get("url")
        if not isinstance(url, str) or not url:
            errors.append(f"{label} needs a url")
        elif url.startswith("http"):
            if not url.startswith(REPO_URL):
                errors.append(f"{label} must link into {REPO_URL}")
        elif ".." in Path(url).parts or not (ROOT / url).is_file():
            errors.append(f"{label} points to missing file {url}")
    return errors


def validate(data) -> list[str]:
    """All problems found in the roadmap data (empty when valid)."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return [f"Expected a {SCHEMA} document"]
    errors = []
    if not isinstance(data.get("updated"), str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["updated"]):
        errors.append("updated must be a YYYY-MM-DD date")
    phases, milestones = data.get("phases"), data.get("milestones")
    if not isinstance(phases, list) or not phases or not isinstance(milestones, list):
        return errors + ["phases and milestones must be lists"]
    phase_ids = []
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict) or not isinstance(phase.get("id"), str) or not re.fullmatch(r"F\d", phase["id"]):
            errors.append(f"phases[{index}] needs an id like F0")
            continue
        if phase["id"] in phase_ids:
            errors.append(f"Duplicate phase {phase['id']}")
        phase_ids.append(phase["id"])
        for field in ("name", "name_ru", "summary", "summary_ru", "gate"):
            if not isinstance(phase.get(field), str) or not phase[field].strip():
                errors.append(f"Phase {phase['id']} needs {field}")
        if phase.get("icon") not in ICONS:
            errors.append(f"Phase {phase['id']} has unsupported icon {phase.get('icon')!r}")
    if phase_ids != sorted(phase_ids):
        errors.append("Phases must be listed in order")
    ids = {}
    for index, item in enumerate(milestones):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not re.fullmatch(r"(HS|PC)-\d{3}", item["id"]):
            errors.append(f"milestones[{index}] needs an id like HS-001 or PC-001")
            continue
        if item["id"] in ids:
            errors.append(f"Duplicate milestone {item['id']}")
        ids[item["id"]] = item
    for mid, item in ids.items():
        status = item.get("status")
        if status not in MILESTONE_STATUSES:
            errors.append(f"{mid}: unsupported status {status!r}")
            continue
        if item.get("phase") not in phase_ids:
            errors.append(f"{mid}: unknown phase {item.get('phase')!r}")
        for field in ("title", "title_ru"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{mid} needs {field}")
        deps = item.get("depends_on")
        if not isinstance(deps, list):
            errors.append(f"{mid}: depends_on must be a list")
            deps = []
        for dep in deps:
            if dep not in ids:
                errors.append(f"{mid}: depends on unknown milestone {dep!r}")
            elif dep == mid:
                errors.append(f"{mid}: depends on itself")
            elif status == "done" and ids[dep].get("status") != "done":
                errors.append(f"{mid} is done but its dependency {dep} is {ids[dep].get('status')}")
            elif status in ("in_progress", "partial") and ids[dep].get("status") in ("planned", "blocked"):
                errors.append(f"{mid} is {status} but its dependency {dep} has not started")
        evidence = item.get("evidence", [])
        errors += _evidence_errors(mid, evidence, require_level=True)
        if status in ("done", "partial") and not evidence:
            errors.append(f"{mid} is {status} without evidence")
        if status == "done" and isinstance(evidence, list) and all(
                isinstance(e, dict) and e.get("level") == "docs" for e in evidence):
            errors.append(f"{mid} is done with documentation-only evidence")
        if status == "partial" and not str(item.get("missing", "")).strip():
            errors.append(f"{mid} is partial but does not say what is missing")
        if status == "blocked" and not str(item.get("blocker", "")).strip():
            errors.append(f"{mid} is blocked without a blocker")
        if status in ("planned", "in_progress") and (item.get("missing") or item.get("blocker")):
            errors.append(f"{mid} is {status} but carries missing/blocker notes")
    errors += _governance_errors(data, ids)
    active = data.get("active_milestone")
    if active not in ids:
        errors.append(f"active_milestone {active!r} is not a milestone")
    elif ids[active].get("status") != "in_progress":
        errors.append(f"active_milestone {active} is not in_progress")
    current = data.get("current_phase")
    if current not in phase_ids:
        errors.append(f"current_phase {current!r} is not a phase")
    elif active in ids and ids[active].get("phase") != current:
        errors.append(f"active_milestone {active} is not in current_phase {current}")
    in_progress = sorted({m.get("phase") for m in ids.values() if m.get("status") == "in_progress"})
    if in_progress and in_progress != [current]:
        errors.append(f"Milestones are in progress outside the current phase: {in_progress}")
    for mid in data.get("next_milestones", []):
        if mid not in ids or ids[mid].get("status") != "planned":
            errors.append(f"next_milestones entry {mid!r} must be a planned milestone")
    levels = data.get("verification")
    if not isinstance(levels, list) or [v.get("level") for v in levels if isinstance(v, dict)] != [
            "unit", "official-static", "browser-e2e", "game-load", "gameplay"]:
        errors.append("verification must list unit, official-static, browser-e2e, game-load, gameplay in order")
    else:
        for level in levels:
            where = f"verification {level['level']}"
            if level.get("status") not in VERIFICATION_STATUSES:
                errors.append(f"{where}: unsupported status {level.get('status')!r}")
            for field in ("name", "name_ru", "detail", "detail_ru"):
                if not isinstance(level.get(field), str) or not level[field].strip():
                    errors.append(f"{where} needs {field}")
            errors += _evidence_errors(where, level.get("evidence", []), require_level=False)
            if level.get("status") == "verified" and not level.get("evidence"):
                errors.append(f"{where} is verified without evidence")
        ladder = [level.get("status") for level in levels]
        for lower, higher in zip(ladder, ladder[1:]):
            if higher == "verified" and lower != "verified":
                errors.append("A verification level cannot be verified while a lower level is not")
    errors += _showcase_errors(data, ids)
    return errors


def known_requirements(data: dict) -> dict[str, str]:
    """Capability or contract id -> 'buildable' (Studio builds it), 'engine' (an audited engine
    has it) or 'missing' (no audited engine has it). The strongest state across profiles wins."""
    from studio_core.capabilities import BUILDABLE, load_registry
    rank = {"missing": 0, "engine": 1, "buildable": 2}
    known: dict[str, str] = {}

    def note(name, state):
        if rank[state] >= rank.get(known.get(name, "missing"), 0):
            known[name] = state

    for profile in load_registry()["profiles"]:
        for name, entry in profile["capabilities"].items():
            note(name, "buildable" if entry["status"] == BUILDABLE else
                 "engine" if entry["status"] == "engine-only" else "missing")
    for contract in data.get("engine_contracts", []):
        if isinstance(contract, dict) and isinstance(contract.get("id"), str):
            note(contract["id"], "engine" if contract.get("status") == "available" else "missing")
    return known


def _cycle(ids: dict) -> list[str]:
    """One dependency cycle, if any, as a list of milestone ids."""
    state, stack = {}, []

    def visit(mid):
        state[mid] = "open"
        stack.append(mid)
        for dep in ids[mid].get("depends_on") or []:
            if dep not in ids:
                continue
            if state.get(dep) == "open":
                return stack[stack.index(dep):] + [dep]
            if dep not in state:
                found = visit(dep)
                if found:
                    return found
        state[mid] = "closed"
        stack.pop()
        return []

    for mid in ids:
        if mid not in state:
            found = visit(mid)
            if found:
                return found
    return []


def _governance_errors(data: dict, ids: dict) -> list[str]:
    errors = []
    contracts = data.get("engine_contracts")
    if not isinstance(contracts, list):
        return ["engine_contracts must be a list"]
    seen = set()
    for contract in contracts:
        cid = contract.get("id") if isinstance(contract, dict) else None
        if not isinstance(cid, str) or not cid or cid in seen:
            errors.append(f"engine contract {cid!r} needs a unique id")
            continue
        seen.add(cid)
        if contract.get("status") not in CONTRACT_STATUSES:
            errors.append(f"engine contract {cid}: status must be one of {', '.join(CONTRACT_STATUSES)}")
        for field in ("title", "title_ru", "note", "source"):
            if not isinstance(contract.get(field), str) or not contract[field].strip():
                errors.append(f"engine contract {cid} needs {field}")
    known = known_requirements(data)
    for mid, item in ids.items():
        track = item.get("track")
        if TRACKS.get(track) != mid[:2]:
            errors.append(f"{mid}: track must be {'studio' if mid.startswith('HS') else 'pixelchat'}")
        for field in GOVERNANCE:
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{mid} needs {field}")
        acceptance = item.get("acceptance")
        if not isinstance(acceptance, list) or not acceptance or not all(isinstance(a, str) and a.strip() for a in acceptance):
            errors.append(f"{mid} needs acceptance criteria")
        target = item.get("validation_target")
        if target not in EVIDENCE_LEVELS or target == "docs":
            errors.append(f"{mid}: validation_target must be an evidence level other than docs")
        ref = item.get("design_ref")
        if not isinstance(ref, str) or not ref or (not ref.startswith(REPO_URL) and not (ROOT / ref).is_file()):
            errors.append(f"{mid}: design_ref {ref!r} must be a repository file or link")
        if "issue" in item and (not isinstance(item["issue"], int) or item["issue"] < 1):
            errors.append(f"{mid}: issue must be a GitHub issue number")
        requirements = item.get("engine_requirements")
        if not isinstance(requirements, list):
            errors.append(f"{mid}: engine_requirements must be a list")
            requirements = []
        for name in requirements:
            if name not in known:
                errors.append(f"{mid}: unknown engine requirement {name!r} (not in the registry or engine_contracts)")
        # Contradictions: a finished milestone must show its target level and everything it needs must exist.
        if item.get("status") == "done":
            levels = {e.get("level") for e in item.get("evidence", []) if isinstance(e, dict)}
            if target and target not in levels:
                errors.append(f"{mid} is done without {target} evidence")
            for name in requirements:
                if known.get(name) == "missing":
                    errors.append(f"{mid} is done but needs {name}, which no audited engine provides")
    cycle = _cycle(ids)
    if cycle:
        errors.append("Dependency cycle: " + " -> ".join(cycle))
    return errors


def _showcase_errors(data: dict, ids: dict) -> list[str]:
    errors = []
    for show in data.get("showcases", []):
        sid = show.get("id", "")
        if not re.fullmatch(r"SC-\d{3}", sid):
            errors.append(f"showcase {sid!r} needs an id like SC-001")
        for field in ("name", "name_ru", "summary", "summary_ru"):
            if not isinstance(show.get(field), str) or not show[field].strip():
                errors.append(f"showcase {sid} needs {field}")
        for mid in show.get("milestones", []):
            if mid not in ids:
                errors.append(f"showcase {sid}: unknown milestone {mid}")
        levels = show.get("levels", [])
        if [lvl.get("level") for lvl in levels] != list(range(1, len(levels) + 1)) or not levels:
            errors.append(f"showcase {sid}: levels must be numbered 1..n")
        ladder = [lvl.get("status") for lvl in levels]
        for status in ladder:
            if status not in VERIFICATION_STATUSES:
                errors.append(f"showcase {sid}: unsupported level status {status!r}")
        for lower, higher in zip(ladder, ladder[1:]):
            if higher == "verified" and lower != "verified":
                errors.append(f"showcase {sid}: a level cannot be verified before the level below it")
    return errors


def upgrade(data: dict) -> dict:
    """roadmap/1 -> roadmap/2 structure. Governance fields stay empty, so the result is valid
    only once they are written (a v1 document never passes as v2 by accident)."""
    if data.get("schema") == SCHEMA:
        return data
    if data.get("schema") != PREVIOUS_SCHEMA:
        raise RoadmapError(f"Cannot upgrade {data.get('schema')!r}")
    out = json.loads(json.dumps(data))
    out["schema"] = SCHEMA
    out.setdefault("engine_contracts", [])
    out.setdefault("showcases", [])
    for item in out["milestones"]:
        item.setdefault("track", "pixelchat" if item["id"].startswith("PC-") else "studio")
        for field in GOVERNANCE:
            item.setdefault(field, "")
        item.setdefault("acceptance", [])
        item.setdefault("engine_requirements", [])
        item.setdefault("validation_target", "")
        item.setdefault("design_ref", "")
    return out


def dumps(data: dict) -> str:
    """The canonical file form (tests keep the committed file in it)."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def load(path: Path = DATA) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = validate(data)
    if problems:
        raise RoadmapError("; ".join(problems))
    return data


def milestones_of(data: dict, phase_id: str, track: str = "studio") -> list[dict]:
    """Milestones of a phase; the experimental PixelChat track is counted separately."""
    return [m for m in data["milestones"] if m["phase"] == phase_id and m.get("track", "studio") == track]


def phase_status(data: dict, phase_id: str) -> str:
    states = [m["status"] for m in milestones_of(data, phase_id)]
    if phase_id == data["current_phase"]:
        return "in_progress"
    if states and all(s == "done" for s in states):
        return "done"
    if any(s in STARTED for s in states):
        return "partial"
    return "planned"


# -- pixel icons ------------------------------------------------------------------

def _grey(color: str) -> str:
    r, g, b = hex_rgb(color)
    lum = 0.3 * r + 0.59 * g + 0.11 * b
    ramp = [P["stone0"], P["stone1"], P["stone2"], P["stone3"], P["stone4"]]
    return ramp[min(4, int(lum / 52))]


def icon(c: Canvas, kind: str, x: int, y: int, dim: bool):
    """Draw a 16x16 phase icon. ``dim`` renders it in stone tones (not started)."""
    def k(name: str) -> str:
        return _grey(P[name]) if dim else P[name]

    if kind == "forge":
        c.sprite(x, y, [
            "......y.........", ".....yYy........", "......y....y....", "..........yYy...",
            "...........y....", "..hhhhhhhhhhhh..", ".hssssssssssssh.", "..dssssssssssd..",
            "....dssssssd....", ".....dssssd.....", ".....dssssd.....", "....dssssssd....",
            "...dssssssssd...", "...dddddddddd...", "................", "................"],
            {"h": k("stone4"), "s": k("stone2"), "d": k("stone1"), "y": k("gold2"), "Y": k("gold3")})
    elif kind == "core":
        cube = [".ttt.", "tTTTt", "lTTTr", "llrrr", ".lrr."]
        for cx, cy in ((5, 1), (1, 9), (10, 9)):
            c.sprite(x + cx, y + cy, cube, {"t": k("cyan1"), "T": k("cyan2"), "l": k("cyan0"), "r": k("stone1")})
        c.line(x + 7, y + 6, x + 4, y + 9, k("gold2"))
        c.line(x + 8, y + 6, x + 11, y + 9, k("gold2"))
        c.line(x + 6, y + 12, x + 10, y + 12, k("gold2"))
    elif kind == "editor":
        c.sprite(x + 3, y + 4, [
            "....tt....", "..ttTTtt..", "ttTTTTTTtt", "lttTTTTttr", "llllttrrrr",
            "llllllrrrr", "llllllrrrr", ".llllrrrr.", "...llrr..."],
            {"t": k("cyan1"), "T": k("cyan2"), "l": k("cyan0"), "r": k("stone1")})
        c.line(x + 8, y + 9, x + 8, y + 1, k("moss3"))
        c.sprite(x + 7, y, [".g.", "ggg"], {"g": k("moss3")})
        c.line(x + 8, y + 9, x + 14, y + 12, k("ember"))
        c.line(x + 8, y + 9, x + 2, y + 12, k("gold2"))
        c.rect(x + 7, y + 8, 3, 3, k("ink"))
    elif kind == "nodes":
        for nx, ny, head in ((0, 2, "cyan1"), (10, 0, "gold1"), (9, 10, "moss2")):
            c.rect(x + nx, y + ny, 6, 5, k("stone2"))
            c.rect(x + nx, y + ny, 6, 1, k(head))
            c.frame(x + nx, y + ny, 6, 5, k("stone3"))
        c.line(x + 6, y + 4, x + 10, y + 2, k("cyan2"))
        c.line(x + 6, y + 5, x + 9, y + 12, k("cyan2"))
        c.set(x + 5, y + 4, k("gold2"))
        c.set(x + 5, y + 5, k("gold2"))
    elif kind == "creature":
        c.sprite(x, y + 3, [
            ".....gggggg.....", "...gGGGGGGGGg...", "..gGGGGGGGGGGg..", "..gGwwGGGGwwGg..",
            ".gGGwkGGGGwkGGg.", ".gGGGGGGGGGGGGg.", ".gGGGGGmmGGGGGg.", ".gGGGGGGGGGGGGg.",
            "..gggggggggggg.."], {"g": k("moss1"), "G": k("moss2"), "w": k("ink"), "k": k("void"), "m": k("moss0")})
        c.sprite(x + 11, y, [".r.r.", "rrrrr", ".rrr.", "..r.."], {"r": k("red")})
    elif kind == "portal":
        c.sprite(x + 2, y, [
            "..oooooooo..", ".oOvvvvvvOo.", "oOvVVcVVVvOo", "oOvVcVVcVvOo", "oOvVVVVVcvOo",
            "oOvcVVVcVvOo", "oOvVVcVVVvOo", "oOvVVVVcVvOo", "oOvvcVVVvvOo", "oOvvvvvvvvOo",
            "oooooooooooo"], {"o": k("stone1"), "O": k("stone3"), "v": k("violet1"), "V": k("violet0"),
                              "c": k("violet2")})
        c.rect(x, y + 12, 16, 2, k("moss2"))
        c.rect(x, y + 14, 16, 2, k("dirt1"))
        c.set(x + 15, y + 2, k("cyan3"))
        c.set(x, y + 5, k("gold2"))
    elif kind == "gear":
        for gy in range(16):
            for gx in range(16):
                d2 = (gx - 7.5) ** 2 + (gy - 7.5) ** 2
                tooth = (gx in (6, 7, 8, 9) and gy in (0, 1, 14, 15)) or (gy in (6, 7, 8, 9) and gx in (0, 1, 14, 15))
                if 2.5 ** 2 < d2 <= 5.6 ** 2 or tooth:
                    c.set(x + gx, y + gy, k("stone3") if gx + gy < 15 else k("stone2"))
        c.set(x + 5, y + 5, k("stone4"))
        c.line(x + 3, y + 12, x + 12, y + 3, k("gold1"), dash=2)
    elif kind == "plug":
        c.rect(x + 4, y + 3, 2, 4, k("stone4"))
        c.rect(x + 10, y + 3, 2, 4, k("stone4"))
        c.rect(x + 2, y + 6, 12, 6, k("gold1"))
        c.rect(x + 2, y + 6, 12, 1, k("gold2"))
        c.rect(x + 3, y + 8, 2, 2, k("gold0"))
        c.rect(x + 6, y + 12, 4, 2, k("stone2"))
        c.rect(x + 7, y + 14, 2, 2, k("cyan1"))
    elif kind == "summit":
        c.sprite(x, y + 4, [
            ".......s........", "......sSs.......", ".....sSSss...s..", "....sSSSsss.sSs.",
            "...sSSSSsssssSss", "..sSSSSsssssSsss", ".ssSSSsssssssss.", "ssssssssssssssss",
            "mmmmmmmmmmmmmmmm", "mmmmmmmmmmmmmmmm"], {"s": k("stone2"), "S": k("stone4"), "m": k("moss2")})
        c.rect(x + 7, y, 1, 5, k("stone4"))
        c.rect(x + 8, y, 4, 3, k("gold2"))


# -- images -------------------------------------------------------------------------

STATUS_COLORS = {"done": "gold2", "partial": "gold1", "in_progress": "cyan2", "planned": "stone2", "blocked": "red"}


def _check(c: Canvas, x: int, y: int, color: str):
    c.sprite(x, y, ["....#", "...#.", "#.#..", ".#..."], {"#": color})


def _cross(c: Canvas, x: int, y: int, color: str):
    c.sprite(x, y, ["#..#", ".##.", ".##.", "#..#"], {"#": color})


def _pip(c: Canvas, x: int, y: int, status: str):
    if status == "done":
        c.rect(x, y, 5, 5, P["gold2"])
        c.rect(x, y, 5, 1, P["gold3"])
    elif status == "partial":
        c.frame(x, y, 5, 5, P["gold1"])
        c.rect(x, y, 3, 5, P["gold1"])
    elif status == "in_progress":
        c.rect(x, y, 5, 5, P["cyan1"])
        c.rect(x + 1, y + 1, 3, 3, P["cyan3"])
    elif status == "blocked":
        c.rect(x, y, 5, 5, P["red"])
        c.rect(x + 2, y + 1, 1, 3, P["void"])
    else:
        c.frame(x, y, 5, 5, P["stone2"])


def _tile(c: Canvas, cx: int, cy: int, kind: str, status: str):
    x, y = cx - 11, cy - 11
    if status == "in_progress":
        for ring, color in ((3, P["cyan0"]), (2, P["cyan1"])):
            c.frame(x - ring, y - ring, 22 + ring * 2, 22 + ring * 2, color)
    c.rect(x, y, 22, 22, P["night2"])
    edge = {"done": P["gold2"], "partial": P["gold1"], "in_progress": P["cyan2"], "blocked": P["red"]}.get(
        status, P["stone2"])
    c.frame(x, y, 22, 22, edge)
    c.rect(x + 1, y + 1, 20, 1, P["stone1"] if status == "planned" else edge)
    icon(c, kind, x + 3, y + 3, dim=status == "planned")
    if status == "done":
        c.rect(x + 15, y - 3, 8, 7, P["night"])
        _check(c, x + 16, y - 2, P["gold2"])
    elif status == "partial":
        c.rect(x + 15, y - 3, 8, 7, P["night"])
        _pip(c, x + 17, y - 2, "partial")


def _centered(c: Canvas, cx: int, y: int, text: str, color: str):
    c.text(cx - Canvas.text_width(text) // 2, y, text, color)


def _backdrop(c: Canvas):
    for y in range(c.height):
        c.rect(0, y, c.width, 1, P["night"] if y < c.height // 2 else P["night2"])
    c.dither_band(0, c.height // 2 - 4, c.width, 8, P["night2"], 8)
    for i in range(70):
        x, y = (i * 97 + 31) % c.width, (i * 53 + 17) % c.height
        c.set(x, y, P["stone1"] if i % 5 else P["stone2"])
    c.frame(0, 0, c.width, c.height, P["stone1"])


def _wrap(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for word in text.upper().split(" "):
        if lines and Canvas.text_width(lines[-1] + " " + word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines


ROW_A, ROW_B = 80, 166
SLOTS = [(40, ROW_A), (115, ROW_A), (190, ROW_A), (265, ROW_A), (340, ROW_A),
         (340, ROW_B), (265, ROW_B), (190, ROW_B), (115, ROW_B)]


def render_overview(data: dict) -> Canvas:
    c = Canvas(400, 246)
    _backdrop(c)
    c.text(14, 10, "DEVELOPMENT JOURNEY", P["gold2"], scale=2, highlight=P["gold3"], shadow=P["void"])
    stamp = "UPDATED " + data["updated"]
    c.text(386 - Canvas.text_width(stamp), 14, stamp, P["faint"])
    x = 14
    for status, label in (("done", "DONE"), ("partial", "PARTIALLY VERIFIED"), ("in_progress", "IN PROGRESS"),
                          ("blocked", "BLOCKED"), ("planned", "PLANNED")):
        _pip(c, x, 32, status)
        c.text(x + 8, 31, label, P["muted"])
        x += Canvas.text_width(label) + 16
    c.rect(14, 43, 372, 1, P["stone1"])

    phases = data["phases"]
    if len(phases) > len(SLOTS):
        raise RoadmapError("The journey map has room for nine phases")
    states = [phase_status(data, p["id"]) for p in phases]
    # Road first, so tiles sit on top of it.
    points = []
    for index, slot in enumerate(SLOTS[:len(phases)]):
        points.append(slot)
        if index == 4:
            points += [(374, ROW_A), (374, ROW_B)]
    # A road segment is lit only between two started phases, so a later phase that started
    # early (F3 before F2) is not drawn as if the phases in between were passed.
    started = {SLOTS[i] for i, s in enumerate(states) if s != "planned"}
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        lit = (x0, y0) in started and ((x1, y1) in started or (x1, y1) not in SLOTS)
        if (x0, y0) not in SLOTS:  # the corner points of the turn inherit the previous segment
            lit = previous
        color = P["gold1"] if lit else P["stone1"]
        for offset in (-1, 0, 1):
            if y0 == y1:
                c.line(x0, y0 + offset, x1, y1 + offset, color, dash=0 if lit else 3)
            else:
                c.line(x0 + offset, y0, x1 + offset, y1, color, dash=0 if lit else 3)
        if lit:
            c.line(x0, y0, x1, y1, P["gold2"], dash=2)
        previous = lit
    for phase, state, (cx, cy) in zip(phases, states, SLOTS):
        _tile(c, cx, cy, phase["icon"], state)
        if state == "in_progress":
            c.sprite(cx - 3, cy - 33, [".ccc.", "cCCCc", "cCwCc", ".cCc.", "..c.."],
                     {"c": P["cyan1"], "C": P["cyan2"], "w": P["ink"]})
            c.text(cx + 5, cy - 32, "NOW", P["cyan2"])
        code_color = P["cyan2"] if state == "in_progress" else P["faint"] if state == "planned" else P["gold1"]
        _centered(c, cx, cy - 23, phase["id"], code_color)
        name_color = P["ink"] if state != "planned" else P["stone4"]
        for line_no, line in enumerate(_wrap(phase["name"], 68)[:2]):
            _centered(c, cx, cy + 15 + line_no * 9, line, name_color)
        items = milestones_of(data, phase["id"])
        if items:
            done = sum(1 for m in items if m["status"] == "done")
            width = len(items) * 6 - 1
            for i, item in enumerate(items):
                _pip(c, cx - width // 2 + i * 6, cy + 34, item["status"])
            _centered(c, cx, cy + 42, f"{done}/{len(items)} DONE", P["faint"] if state == "planned" else P["muted"])
        else:
            _centered(c, cx, cy + 35, "NO TICKETS YET", P["stone2"])

    # Verification ladder: each level is separate evidence; none implies the next.
    c.rect(14, 218, 372, 1, P["stone1"])
    chips = [(level["status"], level["name"].upper()) for level in data["verification"]]
    total = sum(Canvas.text_width(label) + 14 for _, label in chips) + 3 * (len(chips) - 1)
    x = 14 + (372 - total) // 2
    for status, label in chips:
        w = Canvas.text_width(label) + 14
        border = {"verified": P["gold2"], "in_progress": P["cyan2"], "blocked": P["red"]}.get(status, P["stone2"])
        c.rect(x, 225, w, 13, P["night"])
        c.frame(x, 225, w, 13, border)
        if status == "verified":
            _check(c, x + 3, 230, P["gold2"])
        elif status == "blocked":
            _cross(c, x + 3, 229, P["red"])
        elif status == "in_progress":
            c.rect(x + 3, 229, 5, 5, P["cyan1"])
            c.rect(x + 4, 230, 3, 3, P["cyan3"])
        else:
            c.frame(x + 3, 229, 5, 5, P["stone2"])
        c.text(x + 10, 228, label, P["ink"] if status != "planned" else P["stone4"])
        x += w + 3
    return c


def render_current(data: dict) -> Canvas:
    phase = next(p for p in data["phases"] if p["id"] == data["current_phase"])
    items = milestones_of(data, phase["id"])
    gate = _wrap("GATE: " + phase["gate"], 320)
    top = 41 + len(gate) * 9 + 5
    c = Canvas(400, max(64, top + len(items) * 20 + 4))
    _backdrop(c)
    big = Canvas(16, 16)
    icon(big, phase["icon"], 0, 0, dim=False)
    c.frame(10, 10, 42, 42, P["cyan0"])
    c.frame(12, 12, 38, 38, P["cyan2"])
    c.rect(13, 13, 36, 36, P["night2"])
    for yy in range(16):
        for xx in range(16):
            if big.px[yy][xx]:
                c.rect(15 + xx * 2, 15 + yy * 2, 2, 2, big.px[yy][xx])
    c.text(62, 12, f"NOW \u00b7 {phase['id']}", P["cyan2"])
    upcoming = "UP NEXT: " + " \u00b7 ".join(data.get("next_milestones", [])) if data.get("next_milestones") else ""
    if upcoming:
        c.text(386 - Canvas.text_width(upcoming), 12, upcoming, P["faint"])
    c.text(62, 22, phase["name"].upper(), P["ink"], scale=2, shadow=P["void"])
    for index, line in enumerate(gate):
        c.text(62, 41 + index * 9, line, P["faint"])
    y = top
    for item in items:
        _pip(c, 62, y + 1, item["status"])
        state = LABELS["en"][item["status"]].upper()
        c.text(70, y, item["id"], P["ink"])
        c.text(108, y, state, P[STATUS_COLORS[item["status"]]])
        if item["id"] == data["active_milestone"]:
            c.text(114 + Canvas.text_width(state), y, "< ACTIVE", P["cyan2"])
        c.text(108, y + 9, item["title"].upper(), P["muted"])
        y += 20
    return c


# -- markdown -----------------------------------------------------------------------

def _link(item: dict) -> str:
    url = item["url"]
    return f"[{item['ref']}]({url})" if url.startswith("http") else f"[{item['ref']}](../{url})"


def readme_section(data: dict, lang: str) -> str:
    text = LABELS[lang]
    head = ("| Phase | Focus | Status | Milestones done |\n|---|---|---|---|" if lang == "en" else
            "| Фаза | Содержание | Статус | Готово тикетов |\n|---|---|---|---|")
    rows = [head]
    for phase in data["phases"]:
        items = milestones_of(data, phase["id"])
        state = text[phase_status(data, phase["id"])]
        if phase["id"] == data["current_phase"]:
            state = f"**{state}**"
        name = phase["name"] if lang == "en" else phase["name_ru"]
        summary = phase["summary"] if lang == "en" else phase["summary_ru"]
        done = sum(1 for m in items if m["status"] == "done")
        count = f"{done} / {len(items)}" if items else "—"
        rows.append(f"| {phase['id']} {name} | {summary} | {state} | {count} |")
    rows.append("")
    title = "Verification levels" if lang == "en" else "Уровни проверки"
    rows.append(f"**{title}:** " + " → ".join(
        f"{v['name'] if lang == 'en' else v['name_ru']} — {text[v['status']].lower()}" for v in data["verification"]))
    return "\n".join(rows)


def details_section(data: dict) -> str:
    out = []
    for phase in data["phases"]:
        state = LABELS["en"][phase_status(data, phase["id"])]
        out.append(f"### {phase['id']} — {phase['name']} · {state}\n")
        out.append(f"{phase['summary']}.  \n**Gate:** {phase['gate']}.\n")
        items = milestones_of(data, phase["id"])
        if not items:
            out.append("_No backlog tickets yet; this phase depends on earlier phases and upstream engine work._\n")
            continue
        out.append("| Milestone | Status | Depends on | Evidence | Notes |\n|---|---|---|---|---|")
        for item in items:
            evidence = "<br>".join(f"{e['level']}: {_link(e)}" for e in item["evidence"]) or "—"
            notes = item.get("missing") or item.get("blocker") or ""
            if item["id"] == data["active_milestone"]:
                notes = ("**Active.** " + notes).strip()
            deps = ", ".join(item["depends_on"]) or "—"
            out.append(f"| {item['id']} {item['title']} | {LABELS['en'][item['status']]} | {deps} | {evidence} | {notes} |")
        out.append("")
    pixelchat = [m for m in data["milestones"] if m.get("track") == "pixelchat"]
    if pixelchat:
        out.append("### PixelChat · experimental track ([epic #11](" + REPO_URL + "issues/11))\n")
        out.append("A separate prototype track. The browser relay is not a Horizon mod; game integration needs the "
                   "contracts listed below.\n")
        out.append("| Milestone | Status | Depends on | Evidence | Notes |\n|---|---|---|---|---|")
        for item in pixelchat:
            evidence = "<br>".join(f"{e['level']}: {_link(e)}" for e in item["evidence"]) or "—"
            notes = item.get("missing") or item.get("blocker") or ""
            out.append(f"| {item['id']} {item['title']} | {LABELS['en'][item['status']]} | "
                       f"{', '.join(item['depends_on']) or '—'} | {evidence} | {notes} |")
        out.append("")
    if data.get("engine_contracts"):
        out.append("### Engine contracts not yet in a capability profile\n")
        out.append("| Contract | State | Notes | Source |\n|---|---|---|---|")
        for contract in data["engine_contracts"]:
            out.append(f"| `{contract['id']}` | {contract['status']} | {contract['note']} | {contract['source']} |")
        out.append("")
    for show in data.get("showcases", []):
        out.append(f"### Showcase {show['id']}: {show['name']}\n")
        out.append(f"{show['summary']}  \n**Milestones:** {', '.join(show['milestones'])}.\n")
        out.append("| Level | Meaning | Status |\n|---|---|---|")
        for level in show["levels"]:
            out.append(f"| {level['level']} | {level['name']} | {LABELS['en'][level['status']]} |")
        out.append("")
    out.append("### Verification levels\n")
    out.append("| Level | Status | Scope | Evidence |\n|---|---|---|---|")
    for level in data["verification"]:
        evidence = "<br>".join(_link(e) for e in level["evidence"]) or "—"
        out.append(f"| {level['name']} | {LABELS['en'][level['status']]} | {level['detail']} | {evidence} |")
    return "\n".join(out)


def _pr_numbers(item: dict) -> list[int]:
    return [int(n) for e in item["evidence"] for n in re.findall(r"/pull/(\d+)", e["url"])]


def validate_releases(data: dict, releases: dict, version: str) -> list[str]:
    """Problems with docs/releases/releases.json (verified, published releases only)."""
    if not isinstance(releases, dict) or releases.get("schema") != "horizon-studio.releases/1":
        return ["releases.json must be a horizon-studio.releases/1 document"]
    problems, seen = [], set()
    entries = releases.get("releases")
    if not isinstance(entries, list) or not entries:
        return ["releases.json needs at least one release"]
    for entry in entries:
        v = entry.get("version", "")
        where = f"release {v!r}"
        if not re.fullmatch(r"\d+\.\d+\.\d+", v) or v in seen:
            problems.append(f"{where}: invalid or duplicate version")
            continue
        seen.add(v)
        exe = entry.get("executable", {})
        if entry.get("tag") != f"v{v}":
            problems.append(f"{where}: tag must be v{v}")
        if not re.fullmatch(r"[0-9a-f]{40}", entry.get("commit", "")):
            problems.append(f"{where}: commit must be a full SHA")
        if exe.get("name") != f"HorizonStudio-{v}-Windows-x64.exe":
            problems.append(f"{where}: executable name does not match the version")
        if not re.fullmatch(r"[0-9a-f]{64}", exe.get("sha256", "")) or not isinstance(exe.get("size"), int):
            problems.append(f"{where}: executable needs size and SHA-256")
        if entry.get("channel") not in ("prerelease", "stable"):
            problems.append(f"{where}: channel must be prerelease or stable")
        if tuple(map(int, v.split("."))) > tuple(map(int, version.split("."))):
            problems.append(f"{where}: newer than VERSION {version}")
        if not isinstance(entry.get("last_pr"), int) or not entry.get("capabilities"):
            problems.append(f"{where}: needs last_pr and capabilities")
            continue
        milestones = {m["id"]: m for m in data["milestones"]}
        for capability in entry["capabilities"]:
            mid = capability.get("milestone")
            if mid is None:
                continue
            if mid not in milestones:
                problems.append(f"{where}: unknown milestone {mid}")
            elif any(n > entry["last_pr"] for n in _pr_numbers(milestones[mid])):
                problems.append(f"{where}: claims {mid}, which landed after PR #{entry['last_pr']}")
    return problems


def latest_release(releases: dict) -> dict:
    return max(releases["releases"], key=lambda e: tuple(map(int, e["version"].split("."))))


def release_section(data: dict, releases: dict, lang: str) -> str:
    rel = latest_release(releases)
    base = REPO_URL.rstrip("/")
    page, exe = f"{base}/releases/tag/{rel['tag']}", rel["executable"]
    download = f"{base}/releases/download/{rel['tag']}/{exe['name']}"
    sums = f"{base}/releases/download/{rel['tag']}/SHA256SUMS.txt"
    size = f"{exe['size'] / 1048576:.1f} MB" if lang == "en" else f"{exe['size'] / 1048576:.1f} МБ".replace(".", ",")
    channel = {"prerelease": ("alpha prerelease", "альфа-предрелиз"), "stable": ("stable", "стабильный")}[rel["channel"]]
    newer = [m for m in data["milestones"] if m["status"] == "done" and _pr_numbers(m)
             and max(_pr_numbers(m)) > rel["last_pr"]]
    if lang == "en":
        lines = [f"**[Horizon Studio {rel['tag']} — {rel['name']}]({page})** · {channel[0]} · published {rel['published']}  ",
                 f"⬇ **[{exe['name']}]({download})** · {size} · [SHA256SUMS.txt]({sums})  ",
                 f"SHA-256 `{exe['sha256']}` · built from [`{rel['commit'][:7]}`]({base}/commit/{rel['commit']}) · unsigned",
                 "", f"**In this build** ({rel['verified_by']}):", ""]
        lines += [f"- {c['en']}" for c in rel["capabilities"]]
        if newer:
            lines += ["", f"**On `master` but not in this executable:** " + "; ".join(f"{m['id']} {m['title']}" for m in newer) + "."]
    else:
        lines = [f"**[Horizon Studio {rel['tag']} — {rel['name']}]({page})** · {channel[1]} · опубликован {rel['published']}  ",
                 f"⬇ **[{exe['name']}]({download})** · {size} · [SHA256SUMS.txt]({sums})  ",
                 f"SHA-256 `{exe['sha256']}` · собран из [`{rel['commit'][:7]}`]({base}/commit/{rel['commit']}) · без подписи",
                 "", f"**В этой сборке** ({rel['verified_by_ru']}):", ""]
        lines += [f"- {c['ru']}" for c in rel["capabilities"]]
        if newer:
            lines += ["", f"**Есть в `master`, но не в этом EXE:** " + "; ".join(f"{m['id']} {m['title_ru']}" for m in newer) + "."]
    return "\n".join(lines)


def replace_section(text: str, name: str, body: str) -> str:
    start, end = f"<!-- roadmap:{name}:start -->", f"<!-- roadmap:{name}:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise RoadmapError(f"Missing or repeated roadmap:{name} markers")
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    return f"{head}{start}\n{body}\n{end}{tail}"


def outputs(data: dict) -> dict[Path, str]:
    files = {
        ASSETS / "roadmap-overview.svg": render_overview(data).to_svg(
            4, "Horizon Studio development journey",
            "Pixel-art roadmap of phases F0 to F8 with derived statuses, milestone pips and verification levels. "
            f"Current phase {data['current_phase']}, active milestone {data['active_milestone']}."),
        ASSETS / "current-phase.svg": render_current(data).to_svg(
            4, "Horizon Studio current phase",
            f"Current phase {data['current_phase']} with its milestones and their verified status."),
    }
    # The same pixel phase icons, one file each, for the in-app journey explorer.
    for kind in ICONS:
        for dim in (False, True):
            canvas = Canvas(16, 16)
            icon(canvas, kind, 0, 0, dim)
            name = f"{kind}-dim" if dim else kind
            files[ASSETS / "icons" / f"{name}.svg"] = canvas.to_svg(
                2, f"Phase icon: {kind}", f"Pixel phase icon '{kind}'{' (not started)' if dim else ''} from scripts/roadmap.py")
    releases = json.loads(RELEASES.read_text(encoding="utf-8"))
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    problems = validate_releases(data, releases, version)
    if problems:
        raise RoadmapError("; ".join(problems))
    pages = {
        ROOT / "README.md": [("status", readme_section(data, "en")), ("release", release_section(data, releases, "en"))],
        ROOT / "README.ru.md": [("status", readme_section(data, "ru")), ("release", release_section(data, releases, "ru"))],
        ROOT / "docs" / "ROADMAP_VISUAL.md": [("details", details_section(data))],
    }
    for path, sections in pages.items():
        text = path.read_text(encoding="utf-8")
        for name, body in sections:
            text = replace_section(text, name, body)
        files[path] = text
    return files


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render the Horizon Studio roadmap from docs/roadmap/roadmap.json")
    parser.add_argument("--check", action="store_true", help="Fail if data is invalid or outputs are stale")
    args = parser.parse_args(argv)
    try:
        data = load()
        files = outputs(data)
    except (OSError, ValueError) as exc:
        print(f"Roadmap error: {exc}", file=sys.stderr)
        return 1
    stale = []
    for path, content in files.items():
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if current == content:
            continue
        if args.check:
            stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print("Stale roadmap outputs (run python scripts/roadmap.py):", *stale, sep="\n  ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

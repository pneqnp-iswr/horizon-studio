"""The in-app "Development journey": the whole roadmap graph from docs/roadmap/roadmap.json
and, separately, what the running build can do (the HS-008 capability registry).

The roadmap is the development *plan* as of the commit this build was made from; only
``build`` describes this installation. Phase status follows scripts/roadmap.py (tests keep
the two in step); the experimental PixelChat track is listed but not counted in phase progress.
"""
from __future__ import annotations

import json
from pathlib import Path

from studio_core.capabilities import BUILDABLE, load_registry, profile_for

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs" / "roadmap" / "roadmap.json"
VERSION = ROOT / "VERSION"
REPOSITORY = "https://github.com/pneqnp-iswr/horizon-studio"
STARTED = ("done", "partial", "in_progress", "blocked")
TRACKS = {"studio": ("Horizon Studio", "Horizon Studio"),
          "pixelchat": ("PixelChat (experimental)", "PixelChat (экспериментально)")}
MILESTONE_FIELDS = ("id", "track", "phase", "status", "depends_on", "title", "title_ru", "summary", "summary_ru",
                    "deliverable", "deliverable_ru", "acceptance", "engine_requirements", "validation_target",
                    "missing", "blocker")


def phase_status(roadmap: dict, phase_id: str) -> str:
    states = [m["status"] for m in roadmap["milestones"]
              if m["phase"] == phase_id and m.get("track", "studio") == "studio"]
    if phase_id == roadmap["current_phase"]:
        return "in_progress"
    if states and all(s == "done" for s in states):
        return "done"
    if any(s in STARTED for s in states):
        return "partial"
    return "planned"


def link(target: str) -> str:
    """Repository paths become GitHub links; links stay as they are."""
    return target if target.startswith("http") else f"{REPOSITORY}/blob/master/{target}"


def requirement_states(roadmap: dict, registry: dict) -> dict[str, str]:
    """Requirement id -> 'buildable' | 'engine' | 'missing' across the audited profiles."""
    rank = {"missing": 0, "engine": 1, "buildable": 2}
    states: dict[str, str] = {}

    def note(name: str, state: str) -> None:
        if rank[state] >= rank.get(states.get(name, "missing"), 0):
            states[name] = state

    for profile in registry["profiles"]:
        for name, entry in profile["capabilities"].items():
            note(name, "buildable" if entry["status"] == BUILDABLE else
                 "engine" if entry["status"] == "engine-only" else "missing")
    for contract in roadmap.get("engine_contracts", []):
        note(contract["id"], "engine" if contract["status"] == "available" else "missing")
    return states


def build_capabilities(registry: dict | None = None) -> dict:
    """Capabilities of the default engine profile, grouped by what this build can do."""
    registry = registry or load_registry()
    profile = profile_for(registry, None)
    groups: dict[str, list[dict]] = {"official-static": [], "engine-only": [], "unsupported": []}
    for name, entry in sorted(profile["capabilities"].items()):
        groups[entry["status"]].append({"capability": name, **{key: entry.get(key) for key in (
            "api", "stability", "side", "backend", "permissions", "contract", "note", "note_ru", "source")}})
    version = VERSION.read_text(encoding="utf-8").strip() if VERSION.is_file() else "development"
    return {"engine": profile["engine"], "revision": profile["revision"], "label": profile["label"],
            "content_api": profile["content_api"], "buildable": BUILDABLE, "groups": groups,
            "studio_version": version,
            "profiles": [{"revision": p["revision"], "label": p["label"]} for p in registry["profiles"]]}


def view(roadmap: dict | None = None, registry: dict | None = None) -> dict:
    roadmap = roadmap if roadmap is not None else json.loads(ROADMAP.read_text(encoding="utf-8"))
    registry = registry or load_registry()
    states = requirement_states(roadmap, registry)
    dependents: dict[str, list[str]] = {}
    for item in roadmap["milestones"]:
        for dep in item["depends_on"]:
            dependents.setdefault(dep, []).append(item["id"])
    milestones = []
    for item in roadmap["milestones"]:
        entry = {key: item[key] for key in MILESTONE_FIELDS if key in item}
        entry["dependents"] = dependents.get(item["id"], [])
        entry["requirements"] = [{"id": name, "state": states.get(name, "missing")}
                                 for name in item["engine_requirements"]]
        entry["design"] = link(item["design_ref"])
        entry["evidence"] = [{"level": e["level"], "ref": e["ref"], "url": link(e["url"])} for e in item["evidence"]]
        if "issue" in item:
            entry["issue"] = f"{REPOSITORY}/issues/{item['issue']}"
        milestones.append(entry)
    return {
        "schema": "horizon-studio.journey/2",
        "updated": roadmap.get("updated"),
        "repository": REPOSITORY,
        "current_phase": roadmap["current_phase"],
        "active_milestone": roadmap["active_milestone"],
        "next_milestones": list(roadmap.get("next_milestones", [])),
        "phases": [{**{k: p.get(k) for k in ("id", "name", "name_ru", "summary", "summary_ru", "gate", "icon")},
                    "status": phase_status(roadmap, p["id"]),
                    "milestones": [m["id"] for m in roadmap["milestones"] if m["phase"] == p["id"]]}
                   for p in roadmap["phases"]],
        "milestones": milestones,
        "tracks": [{"id": key, "name": en, "name_ru": ru} for key, (en, ru) in TRACKS.items()],
        "engine_contracts": roadmap.get("engine_contracts", []),
        "showcases": roadmap.get("showcases", []),
        "verification": [{k: v.get(k) for k in ("level", "name", "name_ru", "status", "detail", "detail_ru")}
                         for v in roadmap.get("verification", [])],
        "build": build_capabilities(registry),
    }

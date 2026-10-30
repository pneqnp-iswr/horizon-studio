"""The in-app "Development journey": the roadmap (docs/roadmap/roadmap.json) and what the
running build can do (the HS-008 capability registry), as one view for the editor.

The roadmap is the development *plan*; only ``build`` describes this installation.
Phase status follows scripts/roadmap.py (tests keep the two in step).
"""
from __future__ import annotations

import json
from pathlib import Path

from studio_core.capabilities import BUILDABLE, load_registry, profile_for

ROADMAP = Path(__file__).resolve().parents[1] / "docs" / "roadmap" / "roadmap.json"
STARTED = ("done", "partial", "in_progress", "blocked")


def phase_status(roadmap: dict, phase_id: str) -> str:
    states = [m["status"] for m in roadmap["milestones"] if m["phase"] == phase_id]
    if phase_id == roadmap["current_phase"]:
        return "in_progress"
    if states and all(s == "done" for s in states):
        return "done"
    if any(s in STARTED for s in states):
        return "partial"
    return "planned"


def _milestone(roadmap: dict, milestone_id: str) -> dict | None:
    found = next((m for m in roadmap["milestones"] if m["id"] == milestone_id), None)
    if found is None:
        return None
    return {key: found.get(key) for key in ("id", "phase", "status", "title", "title_ru")}


def build_capabilities(registry: dict | None = None) -> dict:
    """Capabilities of the default engine profile, grouped by what this build can do."""
    registry = registry or load_registry()
    profile = profile_for(registry, None)
    groups: dict[str, list[dict]] = {"official-static": [], "engine-only": [], "unsupported": []}
    for name, entry in sorted(profile["capabilities"].items()):
        groups[entry["status"]].append({"capability": name, **{key: entry.get(key) for key in (
            "api", "stability", "side", "backend", "permissions", "contract", "note", "note_ru", "source")}})
    return {"engine": profile["engine"], "revision": profile["revision"], "label": profile["label"],
            "content_api": profile["content_api"], "buildable": BUILDABLE, "groups": groups}


def view(roadmap: dict | None = None, registry: dict | None = None) -> dict:
    roadmap = roadmap if roadmap is not None else json.loads(ROADMAP.read_text(encoding="utf-8"))
    return {
        "schema": "horizon-studio.journey/1",
        "updated": roadmap.get("updated"),
        "current_phase": roadmap["current_phase"],
        "phases": [{**{k: p.get(k) for k in ("id", "name", "name_ru", "summary", "summary_ru", "gate")},
                    "status": phase_status(roadmap, p["id"])} for p in roadmap["phases"]],
        "active_milestone": _milestone(roadmap, roadmap["active_milestone"]),
        "next_milestones": [m for m in (_milestone(roadmap, i) for i in roadmap.get("next_milestones", [])) if m],
        "verification": [{k: v.get(k) for k in ("level", "name", "name_ru", "status", "detail", "detail_ru")}
                         for v in roadmap.get("verification", [])],
        "build": build_capabilities(registry),
    }

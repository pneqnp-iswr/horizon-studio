"""Engine capability registry (HS-008): what a pinned Horizon revision supports, and
whether a ``studio.project/1`` document needs anything it does not.

Statuses, strongest first:
  official-static  Studio builds it and the real cargo-horizon-mod accepted such packages
  engine-only      the engine supports it but Studio cannot produce it yet
  unsupported      the engine has no way to load it at this revision
No status claims that the game loads or runs the content (that is HS-002).
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from studio_core.project_schema import validate_document

REGISTRY = Path(__file__).with_name("engine_profiles.json")
STATUSES = ("official-static", "engine-only", "unsupported")
BUILDABLE = "official-static"
ROOT = Path(__file__).resolve().parents[1]


def load_registry(path: Path = REGISTRY) -> dict:
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = validate_registry(registry)
    if problems:
        raise ValueError("Invalid engine capability registry: " + "; ".join(problems))
    return registry


def validate_registry(registry) -> list[str]:
    if not isinstance(registry, dict) or registry.get("schema") != "horizon-studio.engine-profiles/1":
        return ["expected a horizon-studio.engine-profiles/1 document"]
    problems, revisions = [], set()
    for profile in registry.get("profiles", []):
        revision = profile.get("revision", "")
        if not re.fullmatch(r"[0-9a-f]{40}", revision) or revision in revisions:
            problems.append(f"profile revision {revision!r} must be a unique full SHA")
        revisions.add(revision)
        for name, capability in profile.get("capabilities", {}).items():
            status = capability.get("status")
            if status not in STATUSES:
                problems.append(f"{revision[:7]} {name}: unsupported status {status!r}")
            if status == BUILDABLE and not (ROOT / capability.get("evidence", "")).is_file():
                problems.append(f"{revision[:7]} {name}: official-static needs an evidence document")
            if status != BUILDABLE and not capability.get("note"):
                problems.append(f"{revision[:7]} {name}: {status} needs a note explaining why")
    if registry.get("default") not in revisions:
        problems.append("default must name a listed profile")
    return problems


def profile_for(registry: dict, revision: str | None) -> dict | None:
    revision = revision or registry["default"]
    return next((p for p in registry["profiles"] if p["revision"] == revision), None)


def requirements(doc: dict) -> dict[str, list[str]]:
    """Capability -> objects (``kind id``) that need it."""
    validate_document(doc)
    needs: dict[str, list[str]] = {}

    def need(capability: str, obj: dict):
        needs.setdefault(capability, []).append(f"{obj['kind']} {obj['id']}")

    for obj in doc["objects"]:
        kind, props = obj["kind"], obj["props"]
        if kind == "block":
            for capability in ("content.block", "content.loot_table", "content.lang"):
                need(capability, obj)
            if props.get("requires_tool") or props.get("mining_tool", "none") != "none" \
                    or props.get("tool_tier", "none") != "none":
                need("content.block_tag", obj)
        elif kind == "item":
            need("content.item", obj)
            need("content.lang", obj)
        elif kind == "recipe":
            need("content.recipe", obj)
        elif kind == "structure":
            need("content.structure_nbt", obj)
        else:
            need(f"kind.{kind}", obj)
    return needs


def check(doc: dict, registry: dict | None = None) -> dict:
    """Profile used and diagnostics for everything the project needs but cannot build."""
    registry = registry or load_registry()
    target = doc.get("target") if isinstance(doc.get("target"), dict) else {}
    profile = profile_for(registry, target.get("revision"))
    if profile is None:
        return {"profile": None, "requirements": requirements(doc), "diagnostics": [{
            "level": "error", "code": "ENGINE_PROFILE_UNKNOWN",
            "message": f"No capability profile for Horizon revision {target.get('revision')}; "
                       "nothing can be promised for it"}]}
    needs = requirements(doc)
    diagnostics = []
    for capability, users in sorted(needs.items()):
        entry = profile["capabilities"].get(capability)
        if entry and entry["status"] == BUILDABLE:
            continue
        why = entry["note"] if entry else "this revision has no known way to load it"
        diagnostics.append({"level": "error", "code": "ENGINE_CAPABILITY_MISSING", "capability": capability,
                            "message": f"{capability} ({', '.join(users[:3])}{'…' if len(users) > 3 else ''}): {why}"})
    return {"profile": {"revision": profile["revision"], "label": profile["label"], "content_api": profile["content_api"]},
            "requirements": needs, "diagnostics": diagnostics}

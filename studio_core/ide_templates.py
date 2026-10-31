"""Offline, audited starter projects for Horizon IDE.

The only template inputs are these repository-owned example fixtures. No network
fetches, user paths, native executable code, or unsandboxed template hooks.
The API returns fresh editor state; the caller must ask before replacing work.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from studio_core.migrate import to_editor_state, upgrade

SCHEMA = "horizon-studio.ide-templates/1"
ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = (
    {
        "id": "ruby",
        "file": "ruby_demo.hstudio.json",
        "name": "Ruby Content Kit",
        "name_ru": "Рубиновый набор",
        "description": "One block, one item and two real recipes — a starting point for content mods.",
        "description_ru": "Блок, предмет и два рецепта — основа контентного мода.",
        "category": "content",
    },
    {
        "id": "voxel",
        "file": "voxel_showcase.hstudio.json",
        "name": "Voxel Architect",
        "name_ru": "Воксельный архитектор",
        "description": "Three procedural structures with deterministic generation.",
        "description_ru": "Три процедурные структуры с воспроизводимой генерацией.",
        "category": "world",
    },
    {
        "id": "workshop",
        "file": "workshop_showcase.hstudio.json",
        "name": "Creator Workshop",
        "name_ru": "Мастерская создателя",
        "description": "Blocks, items, crafting, tool tags and six structure generators.",
        "description_ru": "Блоки, предметы, рецепты, инструменты и шесть генераторов структур.",
        "category": "mixed",
    },
)


class TemplateError(ValueError):
    """A missing, corrupt, or unsupported built-in starter fixture."""


def _read(spec):
    # Never accept a path from an HTTP request. IDs resolve through the static catalog.
    path = ROOT / "examples" / spec["file"]
    try:
        payload = path.read_bytes()
        if len(payload) > 6 * 1024 * 1024:
            raise TemplateError("Template exceeds the project size limit")
        doc = upgrade(json.loads(payload))
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        raise TemplateError(f"Built-in template {spec['id']!r} is unavailable: {exc}") from None
    return doc, hashlib.sha256(payload).hexdigest()


def list_templates() -> dict:
    """Build a catalog from the actual fixtures, never from guessed capabilities."""
    entries = []
    for spec in TEMPLATES:
        doc, digest = _read(spec)
        counts = {}
        for asset in doc["objects"]:
            counts[asset["kind"]] = counts.get(asset["kind"], 0) + 1
        entries.append({
            **{k: spec[k] for k in ("id", "name", "name_ru", "description", "description_ru", "category")},
            "project_id": doc["project"]["id"],
            "counts": counts,
            "sha256": digest,
            # Static fixture validation != tested in a running game.
            "verification": "project-schema-only",
            "in_game_verified": False,
        })
    return {"schema": SCHEMA, "templates": entries}


def load_template(template_id: str) -> dict:
    """Return an independent editor-state snapshot, never write to disk."""
    spec = next((s for s in TEMPLATES if s["id"] == template_id), None)
    if spec is None:
        raise KeyError("Unknown starter template")
    doc, digest = _read(spec)
    return {
        "schema": SCHEMA,
        "template_id": spec["id"],
        "sha256": digest,
        "verification": "project-schema-only",
        "in_game_verified": False,
        "state": to_editor_state(doc),
    }

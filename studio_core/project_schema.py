"""Canonical Horizon Studio project document, ``studio.project/1`` (ADR-001).

A project is one JSON document. Every object (block, item, recipe, structure)
has a stable ``uid`` that survives renames, and objects refer to each other by
``{"ref": "<uid>"}`` instead of by name. Object kinds Studio does not know yet
(future plugins) and unknown top-level fields are kept untouched.

Layout::

    {
      "format": "horizon-studio",
      "schema": "studio.project/1",
      "project": {"id": "ruby_demo", "name": "...", "version": "0.1.0", ...},
      "objects": [{"uid": "<uuid>", "kind": "block", "id": "ruby_block", "props": {...}}, ...],
      "source_overrides": {"assets/ruby_demo/models/block/ruby_block.json": "<json text>"},
      "extensions": {},
      "provenance": {"migrations": [{"from": 2, "to": "studio.project/1"}]}
    }
"""
from __future__ import annotations

import json
import re
import uuid

FORMAT = "horizon-studio"
SCHEMA = "studio.project/1"
LEGACY_SCHEMAS = (2, 3, 4)
KINDS = ("block", "item", "recipe", "structure")
# Blocks and items share one namespace in the generated mod (``<mod>:<id>``).
ID_SPACES = {"block": "content", "item": "content", "recipe": "recipe", "structure": "structure"}
KIND_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
OBJECT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_OBJECTS = 10_000
MAX_TEXT = 200
# Fixed namespace: migrating the same legacy file twice yields the same uids.
LEGACY_UID_NAMESPACE = uuid.UUID("7628941c-8780-4684-995d-dff42b0c2d1b")


class ProjectFormatError(ValueError):
    """The data is not a structurally valid project document."""


def new_uid() -> str:
    return str(uuid.uuid4())


def legacy_uid(mod_id: str, kind: str, object_id: str) -> str:
    return str(uuid.uuid5(LEGACY_UID_NAMESPACE, f"{mod_id}\n{kind}\n{object_id}"))


def is_uid(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def is_ref(value) -> bool:
    return isinstance(value, dict) and set(value) == {"ref"} and is_uid(value["ref"])


def _fail(message: str):
    raise ProjectFormatError(message)


def _check_recipe(obj: dict):
    props = obj["props"]
    label = f"Recipe {obj['id']}"
    result = props.get("result")
    if not (result is None or isinstance(result, str) or is_ref(result)):
        _fail(f"{label}: result must be a reference or a resource name")
    grid = props.get("grid")
    if not isinstance(grid, list) or len(grid) > 9:
        _fail(f"{label}: grid must be a list of at most nine slots")
    for cell in grid:
        if not (cell is None or isinstance(cell, str) or is_ref(cell)):
            _fail(f"{label}: each slot must be empty, a reference or a resource name")


def validate_document(doc) -> dict:
    """Return ``doc`` if it is structurally a ``studio.project/1`` document.

    Semantic checks (dangling references, generator limits, value ranges) are
    reported by :mod:`studio_core.graph` and by the generator, not here.
    """
    if not isinstance(doc, dict) or doc.get("format") != FORMAT or doc.get("schema") != SCHEMA:
        _fail(f"Expected a {FORMAT} {SCHEMA} document")
    project = doc.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("id"), str) or len(project["id"]) > MAX_TEXT:
        _fail("project.id must be text")
    objects = doc.get("objects")
    if not isinstance(objects, list) or len(objects) > MAX_OBJECTS:
        _fail(f"objects must be a list of at most {MAX_OBJECTS} entries")
    uids, names = set(), set()
    for index, obj in enumerate(objects):
        if not isinstance(obj, dict):
            _fail(f"objects[{index}] must be an object")
        kind, object_id, uid = obj.get("kind"), obj.get("id"), obj.get("uid")
        if not isinstance(kind, str) or not KIND_RE.fullmatch(kind):
            _fail(f"objects[{index}].kind is invalid")
        if not is_uid(uid):
            _fail(f"objects[{index}].uid must be a lowercase UUID")
        if uid in uids:
            _fail(f"Duplicate object uid {uid}")
        uids.add(uid)
        if not isinstance(object_id, str) or not object_id or len(object_id) > MAX_TEXT:
            _fail(f"objects[{index}].id must be text")
        if not isinstance(obj.get("props"), dict):
            _fail(f"objects[{index}].props must be an object")
        if "id" in obj["props"] or "uid" in obj["props"]:
            _fail(f"objects[{index}].props must not contain id or uid")
        if kind in KINDS:
            if not OBJECT_ID_RE.fullmatch(object_id):
                _fail(f"{kind} {object_id!r}: use 1-64 lowercase letters, numbers, underscores; start with a letter")
            if kind == "recipe":
                _check_recipe(obj)
        key = (ID_SPACES.get(kind, kind), object_id)
        if key in names:
            _fail(f"Duplicate {kind} id {object_id!r}")
        names.add(key)
    overrides = doc.get("source_overrides", {})
    if not isinstance(overrides, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                  for k, v in overrides.items()):
        _fail("source_overrides must map paths to text")
    for field in ("extensions", "provenance"):
        if not isinstance(doc.get(field, {}), dict):
            _fail(f"{field} must be an object")
    return doc


def dumps(doc: dict) -> str:
    """Stable, diff-friendly serialization (key order is part of the format)."""
    return json.dumps(validate_document(doc), ensure_ascii=False, indent=2, allow_nan=False) + "\n"

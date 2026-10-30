"""Conversions between project representations.

* legacy ``.hstudio.json`` (schemas 2, 3, 4)  -> ``studio.project/1``  (:func:`upgrade`)
* editor state posted by the browser UI       -> ``studio.project/1``  (:func:`from_editor_state`)
* ``studio.project/1`` -> editor state                                (:func:`to_editor_state`)
* ``studio.project/1`` -> generator request for ``studio.create_project_files``
                                                                      (:func:`to_generator_request`)

Editor state is the legacy schema-3 shape the UI already works with, plus a
``uid`` on every entry and an opaque ``carry`` object holding everything the
UI does not edit, so that open -> edit -> save loses nothing.
"""
from __future__ import annotations

import copy

from studio_core.project_schema import (FORMAT, LEGACY_SCHEMAS, SCHEMA, ProjectFormatError,
                                        is_ref, is_uid, legacy_uid, validate_document)

GROUPS = (("blocks", "block"), ("items", "item"), ("recipes", "recipe"), ("structures", "structure"))
METADATA_FIELDS = ("id", "name", "version", "author", "description")
LEGACY_TOP_LEVEL = {"format", "schema", "metadata", "blocks", "items", "recipes", "structures",
                    "source_overrides", "carry"}
DOCUMENT_FIELDS = ("format", "schema", "project", "objects", "source_overrides", "extensions", "provenance")


def source_schema(data) -> int | str | None:
    """The schema of a project file, or None if it is not a Studio project file."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return None
    schema = data.get("schema")
    return schema if schema == SCHEMA or schema in LEGACY_SCHEMAS else None


def upgrade(data) -> dict:
    """Return a validated ``studio.project/1`` document for any supported project file."""
    schema = source_schema(data)
    if schema is None:
        raise ProjectFormatError("Expected a Horizon Studio project (.hstudio.json, schema 2-4 or studio.project/1)")
    if schema == SCHEMA:
        return validate_document(copy.deepcopy(data))
    doc = _from_legacy(data, provenance={})
    doc["provenance"].setdefault("migrations", []).append({"from": schema, "to": SCHEMA})
    extra = {key: value for key, value in data.items() if key not in LEGACY_TOP_LEVEL}
    if extra:
        doc["extensions"]["horizon-studio.legacy-fields"] = copy.deepcopy(extra)
    return validate_document(doc)


def from_editor_state(state) -> dict:
    """Canonical document for what the editor holds; restores the opaque ``carry``."""
    if not isinstance(state, dict):
        raise ProjectFormatError("Expected the editor project state")
    carry = state.get("carry") or {}
    if not isinstance(carry, dict):
        raise ProjectFormatError("carry must be an object")
    doc = _from_legacy(state, provenance=copy.deepcopy(carry.get("provenance") or {}))
    project_extra = carry.get("project_extra") or {}
    if not isinstance(project_extra, dict):
        raise ProjectFormatError("carry.project_extra must be an object")
    for key, value in project_extra.items():
        doc["project"].setdefault(key, copy.deepcopy(value))
    preserved = carry.get("preserved_objects") or []
    if not isinstance(preserved, list):
        raise ProjectFormatError("carry.preserved_objects must be a list")
    doc["objects"].extend(copy.deepcopy(preserved))
    extensions = carry.get("extensions") or {}
    if not isinstance(extensions, dict):
        raise ProjectFormatError("carry.extensions must be an object")
    doc["extensions"] = copy.deepcopy(extensions)
    extra_fields = carry.get("document_extra") or {}
    if not isinstance(extra_fields, dict):
        raise ProjectFormatError("carry.document_extra must be an object")
    for key, value in extra_fields.items():
        if key not in DOCUMENT_FIELDS:
            doc[key] = copy.deepcopy(value)
    return validate_document(doc)


def _from_legacy(data: dict, provenance: dict) -> dict:
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        raise ProjectFormatError("Missing project metadata")
    mod_id = metadata.get("id")
    if not isinstance(mod_id, str):
        raise ProjectFormatError("Missing mod ID")
    groups = {}
    for group, _ in GROUPS:
        entries = data.get(group, [])
        if entries is None:
            entries = []
        if not isinstance(entries, list):
            raise ProjectFormatError(f"{group} must be a list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ProjectFormatError(f"{group}: each entry must be an object")
            if not isinstance(entry.get("id"), str):
                raise ProjectFormatError(f"{group}: each entry needs a text id")
        groups[group] = entries

    used = set()

    def uid_for(entry: dict, kind: str) -> str:
        uid = entry.get("uid")
        if uid is None:
            uid = legacy_uid(mod_id, kind, entry["id"])
        elif not is_uid(uid):
            raise ProjectFormatError(f"{kind} {entry['id']}: uid must be a lowercase UUID")
        if uid in used:
            raise ProjectFormatError(f"{kind} {entry['id']}: duplicate uid {uid}")
        used.add(uid)
        return uid

    content = {}
    objects = []
    for group, kind in GROUPS:
        for entry in groups[group]:
            props = {key: copy.deepcopy(value) for key, value in entry.items() if key not in ("id", "uid")}
            obj = {"uid": uid_for(entry, kind), "kind": kind, "id": entry["id"], "props": props}
            if kind in ("block", "item"):
                content.setdefault(entry["id"], obj["uid"])
            objects.append(obj)

    prefix = mod_id + ":"

    def to_ref(value):
        if value in ("", None):
            return None
        if isinstance(value, str):
            local = value[1:] if value.startswith("@") else value[len(prefix):] if value.startswith(prefix) else None
            if local is not None and local in content:
                return {"ref": content[local]}
            if value.startswith("@"):
                # Unknown local reference: keep its legacy meaning; the graph reports it.
                return prefix + value[1:]
        return copy.deepcopy(value)

    for obj in objects:
        if obj["kind"] == "recipe":
            props = obj["props"]
            if "result" in props:
                props["result"] = to_ref(props["result"])
            if isinstance(props.get("grid"), list):
                props["grid"] = [to_ref(cell) for cell in props["grid"]]

    overrides = data.get("source_overrides") or {}
    if not isinstance(overrides, dict):
        raise ProjectFormatError("source_overrides must be an object")
    return {
        "format": FORMAT,
        "schema": SCHEMA,
        "project": copy.deepcopy(metadata),
        "objects": objects,
        "source_overrides": copy.deepcopy(overrides),
        "extensions": {},
        "provenance": provenance,
    }


def _lookup(doc: dict) -> dict:
    return {obj["uid"]: obj for obj in doc["objects"]}


def to_generator_request(doc) -> dict:
    """The request ``studio.create_project_files`` builds a ``.hmod`` from.

    Unknown object kinds are left out (see ``studio_core.graph`` diagnostics).
    """
    validate_document(doc)
    mod_id = doc["project"]["id"]
    objects = _lookup(doc)
    request = copy.deepcopy(doc["project"])
    for group, _ in GROUPS:
        request[group] = []
    kinds = dict((kind, group) for group, kind in GROUPS)

    def resolve(value, label):
        if value is None:
            return ""
        if is_ref(value):
            target = objects.get(value["ref"])
            if target is None:
                raise ValueError(f"{label}: reference to missing object {value['ref']}")
            if target["kind"] not in ("block", "item"):
                raise ValueError(f"{label}: {target['kind']} {target['id']} is not a block or item")
            return f"{mod_id}:{target['id']}"
        return value

    for obj in doc["objects"]:
        if obj["kind"] not in kinds:
            continue
        entry = {"id": obj["id"], **copy.deepcopy(obj["props"])}
        if obj["kind"] == "recipe":
            label = f"Recipe {obj['id']}"
            entry["result"] = resolve(entry.get("result"), label)
            entry["grid"] = [resolve(cell, label) for cell in entry.get("grid", [])]
        request[kinds[obj["kind"]]].append(entry)
    if doc.get("source_overrides"):
        request["source_overrides"] = copy.deepcopy(doc["source_overrides"])
    return request


def to_editor_state(doc) -> dict:
    """The state the browser editor loads; ``carry`` must be sent back unchanged on save."""
    validate_document(doc)
    objects = _lookup(doc)
    state = {"metadata": {key: doc["project"][key] for key in METADATA_FIELDS if key in doc["project"]}}
    for group, _ in GROUPS:
        state[group] = []
    kinds = dict((kind, group) for group, kind in GROUPS)
    preserved = []

    def local(value, label):
        if value is None:
            return ""
        if is_ref(value):
            target = objects.get(value["ref"])
            if target is None or target["kind"] not in ("block", "item"):
                raise ProjectFormatError(f"{label}: reference {value['ref']} does not name a block or item")
            return "@" + target["id"]
        return value

    for obj in doc["objects"]:
        if obj["kind"] not in kinds:
            preserved.append(copy.deepcopy(obj))
            continue
        entry = {"id": obj["id"], "uid": obj["uid"], **copy.deepcopy(obj["props"])}
        if obj["kind"] == "recipe":
            label = f"Recipe {obj['id']}"
            entry["result"] = local(entry.get("result"), label)
            entry["grid"] = [local(cell, label) for cell in entry.get("grid", [])]
        state[kinds[obj["kind"]]].append(entry)
    state["source_overrides"] = copy.deepcopy(doc.get("source_overrides", {}))
    state["carry"] = {
        "project_extra": {k: copy.deepcopy(v) for k, v in doc["project"].items() if k not in METADATA_FIELDS},
        "preserved_objects": preserved,
        "extensions": copy.deepcopy(doc.get("extensions", {})),
        "provenance": copy.deepcopy(doc.get("provenance", {})),
        "document_extra": {k: copy.deepcopy(v) for k, v in doc.items() if k not in DOCUMENT_FIELDS},
    }
    return state

"""Dependency graph over the objects of a ``studio.project/1`` document.

Edges point from the object that uses something to the object it uses
(a recipe depends on its result and its ingredients).
"""
from __future__ import annotations

from studio_core.project_schema import KINDS, is_ref, validate_document


class AssetGraph:
    def __init__(self, doc: dict):
        validate_document(doc)
        self.mod_id = doc["project"]["id"]
        self.objects = {obj["uid"]: obj for obj in doc["objects"]}
        self.edges: list[tuple[str, str, str]] = []
        self.missing: list[tuple[str, str, str]] = []
        for obj in doc["objects"]:
            if obj["kind"] != "recipe":
                continue
            props = obj["props"]
            uses = [("result", props.get("result"))]
            uses += [(f"grid[{index}]", cell) for index, cell in enumerate(props.get("grid", []))]
            seen = set()
            for role, value in uses:
                if not is_ref(value):
                    continue
                target, use = value["ref"], "result" if role == "result" else "ingredient"
                if target not in self.objects:
                    self.missing.append((obj["uid"], target, role))
                elif (target, use) not in seen:
                    seen.add((target, use))
                    self.edges.append((obj["uid"], target, use))

    def dependencies(self, uid: str) -> list[str]:
        return sorted({target for source, target, _ in self.edges if source == uid})

    def dependents(self, uid: str) -> list[str]:
        return sorted({source for source, target, _ in self.edges if target == uid})

    def label(self, uid: str) -> str:
        obj = self.objects.get(uid)
        return f"{obj['kind']} {obj['id']}" if obj else uid

    def diagnostics(self) -> list[dict]:
        found = []
        for source, target, role in self.missing:
            found.append({"level": "error", "code": "MISSING_REFERENCE", "uid": source,
                          "message": f"{self.label(source)}: {role} refers to missing object {target}"})
        for source, target, role in self.edges:
            if self.objects[target]["kind"] not in ("block", "item"):
                found.append({"level": "error", "code": "INVALID_REFERENCE_KIND", "uid": source,
                              "message": f"{self.label(source)}: {role} refers to {self.label(target)}, "
                                         "not a block or item"})
        prefix = self.mod_id + ":"
        for obj in self.objects.values():
            if obj["kind"] == "recipe":
                values = [obj["props"].get("result")] + list(obj["props"].get("grid", []))
                for value in values:
                    if isinstance(value, str) and value.startswith(prefix):
                        found.append({"level": "error", "code": "UNRESOLVED_LOCAL_NAME", "uid": obj["uid"],
                                      "message": f"{self.label(obj['uid'])}: {value} is not an object of this project"})
            elif obj["kind"] == "vfx":
                from studio_core.vfx import diagnostics as vfx_diagnostics
                found.extend(vfx_diagnostics(obj, self.label(obj["uid"])))
            elif obj["kind"] not in KINDS:
                found.append({"level": "warning", "code": "UNSUPPORTED_OBJECT_KIND", "uid": obj["uid"],
                              "message": f"{self.label(obj['uid'])} is kept but not built by this Studio version"})
        return found

    def to_json(self) -> dict:
        return {
            "nodes": [{"uid": uid, "kind": obj["kind"], "id": obj["id"]} for uid, obj in self.objects.items()],
            "edges": [{"from": source, "to": target, "role": role} for source, target, role in self.edges],
            "diagnostics": self.diagnostics(),
        }

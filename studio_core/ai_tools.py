"""AI Creator tool contract and transactional executor (HS-020).

AI agents and people change a project through the same typed operations on the canonical
``studio.project/1`` document. Nothing here writes project files: every edit is planned on a
copy, validated (schema, references, the package generator) and only then committed as a
transaction with a revision precondition, an inverse for rollback and an audit entry. Engine
capability problems are reported, not hidden, and never delete authoring data.

Tools, by effect:
  read-only   inspect_project, list_assets, inspect_capabilities, validate_project, build_project
  edits       create_asset, update_asset, delete_asset (planned with ``propose``, applied with ``commit``)
  history     rollback_transaction
  privileged  export_package — needs ``approved=True`` from a person, never from the model
Native code is not a tool: generated Rust is never built or run by this executor (HS-010).
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import time
from dataclasses import dataclass, field

from studio_core.capabilities import check as capability_check
from studio_core.graph import AssetGraph
from studio_core.migrate import to_generator_request
from studio_core.project_schema import ProjectFormatError, dumps, is_ref, is_uid, new_uid, validate_document

CONTRACT = "horizon-studio.ai-tools/1"
READ_ONLY = ("inspect_project", "list_assets", "inspect_capabilities", "validate_project", "build_project")
EDITS = ("create_asset", "update_asset", "delete_asset")
PRIVILEGED = ("export_package",)
TOOLS = READ_ONLY + EDITS + ("rollback_transaction",) + PRIVILEGED
# Operations the editor's own transactions also use (studio_core.transactions); not offered to models.
STUDIO_EDITS = ("replace_asset", "set_project", "set_target", "set_source_overrides", "set_document_field",
                "reorder_assets", "reorder_fields")
# Document fields with their own operations; any other top-level field goes through set_document_field.
FIXED_FIELDS = ("format", "schema", "project", "objects", "target", "source_overrides")


class ToolError(ValueError):
    """A refused call; ``code`` is stable for programs, ``str()`` is for people."""

    def __init__(self, code: str, message: str, diagnostics: list | None = None):
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics or []


def revision(doc: dict) -> str:
    return hashlib.sha256(dumps(doc).encode("utf-8")).hexdigest()


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass
class Proposal:
    id: str
    actor: str
    base_revision: str
    result_revision: str
    operations: list
    changes: dict
    diagnostics: list
    document: dict = field(repr=False)


@dataclass
class Transaction:
    id: str
    actor: str
    base_revision: str
    result_revision: str
    changes: dict
    before: dict = field(repr=False)
    rolled_back: bool = False
    undo_of: str | None = None  # set on the record a rollback leaves behind


class Session:
    """One open project. Every change goes through propose/commit or rollback."""

    def __init__(self, doc: dict, *, uid_factory=new_uid, clock=time.time):
        self.doc = validate_document(copy.deepcopy(doc))
        self._uid = uid_factory
        self._clock = clock
        self.proposals: dict[str, Proposal] = {}
        self.history: list[Transaction] = []
        self.audit: list[dict] = []
        self._literal = False

    # -- bookkeeping ------------------------------------------------------------
    @property
    def revision(self) -> str:
        return revision(self.doc)

    def _log(self, actor: str, tool: str, args, outcome: str, **extra) -> None:
        self.audit.append({"seq": len(self.audit) + 1, "time": self._clock(), "actor": actor, "tool": tool,
                           "args_sha256": _digest(args), "outcome": outcome, **extra})

    def _expect(self, expected_revision: str | None, actor: str, tool: str, args) -> None:
        if expected_revision != self.revision:
            self._log(actor, tool, args, "rejected", code="REVISION_CONFLICT")
            raise ToolError("REVISION_CONFLICT", "The project changed since it was read; inspect it again before editing")

    # -- read-only tools ----------------------------------------------------------
    def call(self, tool: str, args: dict | None = None, *, actor: str, approved: bool = False) -> dict:
        args = args or {}
        if tool not in TOOLS or tool in EDITS or tool == "rollback_transaction":
            self._log(actor, tool, args, "rejected", code="UNKNOWN_TOOL")
            raise ToolError("UNKNOWN_TOOL", f"{tool} is not a read-only or privileged tool; edits go through propose()")
        if tool in PRIVILEGED and not approved:
            self._log(actor, tool, args, "rejected", code="APPROVAL_REQUIRED")
            raise ToolError("APPROVAL_REQUIRED", f"{tool} needs a person's approval")
        result = getattr(self, "_" + tool)(args)
        self._log(actor, tool, args, "read" if tool in READ_ONLY else "approved")
        return result

    def _inspect_project(self, args) -> dict:
        counts: dict[str, int] = {}
        for obj in self.doc["objects"]:
            counts[obj["kind"]] = counts.get(obj["kind"], 0) + 1
        return {"contract": CONTRACT, "revision": self.revision, "project": copy.deepcopy(self.doc["project"]),
                "target": copy.deepcopy(self.doc.get("target")), "counts": counts, "tools": list(TOOLS)}

    def _list_assets(self, args) -> dict:
        kind = args.get("kind")
        return {"revision": self.revision, "assets": [
            {"uid": o["uid"], "kind": o["kind"], "id": o["id"], "props": copy.deepcopy(o["props"])}
            for o in self.doc["objects"] if kind in (None, o["kind"])]}

    def _inspect_capabilities(self, args) -> dict:
        return capability_check(self.doc)

    def _validate_project(self, args) -> dict:
        diagnostics = _validate(self.doc)
        return {"revision": self.revision, "ok": not any(d["level"] == "error" for d in diagnostics),
                "diagnostics": diagnostics}

    def _package(self) -> bytes:
        from studio import hmod_zip
        blocked = [d for d in capability_check(self.doc)["diagnostics"] if d["level"] == "error"]
        if blocked:
            raise ToolError("ENGINE_CAPABILITY", "The target engine cannot load this project", blocked)
        return hmod_zip(to_generator_request(self.doc))

    def _build_project(self, args) -> dict:
        data = self._package()
        return {"revision": self.revision, "hmod_sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}

    def _export_package(self, args) -> dict:
        data = self._package()
        return {"revision": self.revision, "hmod_sha256": hashlib.sha256(data).hexdigest(),
                "hmod_base64": base64.b64encode(data).decode("ascii")}

    # -- edits ----------------------------------------------------------------------
    def propose(self, operations: list, *, actor: str, expected_revision: str, allowed: tuple = EDITS,
                strict: bool = True, literal: bool = False) -> Proposal:
        """Plan ``operations`` on a copy and validate the result; nothing changes until commit.

        ``strict`` refuses any error diagnostic (models must hand over buildable projects); the editor's
        own transactions pass ``strict=False``: the schema is still enforced, other findings are returned."""
        self._expect(expected_revision, actor, "propose", operations)
        try:
            document, changes = self._plan(operations, allowed, literal=literal)
            diagnostics = _validate(document)
            errors = [d for d in diagnostics if d["level"] == "error"]
            if errors and strict:
                raise ToolError("INVALID_RESULT", "; ".join(d["message"] for d in errors), errors)
        except ToolError as exc:
            self._log(actor, "propose", operations, "rejected", code=exc.code)
            raise
        proposal = Proposal(id=f"p{len(self.audit) + 1}-{_digest(operations)[:12]}", actor=actor,
                            base_revision=self.revision, result_revision=revision(document),
                            operations=copy.deepcopy(operations), changes=changes,
                            diagnostics=diagnostics, document=document)
        self.proposals[proposal.id] = proposal
        self._log(actor, "propose", operations, "proposed", proposal=proposal.id)
        return proposal

    def commit(self, proposal_id: str, *, actor: str, expected_revision: str) -> Transaction:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            self._log(actor, "commit", proposal_id, "rejected", code="UNKNOWN_PROPOSAL")
            raise ToolError("UNKNOWN_PROPOSAL", "No such proposal (cancelled, committed or never made)")
        self._expect(expected_revision, actor, "commit", proposal_id)
        if proposal.base_revision != self.revision:
            self._log(actor, "commit", proposal_id, "rejected", code="STALE_PROPOSAL")
            raise ToolError("STALE_PROPOSAL", "The project changed after this proposal was made")
        transaction = Transaction(id=f"t{len(self.history) + 1}", actor=actor, base_revision=self.revision,
                                  result_revision=proposal.result_revision, changes=proposal.changes,
                                  before=self.doc)
        self.doc = proposal.document
        del self.proposals[proposal_id]
        self.history.append(transaction)
        self._log(actor, "commit", proposal_id, "applied", transaction=transaction.id,
                  base_revision=transaction.base_revision, result_revision=transaction.result_revision)
        return transaction

    def cancel(self, proposal_id: str, *, actor: str) -> None:
        if self.proposals.pop(proposal_id, None) is None:
            raise ToolError("UNKNOWN_PROPOSAL", "No such proposal")
        self._log(actor, "cancel", proposal_id, "cancelled")

    def apply(self, operations: list, *, actor: str, expected_revision: str) -> Transaction:
        proposal = self.propose(operations, actor=actor, expected_revision=expected_revision)
        return self.commit(proposal.id, actor=actor, expected_revision=expected_revision)

    def rollback(self, transaction_id: str, *, actor: str, expected_revision: str) -> Transaction:
        """Undo the newest live transaction (older ones roll back in order, newest first)."""
        self._expect(expected_revision, actor, "rollback_transaction", transaction_id)
        live = [t for t in self.history if not t.rolled_back and t.undo_of is None]
        if not live or live[-1].id != transaction_id:
            self._log(actor, "rollback_transaction", transaction_id, "rejected", code="NOT_LATEST")
            raise ToolError("NOT_LATEST", "Only the newest transaction can be rolled back; roll back later ones first")
        target = live[-1]
        undo = Transaction(id=f"t{len(self.history) + 1}", actor=actor, base_revision=self.revision,
                           result_revision=target.base_revision, changes={"rolled_back": target.id}, before=self.doc,
                           undo_of=target.id)
        self.doc = target.before
        target.rolled_back = True
        self.history.append(undo)
        self._log(actor, "rollback_transaction", transaction_id, "applied", transaction=undo.id)
        return undo

    # -- planning ---------------------------------------------------------------------
    def plan(self, operations: list, *, allowed: tuple = EDITS, literal: bool = False) -> tuple[dict, dict]:
        """The document ``operations`` would produce and what they change; nothing is kept."""
        return self._plan(operations, allowed, literal=literal)

    def _plan(self, operations, allowed=EDITS, *, literal=False) -> tuple[dict, dict]:
        """``literal`` operations carry canonical values (the editor's diffs, undo and redo): no
        ``{"asset": …}`` lookups, and a deletion is not refused for references, because the
        caller checks the result against the exact document it expects."""
        if not isinstance(operations, list) or not operations or len(operations) > 4096:
            raise ToolError("BAD_REQUEST", "Expected a list of 1-4096 operations")
        doc = copy.deepcopy(self.doc)
        changes = {"created": [], "updated": [], "deleted": [], "project": []}
        self._literal = literal
        try:
            for index, op in enumerate(operations):
                if not isinstance(op, dict) or op.get("tool") not in allowed:
                    raise ToolError("UNKNOWN_TOOL", f"operations[{index}]: expected one of {', '.join(allowed)}")
                getattr(self, "_op_" + op["tool"])(doc, op, changes, index)
        finally:
            self._literal = False
        try:
            validate_document(doc)
        except ProjectFormatError as exc:
            raise ToolError("INVALID_RESULT", str(exc)) from exc
        return doc, changes

    def _find(self, doc, uid, index, op=None):
        """The asset an operation names: by ``uid``, or (models only) by ``"asset": "kind:id"``."""
        if uid is None and op is not None and not self._literal and isinstance(op.get("asset"), str):
            kind, _, object_id = op["asset"].partition(":")
            found = next((o for o in doc["objects"] if o["kind"] == kind and o["id"] == object_id), None)
            if found is None:
                raise ToolError("UNKNOWN_ASSET", f"operations[{index}]: no {kind} {object_id!r}")
            return found
        found = next((o for o in doc["objects"] if o["uid"] == uid), None)
        if found is None:
            raise ToolError("UNKNOWN_ASSET", f"operations[{index}]: no asset with uid {uid!r}")
        return found

    def _value(self, doc, value, index):
        return copy.deepcopy(value) if self._literal else self._resolve(doc, value, index)

    @staticmethod
    def _resolve(doc, value, index):
        """``{"asset": "item:ruby"}`` names an asset of the working copy; it becomes a uid reference."""
        if isinstance(value, dict) and set(value) == {"asset"}:
            kind, _, object_id = str(value["asset"]).partition(":")
            target = next((o for o in doc["objects"] if o["kind"] == kind and o["id"] == object_id), None)
            if target is None:
                raise ToolError("UNKNOWN_ASSET", f"operations[{index}]: no {kind} {object_id!r} to reference")
            return {"ref": target["uid"]}
        if isinstance(value, list):
            return [Session._resolve(doc, item, index) for item in value]
        if isinstance(value, dict) and not is_ref(value):
            return {k: Session._resolve(doc, v, index) for k, v in value.items()}
        return copy.deepcopy(value)

    def _op_create_asset(self, doc, op, changes, index):
        kind, object_id, props = op.get("kind"), op.get("id"), op.get("props", {})
        if not isinstance(props, dict):
            raise ToolError("BAD_REQUEST", f"operations[{index}]: props must be an object")
        uid = op.get("uid") or self._uid()
        if not is_uid(uid) or any(o["uid"] == uid for o in doc["objects"]):
            raise ToolError("BAD_REQUEST", f"operations[{index}]: uid must be a new lowercase UUID")
        doc["objects"].append({"uid": uid, "kind": kind, "id": object_id, "props": self._value(doc, props, index)})
        changes["created"].append({"uid": uid, "kind": kind, "id": object_id})

    def _op_update_asset(self, doc, op, changes, index):
        obj = self._find(doc, op.get("uid"), index, op)
        if "props" in op:  # every property at once (keeps the given key order)
            if not isinstance(op["props"], dict) or "set" in op or "unset" in op:
                raise ToolError("BAD_REQUEST", f"operations[{index}]: props must be an object, without set or unset")
            replaced = self._value(doc, op["props"], index)
            fields = sorted(k for k in set(replaced) | set(obj["props"]) if replaced.get(k) != obj["props"].get(k))
            obj["props"] = replaced
        else:
            patch, unset = op.get("set", {}), op.get("unset", [])
            if not isinstance(patch, dict) or not isinstance(unset, list):
                raise ToolError("BAD_REQUEST", f"operations[{index}]: set must be an object and unset a list")
            fields = sorted(set(patch) | set(unset))
            obj["props"].update(self._value(doc, patch, index))
            for key in unset:
                obj["props"].pop(key, None)
        fields = sorted(set(fields) | ({"id"} if "id" in op else set()))
        if "id" in op:  # a rename keeps the uid, so uid references follow it
            obj["id"] = op["id"]
        changes["updated"].append({"uid": obj["uid"], "kind": obj["kind"], "id": obj["id"], "fields": fields})

    # -- the editor's own operations (STUDIO_EDITS; literal values, exact results) ------------
    def _op_replace_asset(self, doc, op, changes, index):
        """Replaces a whole object in place: a changed kind, extra object fields or a new key order."""
        uid, value = op.get("uid"), op.get("object")
        if not isinstance(value, dict) or value.get("uid") != uid:
            raise ToolError("BAD_REQUEST", f"operations[{index}]: object must be the asset with uid {uid!r}")
        obj = self._find(doc, uid, index)
        doc["objects"][doc["objects"].index(obj)] = copy.deepcopy(value)
        changes["updated"].append({"uid": uid, "kind": value.get("kind"), "id": value.get("id"), "fields": ["*"]})

    def _op_set_project(self, doc, op, changes, index):
        value = op.get("project")
        if not isinstance(value, dict):
            raise ToolError("BAD_REQUEST", f"operations[{index}]: project must be an object")
        keys = sorted(k for k in set(value) | set(doc["project"]) if value.get(k) != doc["project"].get(k))
        doc["project"] = copy.deepcopy(value)
        changes["project"].append({"field": "project", "keys": keys})

    def _op_set_target(self, doc, op, changes, index):
        if "target" not in op:
            raise ToolError("BAD_REQUEST", f"operations[{index}]: target is required (null removes it)")
        if op["target"] is None:
            doc.pop("target", None)
        else:
            doc["target"] = copy.deepcopy(op["target"])
        changes["project"].append({"field": "target"})

    def _op_set_source_overrides(self, doc, op, changes, index):
        value = op.get("overrides")
        if value is not None and not isinstance(value, dict):
            raise ToolError("BAD_REQUEST", f"operations[{index}]: overrides must be an object (null removes them)")
        before = doc.get("source_overrides", {})
        if value is None:
            doc.pop("source_overrides", None)
            value = {}
        else:
            doc["source_overrides"] = copy.deepcopy(value)
        changes["project"].append({"field": "source_overrides",
                                   "keys": sorted(k for k in set(value) | set(before) if value.get(k) != before.get(k))})

    def _op_set_document_field(self, doc, op, changes, index):
        name = op.get("field")
        if not isinstance(name, str) or name in FIXED_FIELDS:
            raise ToolError("BAD_REQUEST", f"operations[{index}]: {name!r} cannot be set with set_document_field")
        if op.get("present", True):
            doc[name] = copy.deepcopy(op.get("value"))
        else:
            doc.pop(name, None)
        changes["project"].append({"field": name})

    def _op_reorder_assets(self, doc, op, changes, index):
        order = op.get("uids")
        by_uid = {o["uid"]: o for o in doc["objects"]}
        if not isinstance(order, list) or len(order) != len(by_uid) or set(order) != set(by_uid):
            raise ToolError("BAD_REQUEST", f"operations[{index}]: uids must list every asset exactly once")
        doc["objects"] = [by_uid[uid] for uid in order]
        changes["project"].append({"field": "order"})

    def _op_reorder_fields(self, doc, op, changes, index):
        order = op.get("fields")
        if not isinstance(order, list) or len(order) != len(doc) or set(order) != set(doc):
            raise ToolError("BAD_REQUEST", f"operations[{index}]: fields must list every document field exactly once")
        reordered = {name: doc[name] for name in order}
        doc.clear()
        doc.update(reordered)

    def _op_delete_asset(self, doc, op, changes, index):
        obj = self._find(doc, op.get("uid"), index, op)
        users = [] if self._literal else AssetGraph(doc).dependents(obj["uid"])
        if users:
            raise ToolError("IN_USE", f"operations[{index}]: {obj['kind']} {obj['id']} is used by {len(users)} asset(s); "
                                      "delete or change them first")
        doc["objects"].remove(obj)
        changes["deleted"].append({"uid": obj["uid"], "kind": obj["kind"], "id": obj["id"]})


def _validate(doc: dict) -> list[dict]:
    """Schema, references and the package generator; capability findings stay warnings here
    (authoring data is kept) and become export errors in the export gate."""
    from studio import create_project_files
    diagnostics = list(AssetGraph(doc).diagnostics())
    try:
        create_project_files(to_generator_request(doc))
    except (ValueError, KeyError, TypeError) as exc:
        diagnostics.append({"level": "error", "code": "GENERATOR_REJECTED", "message": str(exc)})
    for item in capability_check(doc)["diagnostics"]:
        diagnostics.append({**item, "level": "warning", "export_blocking": True})
    return diagnostics


class FixtureProvider:
    """A deterministic stand-in for a model: turns a structured request into tool operations.
    Live providers (Claude, compatible APIs, local models) implement the same ``propose`` and
    are added in HS-021, behind explicit consent before project data leaves the machine."""

    name = "fixture"

    INTENTS = ("material_set", "update")

    def propose(self, request: dict, context: dict) -> list[dict]:
        intent = request.get("intent")
        if intent == "update":  # change properties of one existing asset, named "kind:id"
            if not isinstance(request.get("asset"), str) or not isinstance(request.get("set"), dict):
                raise ToolError("BAD_REQUEST", "update needs an asset ('kind:id') and the properties to set")
            return [{"tool": "update_asset", "asset": request["asset"], "set": request["set"]}]
        if intent != "material_set":
            raise ToolError("UNSUPPORTED_REQUEST", f"The fixture provider only knows {', '.join(self.INTENTS)}")
        if not isinstance(request.get("material"), str):
            raise ToolError("BAD_REQUEST", "material_set needs a material id")
        material, label = request["material"], request.get("name", request["material"].replace("_", " ").title())
        block = f"{material}_block"
        return [
            {"tool": "create_asset", "kind": "block", "id": block, "props": {
                "name": f"Block of {label}", "template": request.get("block_template", "minecraft:iron_block"),
                "hardness": request.get("hardness", 4), "light": request.get("light", 0)}},
            {"tool": "create_asset", "kind": "item", "id": material, "props": {
                "name": label, "template": request.get("item_template", "minecraft:diamond"),
                "rarity": request.get("rarity", "common"), "max_stack_size": 64}},
            {"tool": "create_asset", "kind": "recipe", "id": block, "props": {
                "type": "shaped", "result": {"asset": f"block:{block}"}, "count": 1,
                "grid": [{"asset": f"item:{material}"}] * 9}},
            {"tool": "create_asset", "kind": "recipe", "id": f"{material}_from_block", "props": {
                "type": "shapeless", "result": {"asset": f"item:{material}"}, "count": 9,
                "grid": [{"asset": f"block:{block}"}] + [None] * 8}},
        ]


def run_request(session: Session, provider, request: dict, *, actor: str | None = None) -> Proposal:
    """Ask a provider for operations and return them as a proposal. A person (or an approved
    policy) commits it; the provider never mutates the project itself."""
    actor = actor or f"ai:{provider.name}"
    context = session.call("inspect_project", actor=actor)
    operations = provider.propose(request, context)
    return session.propose(operations, actor=actor, expected_revision=context["revision"])

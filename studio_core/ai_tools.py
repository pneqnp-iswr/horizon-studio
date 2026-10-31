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
    def propose(self, operations: list, *, actor: str, expected_revision: str) -> Proposal:
        """Plan ``operations`` on a copy and validate the result; nothing changes until commit."""
        self._expect(expected_revision, actor, "propose", operations)
        try:
            document, changes = self._plan(operations)
            diagnostics = _validate(document)
            errors = [d for d in diagnostics if d["level"] == "error"]
            if errors:
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
    def _plan(self, operations) -> tuple[dict, dict]:
        if not isinstance(operations, list) or not operations or len(operations) > 256:
            raise ToolError("BAD_REQUEST", "Expected a list of 1-256 operations")
        doc = copy.deepcopy(self.doc)
        changes = {"created": [], "updated": [], "deleted": []}
        for index, op in enumerate(operations):
            if not isinstance(op, dict) or op.get("tool") not in EDITS:
                raise ToolError("UNKNOWN_TOOL", f"operations[{index}]: expected one of {', '.join(EDITS)}")
            getattr(self, "_op_" + op["tool"])(doc, op, changes, index)
        try:
            validate_document(doc)
        except ProjectFormatError as exc:
            raise ToolError("INVALID_RESULT", str(exc)) from exc
        return doc, changes

    def _find(self, doc, uid, index):
        found = next((o for o in doc["objects"] if o["uid"] == uid), None)
        if found is None:
            raise ToolError("UNKNOWN_ASSET", f"operations[{index}]: no asset with uid {uid!r}")
        return found

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
        doc["objects"].append({"uid": uid, "kind": kind, "id": object_id, "props": self._resolve(doc, props, index)})
        changes["created"].append({"uid": uid, "kind": kind, "id": object_id})

    def _op_update_asset(self, doc, op, changes, index):
        obj = self._find(doc, op.get("uid"), index)
        patch, unset = op.get("set", {}), op.get("unset", [])
        if not isinstance(patch, dict) or not isinstance(unset, list):
            raise ToolError("BAD_REQUEST", f"operations[{index}]: set must be an object and unset a list")
        fields = sorted(set(patch) | set(unset) | ({"id"} if "id" in op else set()))
        obj["props"].update(self._resolve(doc, patch, index))
        for key in unset:
            obj["props"].pop(key, None)
        if "id" in op:  # a rename keeps the uid, so uid references follow it
            obj["id"] = op["id"]
        changes["updated"].append({"uid": obj["uid"], "kind": obj["kind"], "id": obj["id"], "fields": fields})

    def _op_delete_asset(self, doc, op, changes, index):
        obj = self._find(doc, op.get("uid"), index)
        users = AssetGraph(doc).dependents(obj["uid"])
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

    def propose(self, request: dict, context: dict) -> list[dict]:
        if request.get("intent") != "material_set":
            raise ToolError("UNSUPPORTED_REQUEST", "The fixture provider only knows the 'material_set' intent")
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

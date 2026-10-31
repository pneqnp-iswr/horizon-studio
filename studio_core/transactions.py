"""HS-020: one transaction model for the person and the AI Creator.

The core owns a project's canonical revision. Every change, a person's edit in the editor or an AI
proposal a person approved, is the same thing: typed operations (``studio_core.ai_tools``) applied
by one executor to the stored ``studio.project/1`` document, checked against a revision
precondition, saved through :class:`~studio_core.workspace.WorkspaceStore` and recorded in a
journal on disk, so undo and redo work across people, AI and restarts.

    Read -> Propose -> Preview diff -> Validate -> Approve -> Commit -> Persist -> Undo/Redo

* **Revision.** ``sha256`` of the canonical bytes (the same digest as the workspace store). A
  request names the revision it was made against; anything else is a conflict (409), never a
  silent overwrite.
* **Editor edits.** The editor sends the state it now holds and the revision it started from. The
  core turns the difference into operations (:func:`diff_documents`), applies them with the
  executor and checks that the result is byte for byte the document it was asked for, and that
  the inverse operations give back the previous document byte for byte. Only then does it save.
* **AI proposals.** A provider's operations are planned on a copy and validated strictly (a model
  must hand over a buildable project). They wait, in memory, for a person: approve commits them
  if the project is still at the proposal's revision (otherwise ``STALE_PROPOSAL``); reject
  drops them. Both are audited.
* **Journal.** ``<workspace>.journal.json`` next to the workspace: entries with their forward and
  inverse operations, a cursor, and an audit trail. Undo applies the inverse of the entry before
  the cursor, redo the operations after it; each step is verified against the recorded revisions.
  A new commit drops the redo steps. The journal is bounded (entries and bytes).
* **Crashes.** The workspace is written first, then the journal. On open, a journal that does not
  match the workspace is reconciled (the cursor moves to the matching entry, e.g. after a
  recovery from the backup copy) or, if nothing matches, reset; the document itself is never
  lost, and the response says what happened to the history.
* **Project identity.** A workspace is keyed by the mod ID; changing the ID starts another
  workspace (its own revision and history). History does not cross an ID change.
"""
from __future__ import annotations

import copy
import json
import threading
import time
import uuid

from studio_core.ai_tools import EDITS, STUDIO_EDITS, FixtureProvider, Session, ToolError, revision, run_request
from studio_core.migrate import upgrade
from studio_core.project_schema import ProjectFormatError, dumps
from studio_core.storage import atomic_write_bytes
from studio_core.workspace import WorkspaceConflict, WorkspaceNotFound, WorkspaceStore

JOURNAL_SCHEMA = "horizon-studio.journal/1"
ALL_EDITS = EDITS + STUDIO_EDITS
OBJECT_KEYS = ["uid", "kind", "id", "props"]
MAX_ENTRIES = 100
MAX_JOURNAL_BYTES = 4 * 1024 * 1024
MAX_AUDIT = 200
PROPOSAL_TTL = 30 * 60
MAX_PROPOSALS = 16
MAX_LABEL = 120
PROVIDERS = {"fixture": FixtureProvider}


class TransactionError(ToolError):
    """A refused request. ``status`` is the HTTP status the server answers with."""

    STATUS = {"REVISION_CONFLICT": 409, "STALE_PROPOSAL": 409, "HISTORY_DIVERGED": 409, "NOTHING_TO_UNDO": 409,
              "NOTHING_TO_REDO": 409, "UNKNOWN_PROPOSAL": 404, "NOT_FOUND": 404, "INTERNAL_MISMATCH": 500}

    def __init__(self, code: str, message: str, diagnostics: list | None = None, **details):
        super().__init__(code, message, diagnostics)
        self.status = self.STATUS.get(code, 400)
        self.details = details


def _same(a, b) -> bool:
    """Equal including key order (key order is part of the canonical bytes)."""
    return json.dumps(a, ensure_ascii=False, allow_nan=False) == json.dumps(b, ensure_ascii=False, allow_nan=False)


# -- the diff ---------------------------------------------------------------------------------
def diff_documents(before: dict, after: dict) -> list[dict]:
    """Operations that turn ``before`` into exactly ``after`` (``[]`` when they are identical).

    Order: created assets, updated assets, deleted assets, asset order, then document fields and
    their order. The service verifies every diff by applying it, so a gap here fails loudly."""
    ops: list[dict] = []
    old = {o["uid"]: o for o in before["objects"]}
    new = {o["uid"]: o for o in after["objects"]}
    for obj in after["objects"]:
        if obj["uid"] in old:
            continue
        ops.append({"tool": "create_asset", "uid": obj["uid"], "kind": obj["kind"], "id": obj["id"],
                    "props": copy.deepcopy(obj["props"])})
        if list(obj) != OBJECT_KEYS:
            ops.append({"tool": "replace_asset", "uid": obj["uid"], "object": copy.deepcopy(obj)})
    for obj in after["objects"]:
        prior = old.get(obj["uid"])
        if prior is None or _same(prior, obj):
            continue
        if list(obj) != OBJECT_KEYS or list(prior) != OBJECT_KEYS or prior["kind"] != obj["kind"]:
            ops.append({"tool": "replace_asset", "uid": obj["uid"], "object": copy.deepcopy(obj)})
            continue
        op = {"tool": "update_asset", "uid": obj["uid"]}
        if prior["id"] != obj["id"]:
            op["id"] = obj["id"]
        if not _same(prior["props"], obj["props"]):
            changed = {k: copy.deepcopy(v) for k, v in obj["props"].items()
                       if k not in prior["props"] or not _same(prior["props"][k], v)}
            removed = [k for k in prior["props"] if k not in obj["props"]]
            result = {**prior["props"], **changed}
            for key in removed:
                result.pop(key)
            if list(result) == list(obj["props"]):
                op.update({"set": changed} if changed else {})
                op.update({"unset": removed} if removed else {})
            else:
                op["props"] = copy.deepcopy(obj["props"])
        ops.append(op)
    for obj in before["objects"]:
        if obj["uid"] not in new:
            ops.append({"tool": "delete_asset", "uid": obj["uid"]})
    order = [o["uid"] for o in before["objects"] if o["uid"] in new] + \
            [o["uid"] for o in after["objects"] if o["uid"] not in old]
    if order != [o["uid"] for o in after["objects"]]:
        ops.append({"tool": "reorder_assets", "uids": [o["uid"] for o in after["objects"]]})

    if not _same(before["project"], after["project"]):
        ops.append({"tool": "set_project", "project": copy.deepcopy(after["project"])})
    keys = list(before)
    for name in dict.fromkeys(list(before) + list(after)):
        if name in ("format", "schema", "project", "objects"):
            continue
        present = name in after
        if (name in before) == present and (not present or _same(before[name], after[name])):
            continue
        value = copy.deepcopy(after.get(name))
        if name == "target":
            ops.append({"tool": "set_target", "target": value})
        elif name == "source_overrides":
            ops.append({"tool": "set_source_overrides", "overrides": value})
        else:
            ops.append({"tool": "set_document_field", "field": name, **({"value": value} if present else {"present": False})})
        if present and name not in keys:
            keys.append(name)
        elif not present:
            keys.remove(name)
    if keys != list(after):
        ops.append({"tool": "reorder_fields", "fields": list(after)})
    return ops


def describe(before: dict, after: dict) -> dict:
    """A reviewable diff: per asset what changed, with before and after values."""
    old = {o["uid"]: o for o in before["objects"]}
    new = {o["uid"]: o for o in after["objects"]}
    labels = {o["uid"]: f"{o['kind']}:{o['id']}" for o in [*before["objects"], *after["objects"]]}
    assets = []
    for uid in dict.fromkeys([*new, *old]):
        a, b = new.get(uid), old.get(uid)
        if b is None:
            assets.append({"change": "created", "uid": uid, "kind": a["kind"], "id": a["id"],
                           "fields": [{"path": k, "after": v} for k, v in a["props"].items()]})
        elif a is None:
            assets.append({"change": "deleted", "uid": uid, "kind": b["kind"], "id": b["id"],
                           "fields": [{"path": k, "before": v} for k, v in b["props"].items()]})
        elif not _same(a, b):
            fields = [{"path": "id", "before": b["id"], "after": a["id"]}] if a["id"] != b["id"] else []
            for key in dict.fromkeys([*a["props"], *b["props"]]):
                if key not in b["props"]:
                    fields.append({"path": key, "after": a["props"][key]})
                elif key not in a["props"]:
                    fields.append({"path": key, "before": b["props"][key]})
                elif not _same(a["props"][key], b["props"][key]):
                    fields.append({"path": key, "before": b["props"][key], "after": a["props"][key]})
            assets.append({"change": "updated", "uid": uid, "kind": a["kind"], "id": a["id"], "fields": fields})
    document = [name for name in dict.fromkeys([*before, *after]) if name != "objects"
                and not _same(before.get(name), after.get(name))]
    return {"assets": assets, "document": document, "labels": labels}


def _label(text, fallback: str) -> str:
    text = " ".join(str(text or "").split())[:MAX_LABEL]
    return text or fallback


def _summary(changes: dict) -> str:
    parts = []
    for key, word in (("created", "add"), ("updated", "change"), ("deleted", "remove")):
        names = [f"{c['kind']} {c['id']}" for c in changes.get(key, [])]
        if names:
            parts.append(f"{word} {', '.join(names[:3])}{' …' if len(names) > 3 else ''}")
    fields = sorted({c["field"] for c in changes.get("project", [])})
    if fields:
        parts.append("set " + ", ".join(fields))
    return "; ".join(parts) or "no change"


# -- the service ------------------------------------------------------------------------------
class ProjectService:
    """Transactions for the projects in one workspace folder. Thread-safe within a process."""

    def __init__(self, store: WorkspaceStore, *, clock=time.time, providers: dict | None = None, registry=None):
        self.store = store
        self.clock = clock
        self.providers = dict(PROVIDERS if providers is None else providers)
        self.registry = registry  # studio_core.providers.Providers: remote providers, consent, offline mode
        self.proposals: dict[str, dict] = {}
        self.cancels: dict[str, threading.Event] = {}
        self._lock = threading.RLock()

    # -- the journal ---------------------------------------------------------------
    def journal_path(self, project_id: str):
        primary, _ = self.store.paths(project_id)
        return primary.with_name(primary.name[: -len(".hstudio.json")] + ".journal.json")

    def _fresh(self, project_id: str, rev: str | None) -> dict:
        return {"schema": JOURNAL_SCHEMA, "project_id": project_id, "revision": rev, "cursor": 0, "entries": [],
                "audit": []}

    def _load(self, project_id: str, rev: str) -> tuple[dict, str | None]:
        """The journal for the workspace at ``rev`` and what had to be done to make them agree."""
        path = self.journal_path(project_id)
        try:
            journal = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        except (OSError, UnicodeError, ValueError):
            journal = {}
        if journal is None:
            return self._fresh(project_id, rev), None
        if not self._well_formed(journal, project_id):
            fresh = self._fresh(project_id, rev)
            self._audit(fresh, "system", "history_reset", reason="unreadable journal")
            return fresh, "reset"
        if journal["revision"] == rev:
            return journal, None
        # The workspace and the journal disagree (a crash between the two writes, or the workspace
        # came back from its backup copy). Move the cursor to the step that matches, if one does.
        entries = journal["entries"]
        states = [entries[0]["base_revision"]] + [e["result_revision"] for e in entries] if entries else []
        matches = [i for i, state in enumerate(states) if state == rev]
        if matches:
            journal["cursor"], journal["revision"] = matches[-1], rev
            self._audit(journal, "system", "history_reconciled", cursor=matches[-1])
            return journal, "reconciled"
        fresh = self._fresh(project_id, rev)
        fresh["audit"] = journal["audit"]
        self._audit(fresh, "system", "history_reset", reason="the workspace changed outside the journal")
        return fresh, "reset"

    @staticmethod
    def _well_formed(journal, project_id) -> bool:
        if not isinstance(journal, dict) or journal.get("schema") != JOURNAL_SCHEMA:
            return False
        if journal.get("project_id") != project_id or not isinstance(journal.get("entries"), list):
            return False
        cursor = journal.get("cursor")
        if not isinstance(cursor, int) or not 0 <= cursor <= len(journal["entries"]):
            return False
        if not isinstance(journal.get("audit"), list):
            return False
        keys = {"id", "actor", "label", "base_revision", "result_revision", "ops", "inverse"}
        if not all(isinstance(e, dict) and keys <= set(e) for e in journal["entries"]):
            return False
        return all(a["result_revision"] == b["base_revision"] for a, b in zip(journal["entries"], journal["entries"][1:]))

    def _save_journal(self, journal: dict) -> None:
        overflow = len(journal["entries"]) - MAX_ENTRIES
        if overflow > 0:
            del journal["entries"][:overflow]
            journal["cursor"] = max(0, journal["cursor"] - overflow)
        del journal["audit"][:-MAX_AUDIT]
        while True:
            raw = (json.dumps(journal, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
            if len(raw) <= MAX_JOURNAL_BYTES or not journal["entries"]:
                break
            if journal["cursor"] > 0:  # forget the oldest undo step first, then redo steps
                del journal["entries"][0]
                journal["cursor"] -= 1
            else:
                del journal["entries"][-1]
        atomic_write_bytes(self.journal_path(journal["project_id"]), raw)

    def _audit(self, journal: dict, actor: str, action: str, **details) -> None:
        journal["audit"].append({"at": self.clock(), "actor": actor, "action": action, **details})

    @staticmethod
    def _history(journal: dict) -> dict:
        entries, cursor = journal["entries"], journal["cursor"]
        view = lambda e: {"id": e["id"], "label": e["label"], "actor": e["actor"],
                          **({"approved_by": e["approved_by"]} if e.get("approved_by") else {})}
        return {"undo": [view(e) for e in reversed(entries[:cursor])], "redo": [view(e) for e in entries[cursor:]]}

    # -- reading -------------------------------------------------------------------------
    def _current(self, project_id: str) -> tuple[dict, dict, str | None, bool]:
        try:
            found = self.store.recover(project_id)
        except WorkspaceNotFound:
            raise TransactionError("NOT_FOUND", "No saved workspace exists for this project") from None
        journal, note = self._load(project_id, found["revision"])
        return found["document"], journal, note, found["recovered_from_backup"]

    def open(self, project_id: str) -> dict:
        with self._lock:
            doc, journal, note, from_backup = self._current(project_id)
            if note:
                self._save_journal(journal)
            return {"document": doc, "revision": journal["revision"], "recovered_from_backup": from_backup,
                    "history": self._history(journal), "history_note": note}

    def audit(self, project_id: str) -> list[dict]:
        with self._lock:
            return copy.deepcopy(self._current(project_id)[1]["audit"])

    # -- committing ----------------------------------------------------------------------
    def commit(self, document: dict, *, base_revision: str | None, actor: str = "editor",
               label: str | None = None) -> dict:
        """Make the project ``document``; ``base_revision`` is the revision the change started from
        (``None`` only for a project with no workspace yet)."""
        try:
            target = upgrade(document)
        except ProjectFormatError as exc:
            raise TransactionError("BAD_REQUEST", str(exc)) from exc
        project_id = target["project"]["id"]
        with self._lock:
            try:
                current, journal, _note, _backup = self._current(project_id)
            except TransactionError:
                if base_revision is not None:
                    raise TransactionError("REVISION_CONFLICT", "This project has no saved workspace any more",
                                           revision=None) from None
                saved = self._save(target, None)
                journal = self._fresh(project_id, saved["revision"])
                self._audit(journal, actor, "created", revision=saved["revision"])
                self._save_journal(journal)
                return self._result(target, journal, None)
            return self._apply_target(current, target, journal, base_revision=base_revision, actor=actor,
                                      label=label)

    def _apply_target(self, current, target, journal, *, base_revision, actor, label, approved_by=None,
                      extra_audit=None) -> dict:
        if base_revision != journal["revision"]:
            self._audit(journal, actor, "conflict", expected=base_revision, actual=journal["revision"])
            self._save_journal(journal)
            raise TransactionError("REVISION_CONFLICT", "The project changed since this editor read it",
                                   revision=journal["revision"])
        ops = diff_documents(current, target)
        if not ops:
            return self._result(current, journal, None)
        result, changes = self._run(current, ops, expect=target)
        inverse = diff_documents(result, current)
        self._run(result, inverse, expect=current)
        saved = self._save(result, journal["revision"])
        entry = {"id": uuid.uuid4().hex[:12], "actor": actor, "label": _label(label, _summary(changes)),
                 "at": self.clock(), "base_revision": journal["revision"], "result_revision": saved["revision"],
                 "changes": changes, "ops": ops, "inverse": inverse}
        if approved_by:
            entry["approved_by"] = approved_by
        del journal["entries"][journal["cursor"]:]
        journal["entries"].append(entry)
        journal["cursor"] = len(journal["entries"])
        journal["revision"] = saved["revision"]
        self._audit(journal, actor, "commit", entry=entry["id"], revision=saved["revision"], **(extra_audit or {}))
        self._save_journal(journal)
        return self._result(result, journal, entry)

    def _run(self, doc: dict, ops: list, *, expect: dict) -> tuple[dict, dict]:
        try:
            result, changes = Session(doc).plan(ops, allowed=ALL_EDITS, literal=True)
        except ToolError as exc:
            raise TransactionError(exc.code, str(exc), exc.diagnostics) from exc
        if dumps(result) != dumps(expect):
            raise TransactionError("INTERNAL_MISMATCH", "The operations did not produce the expected document; "
                                                        "nothing was saved")
        return result, changes

    def _save(self, doc: dict, expected: str | None) -> dict:
        try:
            return self.store.save(doc, expected_revision=expected)
        except WorkspaceConflict as exc:
            raise TransactionError("REVISION_CONFLICT", str(exc), revision=None) from exc
        except ValueError as exc:
            raise TransactionError("BAD_REQUEST", str(exc)) from exc

    def _result(self, doc: dict, journal: dict, entry: dict | None) -> dict:
        return {"document": doc, "revision": journal["revision"], "history": self._history(journal),
                "entry": None if entry is None else {k: entry[k] for k in ("id", "label", "actor", "changes")}}

    # -- undo and redo -----------------------------------------------------------------------
    def undo(self, project_id: str, *, expected_revision: str, actor: str = "editor") -> dict:
        return self._step(project_id, expected_revision, actor, back=True)

    def redo(self, project_id: str, *, expected_revision: str, actor: str = "editor") -> dict:
        return self._step(project_id, expected_revision, actor, back=False)

    def _step(self, project_id, expected_revision, actor, *, back: bool) -> dict:
        with self._lock:
            current, journal, _note, _backup = self._current(project_id)
            if expected_revision != journal["revision"]:
                raise TransactionError("REVISION_CONFLICT", "The project changed since this editor read it",
                                       revision=journal["revision"])
            cursor = journal["cursor"]
            if back and cursor == 0:
                raise TransactionError("NOTHING_TO_UNDO", "Nothing to undo")
            if not back and cursor == len(journal["entries"]):
                raise TransactionError("NOTHING_TO_REDO", "Nothing to redo")
            entry = journal["entries"][cursor - 1 if back else cursor]
            start, goal = (entry["result_revision"], entry["base_revision"]) if back else \
                (entry["base_revision"], entry["result_revision"])
            if start != journal["revision"]:
                raise TransactionError("HISTORY_DIVERGED", "The history no longer matches the project")
            try:
                result, _changes = Session(current).plan(entry["inverse" if back else "ops"], allowed=ALL_EDITS,
                                                         literal=True)
            except ToolError as exc:
                raise TransactionError("HISTORY_DIVERGED", f"The step cannot be replayed: {exc}") from exc
            if revision(result) != goal:
                raise TransactionError("HISTORY_DIVERGED", "Replaying the step did not give the recorded revision")
            saved = self._save(result, journal["revision"])
            journal["cursor"] = cursor - 1 if back else cursor + 1
            journal["revision"] = saved["revision"]
            self._audit(journal, actor, "undo" if back else "redo", entry=entry["id"], revision=saved["revision"])
            self._save_journal(journal)
            return {"document": result, "revision": saved["revision"], "history": self._history(journal),
                    "step": {"id": entry["id"], "label": entry["label"], "actor": entry["actor"]}}

    # -- AI proposals --------------------------------------------------------------------------
    def _expire(self) -> None:
        now = self.clock()
        for key in [k for k, p in self.proposals.items() if now - p["created_at"] > PROPOSAL_TTL]:
            del self.proposals[key]

    def cancel(self, request_id: str) -> bool:
        """Stops a provider call that is still running (between streamed events)."""
        event = self.cancels.get(request_id)
        if event is not None:
            event.set()
        return event is not None

    def _source(self, provider: str, cancel: threading.Event):
        if provider in self.providers:
            return self.providers[provider]()
        if self.registry is None:
            raise TransactionError("UNKNOWN_PROVIDER", f"No provider {provider!r} is configured")
        try:
            return self.registry.create(provider, cancel)
        except ToolError as exc:
            raise TransactionError(exc.code, str(exc)) from exc

    def propose(self, project_id: str, request: dict, *, provider: str = "fixture", base_revision: str,
                actor: str | None = None, request_id: str | None = None) -> dict:
        """Ask a provider for operations on the stored project; returns a proposal to review.

        A remote provider runs outside the lock (it can take a while); the result is checked against
        the revision again before it becomes a proposal."""
        if not isinstance(request, dict):
            raise TransactionError("BAD_REQUEST", "request must be an object")
        cancel = threading.Event()
        source = self._source(provider, cancel)
        actor = actor or f"ai:{source.name}"
        with self._lock:
            self._expire()
            current, journal, _note, _backup = self._current(project_id)
            if base_revision != journal["revision"]:
                raise TransactionError("REVISION_CONFLICT", "The project changed since this editor read it",
                                       revision=journal["revision"])
        if request_id:
            self.cancels[request_id] = cancel
        session = Session(current)
        try:
            proposal = run_request(session, source, request, actor=actor)
        except ToolError as exc:
            with self._lock:
                current, journal, _note, _backup = self._current(project_id)
                self._audit(journal, actor, "proposal_refused", code=exc.code)
                self._save_journal(journal)
            raise TransactionError(exc.code, str(exc), exc.diagnostics) from exc
        finally:
            if request_id:
                self.cancels.pop(request_id, None)
        with self._lock:
            current, journal, _note, _backup = self._current(project_id)
            if journal["revision"] != proposal.base_revision:
                self._audit(journal, actor, "proposal_refused", code="STALE_PROPOSAL")
                self._save_journal(journal)
                raise TransactionError("STALE_PROPOSAL", "The project changed while the provider was answering; "
                                                         "ask again", revision=journal["revision"])
            if len(self.proposals) >= MAX_PROPOSALS:
                oldest = min(self.proposals, key=lambda k: self.proposals[k]["created_at"])
                del self.proposals[oldest]
            key = uuid.uuid4().hex
            usage = getattr(source, "usage", None)
            self.proposals[key] = {"project_id": project_id, "actor": actor, "provider": source.name,
                                   "remote": bool(getattr(source, "remote", False)), "usage": usage,
                                   "base_revision": journal["revision"], "document": proposal.document,
                                   "operations": proposal.operations, "changes": proposal.changes,
                                   "diagnostics": proposal.diagnostics, "created_at": self.clock(),
                                   "request": copy.deepcopy(request)}
            self._audit(journal, actor, "proposed", proposal=key, operations=len(proposal.operations),
                        **({"usage": usage} if usage else {}))
            self._save_journal(journal)
            return self.proposal_view(key, current)

    def proposal_view(self, key: str, current: dict | None = None) -> dict:
        p = self.proposals[key]
        before = current if current is not None else self._current(p["project_id"])[0]
        return {"id": key, "project_id": p["project_id"], "actor": p["actor"], "provider": p["provider"],
                "simulated": p["provider"] == "fixture", "remote": p.get("remote", False), "usage": p.get("usage"),
                "base_revision": p["base_revision"],
                "result_revision": revision(p["document"]), "operations": copy.deepcopy(p["operations"]),
                "summary": _summary(p["changes"]), "changes": copy.deepcopy(p["changes"]),
                "diagnostics": copy.deepcopy(p["diagnostics"]), "diff": describe(before, p["document"]),
                "expires_at": p["created_at"] + PROPOSAL_TTL}

    def _take(self, project_id: str, key: str) -> dict:
        self._expire()
        p = self.proposals.get(key)
        if p is None or p["project_id"] != project_id:
            raise TransactionError("UNKNOWN_PROPOSAL", "No such proposal (expired, decided or never made)")
        return p

    def commit_proposal(self, project_id: str, key: str, *, expected_revision: str, approved_by: str = "editor") -> dict:
        """A person approves a proposal: it is committed only at the revision it was made for."""
        with self._lock:
            p = self._take(project_id, key)
            current, journal, _note, _backup = self._current(project_id)
            if p["base_revision"] != journal["revision"]:
                del self.proposals[key]
                self._audit(journal, approved_by, "stale_proposal", proposal=key, actor_of=p["actor"])
                self._save_journal(journal)
                raise TransactionError("STALE_PROPOSAL", "The project changed after this proposal was made; "
                                                         "ask again", revision=journal["revision"])
            result = self._apply_target(current, p["document"], journal, base_revision=expected_revision,
                                        actor=p["actor"], label=f"AI: {_summary(p['changes'])}",
                                        approved_by=approved_by, extra_audit={"proposal": key})
            del self.proposals[key]
            return result

    def reject(self, project_id: str, key: str, *, actor: str = "editor") -> dict:
        with self._lock:
            p = self._take(project_id, key)
            del self.proposals[key]
            _current, journal, _note, _backup = self._current(project_id)
            self._audit(journal, actor, "rejected", proposal=key, actor_of=p["actor"])
            self._save_journal(journal)
            return {"rejected": key, "revision": journal["revision"]}

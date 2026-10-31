# ADR 0003: The core owns project revisions; people and AI change projects through one transaction protocol

- **Status:** accepted (HS-020)
- **Date:** 2026-10-31
- **Deciders:** maintainer (repository owner) on the recommendation of this ADR
- **Builds on:** [ADR 0001](0001-canonical-project-document.md) (one canonical `studio.project/1` model) and
  [ADR 0002](0002-desktop-shell.md) (the editor and the Python core inside the desktop shell)

## Context

Up to Engineering Cycle 2 a project had two independent ways of changing:

| | The editor | The AI executor |
|---|---|---|
| State | the whole editor state in the page | `Session` over a canonical document, in memory |
| History | a local snapshot journal, lost on reload | a transaction list, lost when the process ends |
| Persistence | a debounced whole-state write with a revision check | none (CLI writes a new file) |
| Validation | the editor's own checks | schema, references, the package generator |

A person and an AI editing the same block had no shared revision, no shared undo and no shared audit. An AI change
could only reach the editor by replacing the whole state, which is exactly the "two sources of truth" problem HS-020
must remove.

## Decision

1. **The core owns each project's canonical document and revision** (SHA-256 of its canonical bytes, as already used by
   `WorkspaceStore`) and its history, in a journal on disk next to the workspace.
2. **Every change is a typed operation list run by one executor** (`studio_core.ai_tools.Session`):
   - a person's action becomes a commit; the core turns the editor's state into exact operations against the stored
     document (`studio_core.transactions.diff_documents`);
   - an AI request becomes a proposal, which a person approves or rejects.
   Undo and redo replay recorded inverse and forward operations.
3. **Every command names its base revision.** A mismatch is a 409 with a code (`REVISION_CONFLICT`, `STALE_PROPOSAL`),
   never a silent overwrite.
4. **Each step is proven before it is saved.** The forward operations must give the requested document byte for byte,
   and the inverse operations the previous one.
5. **The editor is a view and a command client.** It keeps a local history only while detached from a workspace
   (invalid ID, no core, an unresolved conflict).

The protocol, recovery rules and limits are specified in [TRANSACTIONS.md](../architecture/TRANSACTIONS.md).

## Options considered

| Option | Why not |
|---|---|
| Keep the editor's snapshots and let the AI send whole states | Two histories; an AI change is indistinguishable from a paste; no per-field review; undo of an AI change depends on which tab made it |
| The editor computes operations itself (a JavaScript diff) | Two implementations of the canonical model (JS and Python) must agree byte for byte; the core would still have to verify them |
| Event sourcing (the journal is the truth, the document a projection) | Larger change, migration of existing workspaces, and recovery would depend on replaying every event; the document-plus-journal design keeps the document authoritative and the journal disposable |
| A CRDT for live multi-tab editing | Studio is single-user and local; a revision check plus an explicit choice is honest and much smaller |

## Consequences

- Undo and redo survive a reload and a restart, and cover AI changes; one undo takes back a whole AI proposal.
- A second tab, a second window or a stale AI proposal cannot overwrite newer work.
- Unknown plugin objects, extra object fields, extensions, unknown document and project fields, effects and the engine
  target survive every step byte for byte (tested), because operations are literal and results are verified.
- Each user action is one small round trip to the local core (milliseconds); the editor queues them in order.
- A crash between the workspace write and the journal write can lose history, never the document, and the editor is
  told (`history_note`).
- Changing a mod ID starts another workspace; history does not cross it.

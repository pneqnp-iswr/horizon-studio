# Project transactions (HS-020)

A person editing a block in the workbench and the AI Creator changing that same block do the same thing: they send typed
operations to the core, which applies them to the canonical `studio.project/1` document with one executor, saves the
result and records it in one history. Decision record: [ADR-0003](../adr/0003-unified-transactions.md).

```
Read ─► Propose ─► Preview diff ─► Validate ─► Approve ─► Commit ─► Persist ─► Undo / Redo
 open    AI: provider ops          schema,     a person   revision   workspace   the shared journal
         editor: diff of its state references,  (AI only)  check +    + journal   (people and AI)
                                    generator               exact result
```

## Who owns what

| Thing | Owner | Where |
|---|---|---|
| The project document and its **revision** (SHA-256 of its canonical bytes) | the core | `WorkspaceStore`: `~/.horizon-studio/workspaces/<sha256(id)>.hstudio.json` and `.previous` |
| **History** (undo and redo steps, with their operations and inverses) and the **audit trail** | the core | `<sha256(id)>.journal.json` next to the workspace |
| Pending **AI proposals** | the core, in memory, 30 minutes, at most 16 | `ProjectService.proposals` |
| What is on screen, form fields, the selected tab | the editor | the page |
| A local history while **detached** (invalid mod ID, no core, an unresolved conflict) | the editor | `editor_history.js`, memory only |

There is one source of truth for a project: the core's document at its current revision. The editor is a view of
it plus a command client (`editor_workspace.js`). Its `localStorage` copy is a convenience cache for reloading a
page, never a second history.

## Operations

The executor is `studio_core.ai_tools.Session`. Models are offered `create_asset`, `update_asset` and `delete_asset`
(plus read-only tools). The editor's transactions also use operations that are **not offered to models**:
`replace_asset`, `set_project`, `set_target`, `set_source_overrides`, `set_document_field`, `reorder_assets` and
`reorder_fields`.

- **Literal operations.** An editor diff, an undo and a redo carry canonical values: no `{"asset": …}` lookups, so
  a plugin's value that happens to look like one is kept as it is.
- **Exact operations.** Key order is part of the canonical bytes, so the diff reproduces it, falling back to a whole
  `props` or a whole object when a patch would not.
- **Proven by test.** 300 seeded random edit pairs (with plugin objects, extra object fields, shuffled keys and removed
  fields) are checked both ways in `tests/test_transactions.py`.

## The command protocol

All commands are `POST` with the session token, the usual Host/Origin checks and JSON bodies. They answer the editor
state, the revision and the history (`{undo: [...newest first], redo: [...]}`; each step has `label`, `actor`, and
`approved_by` for AI steps).

| Command | Body | Notes |
|---|---|---|
| `/api/tx/open` | `project_id`, optional `state` | `matches` says whether the editor already holds exactly this project; `history_note` is `reconciled` or `reset` after a crash (below); 404 when there is no workspace yet |
| `/api/tx/commit` | `state`, `base_revision`, optional `label` | one user action. `base_revision: null` only creates a new workspace, and that first commit has no history step |
| `/api/tx/undo`, `/api/tx/redo` | `project_id`, `expected_revision` | move through the shared history |
| `/api/tx/history` | `project_id` | history plus the audit trail |
| `/api/ai/propose` | `project_id`, `base_revision`, `provider`, `request` | plans on a copy and validates strictly; returns the operations, a per-field diff (`before`/`after`), diagnostics, `simulated: true` for the fixture provider |
| `/api/ai/commit` | `project_id`, `proposal_id`, `expected_revision` | the person approves; committed only at the proposal's revision |
| `/api/ai/reject` | `project_id`, `proposal_id` | dropped and audited |
| `/api/workspace/write` | `state`, `expected_revision` | older clients: one more commit in the same journal, labelled *Workspace write* |
| `/api/workspace/recover` | `project_id` | read only |

Refusals carry a stable `code`:

| HTTP status | Codes | When |
|---|---|---|
| 409 | `REVISION_CONFLICT` | the response names the current revision |
| 409 | `STALE_PROPOSAL` | the proposal is dropped, not kept for later |
| 409 | `HISTORY_DIVERGED`, `NOTHING_TO_UNDO`, `NOTHING_TO_REDO` | — |
| 404 | `NOT_FOUND`, `UNKNOWN_PROPOSAL` | — |
| 400 | `UNKNOWN_PROVIDER`, `INVALID_RESULT`, `UNKNOWN_ASSET`, `IN_USE`, `BAD_REQUEST` | — |

## How a commit is checked

1. **Revision.** The request's base revision must be the stored revision; otherwise the answer is 409 and nothing is
   written.
2. **Diff.** The editor's state becomes a canonical document (`from_editor_state`), and `diff_documents(stored, target)`
   becomes operations. No difference means no step.
3. **Forward check.** The executor applies the operations to a copy. The schema is checked, and the result must be byte
   for byte the target document (`INTERNAL_MISMATCH` otherwise, and nothing is saved).
4. **Inverse check.** `diff_documents(result, stored)` is applied to the result and must give back the stored document
   byte for byte, so undo is proven before the step exists.
5. **Write.** The workspace is saved with the revision precondition (primary and previous copy, `fsync`), then the
   journal: the step is added, the redo steps are dropped and the cursor moves.

AI proposals are validated **strictly** before a person sees them: the schema, references, the package generator, and
engine capabilities as export-blocking warnings. A model must hand over a project that builds. The editor's own commits
are **lenient**: the schema is enforced and the other findings stay the editor's diagnostics, so a half-finished recipe
can be saved and undone.

## Undo, redo and grouping

- **One shared history.** Undo applies the inverse of the step before the cursor, redo the operations after it. A step
  is replayed only from its recorded revision and must reach its other recorded revision exactly; anything else is
  `HISTORY_DIVERGED` and nothing is written.
- **Steps from people and AI.** An approved AI proposal is one step, however many operations it has; one undo takes
  back the whole AI change. A person's action (adding an entry, a field's `change` event, applying a source override,
  choosing a target, an effect edit) is one step.
- **Replaying a step.** Redo replays the recorded operations, not the model's request, so the uids and the `.hmod` are
  the same as the first time.
- **Labels.** Steps carry a label, either the editor's or a summary such as "AI: add item topaz, block topaz_block".
- **Bounds.** At most 100 steps and 4 MiB of journal; the oldest undo steps go first.
- **Editor queue.** The editor sends commands one at a time, in order. If an undo answers after a newer edit was
  queued, the editor keeps showing the newer edit and the queued commit brings the core to it, so screen and disk
  agree.

## Conflicts between tabs and windows

Every command names the revision it was made against.
- **A stale command** (a second tab, another window, an AI proposal approved elsewhere) gets 409. The editor stops
  sending and shows **Restore disk** and **Keep editor**:
  - **Restore disk** loads the core's copy and history.
  - **Keep editor** commits the editor's state on top of the current revision as a normal step, which can be undone.
- **Returning to a tab** (`focus` or `visibilitychange`), the editor asks the core whether the project moved, so a
  change made elsewhere shows up before the next edit rather than after it.

## Crashes and recovery

- **Order of writes.** The workspace is written before the journal, each atomically.
- **Matching on open.** If the journal's revision is not the workspace's, the core looks for the history position that
  matches:
  - after a recovery from the `.previous` copy, the cursor moves back one step, and that step can be redone
    (`history_note: "reconciled"`);
  - if nothing matches (a crash between the two writes, or a file edited by hand), the history is reset, the document
    is kept, and the open reports `history_note: "reset"` and an audit record.
- **What can be lost.** A crash can lose history, never the saved document. An unreadable or inconsistent journal is
  treated the same way.

## Project identity

A workspace is keyed by the mod ID. Changing the ID starts another workspace with its own revision and history; the
previous ID's workspace stays on disk. History does not cross an ID change.

## Limits

- **One machine.** Revisions protect tabs and windows of one Studio core. Two cores sharing one `HORIZON_STUDIO_HOME`
  are protected by the revision check on each write, but there is no cross-process lock between that check and the
  write. This is not a multi-host store.
- **Proposals.** Pending proposals live in memory, so a restart drops them (they would be stale after any change
  anyway).
- **Old journals.** A journal step holds the operations needed to undo it, which can include large values (source
  overrides, effects). Only 4 MiB is kept.

## Tests

| What | Where |
|---|---|
| The 13 HS-020 acceptance steps, the journal, crashes, a tampered step, 300 random exact diffs, the HTTP protocol | `tests/test_transactions.py` |
| The editor's command client: chaining, undo/redo, late answers, conflicts, focus checks, project switches, AI approve/stale/reject | `tests/test_editor_workspace.cjs` |
| Real Chromium against the real core: undo/redo from buttons and shortcuts reach the disk and survive a reload; a stale tab gets a conflict; Keep editor | `tests/e2e/editor.e2e.cjs` |
| The same flows in the desktop window | `tests/desktop/desktop.e2e.cjs` |

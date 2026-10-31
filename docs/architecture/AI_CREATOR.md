# AI Creator architecture (HS-020, HS-021, HS-022)

**Principle:** AI and people edit the same canonical project with the same validated, reversible operations. A model
never writes project files, never bypasses validation and never approves native code.

```
request ──► provider (Claude | compatible API | local model | fixture) ──► typed operations
                                                                            │
                         Session (studio_core/ai_tools.py)                  ▼
  inspect/list/validate/capabilities/build ◄── read-only tools      propose(operations, expected_revision)
                                                                            │ plan on a copy: schema → references
                                                                            │ → package generator → capability notes
                                                                            ▼
                                     Proposal (changes preview, diagnostics) ──► person reviews
                                                                            │ commit(proposal, expected_revision)
                                                                            ▼
                     Transaction (base/result revision, inverse) ──► audit log ──► rollback_transaction
```

## Tool contract `horizon-studio.ai-tools/1`

| Tool | Effect | Notes |
|---|---|---|
| `inspect_project` | read | project metadata, target engine, counts per kind, revision, tool list |
| `list_assets` | read | uid, kind, id and props; optional kind filter |
| `inspect_capabilities` | read | the HS-008 check for the project's target engine |
| `validate_project` | read | references, the package generator and capability findings |
| `build_project` | read | builds the `.hmod` in memory and returns its SHA-256; refused when the target engine cannot load the project |
| `create_asset` | edit | kind, id, props; `{"asset": "kind:id"}` in props becomes a uid reference |
| `update_asset` | edit | `set`, `unset`, optional rename; uid references follow a rename |
| `delete_asset` | edit | refused while other assets use it |
| `rollback_transaction` | history | the newest live transaction first; restores the exact previous document |
| `export_package` | privileged | returns the package bytes only with `approved=True` from a person |

Not tools, by design: running shell commands, writing arbitrary files, building or running Rust. Native mods are built
only through HS-010's isolated, user-approved process; an AI tool can never approve Horizon's native-code trust boundary.

## Transactions

- **Revision preconditions.** `propose`, `commit` and `rollback` take `expected_revision` (SHA-256 of the canonical
  document). A stale caller gets `REVISION_CONFLICT`; a proposal made before another commit is `STALE_PROPOSAL`.
- **Preview before change.** A proposal lists created, updated and deleted assets with diagnostics; nothing changes
  until it is committed, and `cancel` discards it.
- **Validation.** Schema (`validate_document`), references (`AssetGraph`), the package generator (value ranges,
  templates) on the whole resulting document. Engine capability findings are warnings during editing (authoring data
  is kept) and errors at export.
- **Stable IDs.** New assets get UUIDs; references are by uid, so renames never break them.
- **Audit log.** Every call records sequence, time, actor (`human`, `ai:<provider>`), tool, a SHA-256 of the arguments,
  the outcome (`read`, `proposed`, `applied`, `rejected`, `cancelled`) and the revisions or refusal code. Arguments
  are hashed, not stored, so the log does not copy project content.
- **Determinism.** Equivalent canonical projects build identical packages: the fixture provider's Ruby set builds the
  exact bytes the official checker accepted (`ee3e1c87…`).

## One history with the editor (HS-020)

Proposals reach the editor through the core's transaction protocol ([TRANSACTIONS.md](TRANSACTIONS.md)), not as a
replacement of the editor's state:
- `/api/ai/propose` plans the provider's operations on a copy of the stored project and validates them strictly, and
  returns a per-field diff;
- `/api/ai/commit` commits them only at the revision they were made for (`STALE_PROPOSAL` otherwise);
- `/api/ai/reject` drops them.

An approved proposal is one step in the same journal as the person's edits, so one undo takes it back, after a restart
too. The journal records the resolved operations, so redo gives the same uids and the same `.hmod`.

## Providers and privacy (HS-021, planned)

- One interface, `propose(request, context) -> operations`. `FixtureProvider` is the deterministic reference used in
  tests and the CLI; live providers (Claude first, then other compatible APIs, optional local inference) live in their
  own module and never touch the project model directly.
- API keys go to the operating system's credential store, never into project files, workspace snapshots or Git.
- No project data leaves the machine without an explicit, per-provider authorization; an offline mode disables every
  network provider and Studio stays fully usable.
- Model choice is per project and per request; the audit log records the provider and model name.

## Using it today

```sh
python horizon_cli.py ai-apply project.hstudio.json --operations ops.json -o result.hstudio.json --audit audit.jsonl
```

`ops.json` is a list of edit operations, or `{"request": {"intent": "material_set", "material": "ruby"}}` for the
fixture provider. The input project is never modified; a refused transaction writes nothing.

## Roadmap

- HS-020 (in progress): this contract and executor, and one transaction protocol for the editor and AI proposals
  (`studio_core/transactions.py`). The editor routes its own edits, undo and redo through it. It is complete once the
  AI Creator panel drives the AI path in the browser end to end.
- HS-021: providers, credentials, consent and offline mode.
- HS-022: the AI Creator panel (proposal review, audit trail, approvals) and authoring across models, animation, VFX, entities, graphs and Rust, with validate-and-repair loops.
- HS-024: the live preview loop through the Preview Bridge (HS-023).

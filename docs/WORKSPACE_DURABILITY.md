# HS-006 — Durable local workspaces and Undo/Redo

> **Since HS-020** the core owns each project's revision and history: undo and redo are steps in a journal on disk
> (`<sha256(id)>.journal.json` next to the workspace), shared by the editor and approved AI proposals, and they survive
> a reload and a restart. Every edit is one transaction against a named revision. The protocol is in
> [architecture/TRANSACTIONS.md](architecture/TRANSACTIONS.md); this page describes the storage underneath it.

Undo/Redo cover add/edit/delete operations, recipe changes, applied Source Workbench overrides, the engine target,
effects and project metadata after a change event. Shortcuts: Ctrl/Cmd+Z to undo and Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y to
redo when focus is outside text fields and the source editor.

While the editor is not attached to a workspace (an invalid mod ID, no core, or a conflict not yet resolved), it keeps
a bounded local history of complete editor-state snapshots (`editor_history.js`), in memory only.

## Disk persistence

The localhost backend uses `WorkspaceStore` and `atomic_write_bytes` to maintain:

- `~/.horizon-studio/workspaces/<sha256(project-id)>.hstudio.json` — canonical current version
- the same filename with `.previous` — previous verified version

A new write first saves the last valid snapshot as backup, then atomically replaces the primary file (flush and fsync). A damaged current snapshot is recovered from the last good copy. Repeated valid saves of identical bytes do not rewrite the file.

The editor sends one transaction per action through `POST /api/tx/commit` (and `/api/tx/undo`, `/api/tx/redo`); `POST /api/tx/open` and `POST /api/workspace/recover` read a workspace for a specific mod ID. The older `POST /api/workspace/write` is kept for compatibility and is recorded in the same journal. Both endpoints inherit the existing Host/Origin/CSRF safeguards. The server does not accept arbitrary filesystem paths from the browser. Workspace filenames are opaque SHA-256 hashes of validated mod IDs.

Each write requires the exact revision hash previously returned by recovery or save. Concurrent changes cause **HTTP 409**, not last-write-wins. When the browser has a different version from the disk copy, it pauses autosave and presents **Restore disk** or **Keep editor**. Neither option is chosen automatically. Restore discards the editor's current copy, so download a separate project backup first if needed.

The most recent browser fallback is still kept in `localStorage` where supported. Browser storage can be smaller than the maximum project file size, so successful disk autosave is a separate status. Open Project / Save Project continue to import/download portable `.hstudio.json` files.

## Limits

- The snapshot store has one previous-good generation, not an unbounded revision history.
- Undo/Redo history is per mod ID: changing the ID starts another workspace. The journal keeps at most 100 steps (4 MiB); a crash between the workspace write and the journal write can lose history, never the document.
- Only one local Studio instance per server port is supported. The optimistic SHA-256 check protects different tabs/processes in ordinary use but is not a distributed multi-host lock.
- A manually corrupted current file and previous snapshot is an error; recovery never silently overwrites both.
- Security and simulated filesystem failure tests run in Python CI. The transaction service has Python integration tests on a real folder (`tests/test_transactions.py`); the local journal (`editor_history.js`) and the command client (`editor_workspace.js`) have Node 22 unit tests. Autosave, recovery in a fresh browser, revision conflicts and both conflict choices are exercised in Chromium by the browser E2E suite ([BROWSER_E2E.md](BROWSER_E2E.md)).

The snapshots are part of the author's private local machine and are not bundled with published game mods. No Minecraft or Horizon assets are copied.

Windows PyInstaller packages must include `editor_history.js` and the bundled launcher smoke test fetches it alongside other JS assets. An unmodified older executable cannot provide the new workspace UI; use a future release built from this source after QA.

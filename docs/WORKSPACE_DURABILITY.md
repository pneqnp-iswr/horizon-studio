# HS-006 — Durable local workspaces and Undo/Redo

The browser editor now records committed state changes using a bounded in-memory journal. Undo/Redo work for add/edit/delete operations, recipe changes, applied Source Workbench overrides and project metadata after a change event. Shortcuts: Ctrl/Cmd+Z to undo and Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y to redo when focus is outside text fields and the source editor.

The journal stores complete editor-state snapshots, preserving stable `uid` values and unknown plugin `carry` fields. It is memory-limited and **not persisted across app restarts**; the canonical project itself is saved on disk.

## Disk persistence

The localhost backend uses `WorkspaceStore` and `atomic_write_bytes` to maintain:

- `~/.horizon-studio/workspaces/<sha256(project-id)>.hstudio.json` — canonical current version
- the same filename with `.previous` — previous verified version

A new write first saves the last valid snapshot as backup, then atomically replaces the primary file (flush and fsync). A damaged current snapshot is recovered from the last good copy. Repeated valid saves of identical bytes do not rewrite the file.

The browser debounces edits and writes only through `POST /api/workspace/write`; `POST /api/workspace/recover` reads a workspace for a specific mod ID. Both endpoints inherit the existing Host/Origin/CSRF safeguards. The server does not accept arbitrary filesystem paths from the browser. Workspace filenames are opaque SHA-256 hashes of validated mod IDs.

Each write requires the exact revision hash previously returned by recovery or save. Concurrent changes cause **HTTP 409**, not last-write-wins. When the browser has a different version from the disk copy, it pauses autosave and presents **Restore disk** or **Keep editor**. Neither option is chosen automatically. Restore discards the editor's current copy, so download a separate project backup first if needed.

The most recent browser fallback is still kept in `localStorage` where supported. Browser storage can be smaller than the maximum project file size, so successful disk autosave is a separate status. Open Project / Save Project continue to import/download portable `.hstudio.json` files.

## Limits

- The snapshot store has one previous-good generation, not an unbounded revision history.
- In-memory Undo/Redo resets on project switch and app restart.
- Only one local Studio instance per server port is supported. The optimistic SHA-256 check protects different tabs/processes in ordinary use but is not a distributed multi-host lock.
- A manually corrupted current file and previous snapshot is an error; recovery never silently overwrites both.
- Security and simulated filesystem failure tests run in Python CI. The journal (`editor_history.js`) and the disk sync controller (`editor_workspace.js`) have Node 22 unit tests. Autosave, recovery in a fresh browser, revision conflicts and both conflict choices are exercised in Chromium by the browser E2E suite ([BROWSER_E2E.md](BROWSER_E2E.md)).

The snapshots are part of the author's private local machine and are not bundled with published game mods. No Minecraft or Horizon assets are copied.

Windows PyInstaller packages must include `editor_history.js` and the bundled launcher smoke test fetches it alongside other JS assets. An unmodified older executable cannot provide the new workspace UI; use a future release built from this source after QA.

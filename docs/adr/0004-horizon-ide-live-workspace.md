# ADR 0004 — Horizon IDE: a playable game and code/AI workbench in one window

- Date: 2026-11-01
- Status: **PROPOSED, not implemented**
- Scope: Horizon Studio desktop 0.8.x -> optional Horizon IDE workspace, Windows first
- Related existing tasks: HS-002, HS-020, HS-021, HS-023, HS-024, HS-033, HS-034

## User experience and truthful labels

One app window has a resizable **playable** Horizon game viewport (default 60% width) and a development pane (default 40%): source files, Monaco code editor, diagnostics, AI chat/proposals, build/test logs and a curated template picker. Keyboard and mouse game capture must be explicit; one shortcut returns focus to the editor. Preview worlds are isolated and disposable.

Primary loop: select template -> edit or ask AI -> inspect diff -> explicitly apply -> validate -> build/stage -> load/reload in preview -> assert actual game state -> inspect errors -> undo and retest. A code compilation may take time: never label builds as instant hot reload.

Do not present a screenshot stream as an interactive embedded game. A read-only screenshot is a legitimate **Preview**, but does not satisfy the playable single-window requirement.

## Reuse instead of rewrites

| Component | Existing source / upstream component | Missing capability |
| --- | --- | --- |
| Desktop shell | `desktop/` Tauri 2; already packaged as 0.8.0 | Native host region for a real rendering window |
| Project and history | `studio.project/1`, HS-020 unified transactions | Source-file revisions + template provenance; safe patch application |
| Content authoring | Existing .hmod generator, official checker, blocks, items, structures | Verified real game install/load/reload, not just static checker |
| AI | Existing AI Creator, permissions, provider choice, per-field diff, apply/undo, OS credential store | Source-code patch proposals with semantic diagnostics; tool sandbox; never direct model shell access |
| Game control | `studio_core/preview_bridge.py` + upstream `horizon-ctl` and its local control socket | Persistent session, assertions after each deploy, log/error capture |
| Code editor | **Monaco Editor** (MIT) | Rust/JSON syntax, files/tabs, diagnostics, optional rust-analyzer LSP |
| Templates | Existing Studio examples; upstream `cargo horizon-mod new --template content`; `horizon-native-mod-template` | Versioned vetted local template catalog with license and engine compatibility checks |

Never blindly migrate to VS Code/Electron. Retain the existing tested Tauri shell, Python core, and transaction layer. Use Monaco as a component, not as a whole second IDE.

## Game embedding — highest risk, prove first

Horizon is a native Rust game renderer, not an HTML component. A Tauri WebView cannot directly display a playable GPU surface inside a DOM node.

- **Windows feasibility spike:** prove a properly sized native child game HWND hosted within a native region of the app; test Win32 child window styles, cross-process reparenting/DPI, compositor, frame pacing, mouse capture, keyboard focus, resize and termination. `SetParent` is experimental, not guaranteed. Microsoft's documentation explicitly warns about DPI awareness across HWND trees: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setparent .
- **Better durable route:** request or implement a supported upstream Horizon host-window/render-surface interface, with clean game-engine lifecycle and defined input routing; avoid a fragile undocumented forced reparent as the sole path.
- **Fallback:** controlled external playable game window alongside a synchronized IDE. This is NOT the accepted single-window mode.
- Screenshots and `horizon-ctl` are for validation and noninteractive previews, not a substitute for user-playable rendering.
- Keep game and editor loops/processes isolated, IPC bounded, diagnostics asynchronous.

## Reload semantics: separate the fast paths

| Authoring mode | Correct deploy strategy | What the UI may promise |
| --- | --- | --- |
| Studio VFX preview | Update editor renderer | Interactive *Studio* preview, not in-game effect |
| Items/blocks/data .hmod | Validate/package, probe supported game reload, confirm with `horizon-ctl` | In-game iteration only if the pinned installed version proves it |
| Sandbox Wasm/code .hmod where supported | Compile, package, reload through verified dev mode | Measured build + reload |
| Native Rust .hnmod source mixin | Explicit trust approval, stage/compile the Horizon binary, restart isolated game | **Build and restart**, not runtime hot replacement |

Upstream `docs/mods.md` documents a Wasm `--dev-mod` workflow; the newer `docs/native-mods.md` documents source-mixin Rust native mods compiled into the client, with a roadmap toward replacing the former runtime. These docs describe different paths/states. Detect capabilities from the selected *real installed game build*; pin revisions and fail with an understandable error when incompatible.

References:
- https://github.com/horizon-rust/horizon/blob/main/docs/mods.md
- https://github.com/horizon-rust/horizon/blob/main/docs/native-mods.md
- https://github.com/horizon-rust/horizon/blob/main/docs/agent-control.md
- https://github.com/horizon-rust/horizon-native-mod-template
- https://microsoft.github.io/monaco-editor/

## Native code security

- AI responses are **untrusted proposals**. Source edits require reviewable diff and a revision precondition; changes join the same project journal, with Undo/Redo and audit metadata.
- Never let AI automatically approve privileged Rust mixins or execute arbitrary shell commands. Native mods run with full process/user privileges; obtaining trusted build permission must be an explicit human action.
- Build native mods in an isolated disposable workspace and start only owned game processes, separate from personal saved worlds. A build sandbox alone does not sandbox the final native game process.
- Do not download/bundle Minecraft game files, bypass authentication or inspect login tokens. The user must have a licensed compatible installation.
- Preserve Tauri origin/IPC allowlists and the existing preview evidence signatures.

## Executable milestones and acceptance tests

### IDE-001 — Authoritative real Horizon preview smoke (do FIRST)

Extend HS-002/023 instead of inventing another runner. On a user-authorized installed Horizon client with GPU and prepared licensed assets: launch an isolated world, stage an actual Studio content .hmod, query `horizon-ctl`, confirm a real exact item-inventory delta, record package SHA256/Horizon commit/launch API, close cleanly. Assertions MUST reject unsupported content, spoofed IDs and screenshot-only successes. Current repository only establishes this against fakes, not a real game.

### IDE-002 — Playable single-window embedding spike

Windows-only proof, feature flagged and off by default, no release promise. Can the player walk, aim, click, type and resize inside the Tauri window? Test dual-DPI monitors, focus capture/release, Alt+Tab, minimize, sleep/resume, HDR/graphics backend, session exit and 30-minute run. Abort unsafe reparent; document measured failures. Acceptance: **no independent top-level game window** and consistently interactive game viewport, not image frames.

### IDE-003 — IDE workbench and template gallery

Introduce Monaco, source tabs, status/terminal diagnostics, layout persistence and file tree without regressing legacy Studio screens. Template catalog: Studio content blocks/items/recipes/structures; official content starter; official native mod template. Every template stores upstream source/license/commit, API compatibility, output type and reproducible build/test recipe. Acceptance: instantiate/edit/save/reopen/build three template types in E2E; do not falsely label unsupported game features.

### IDE-004 — Fast content edit/reload/verify cycle

Persistent isolated game session. On Apply/Save, build project, compare package hash, use game hot-reload only after a genuine compatibility probe; otherwise restart the isolated session with progress UI. Machine-readable test output: game commit, action, expected value, observed value, pass/fail, duration, logs and screenshot as secondary evidence. Validate item changes and Undo roundtrip in a real client.

### IDE-005 — AI authoring and test loop

Build on HS-020/021 transactional AI. Source-code proposals are patch sets with file/path allowlist, expected revision, diff, validation and manual approve/reject; no silent code execution. CI includes malicious path attempts, stale patches, build errors, cancellation and rollback tests. Optional live model run is clearly distinguished from fixture simulations.

### IDE-006 — Native Rust editing

Offer official `horizon-native-mod-template` flow with rust-analyzer and compiler diagnostics. Cache builds when safe; show actual compilation/restart progress. Human-approved native trust boundary, isolated run and recovery. Test real hook behavior inside the game before claiming functional compatibility.

### IDE-007 — Other OSes

Use upstream native host API when feasible; evaluate Linux and macOS explicitly. Windows HWND experiments are not cross-platform solutions.

## Nonfunctional acceptance

- Existing .hstudio projects, .hmod byte reproducibility, core security, releases and E2E must not regress.
- Measure Save -> observed in-game result, build cache hit rate, crash recovery, input latency, FPS/frame time during editing, memory and reconnect reliability.
- Separate evidence stages: fixture/unit -> official checker -> desktop E2E -> real game-load -> actual gameplay assertion.
- No milestone is marked complete by this proposed architecture document.

**Decision requested for implementation:** start IDE-001 and IDE-002 in parallel as independent technical spikes; only then integrate the one-window IDE UI around the proven mechanism.

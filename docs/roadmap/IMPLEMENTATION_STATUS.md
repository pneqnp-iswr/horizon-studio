# Horizon Studio — Implementation Status

Last updated: 2026-10-31. Master before this update: `2f9f1bc` (PR #22). Roadmap data: [`roadmap.json`](roadmap.json) → [visual roadmap](../ROADMAP_VISUAL.md).

## Roadmap position

- **F0 — Foundation:** code complete; gate still lacks a real-game load record (HS-002 blocked on an authorized Horizon installation).
- **F1 — Project Core:** done — HS-005, HS-006, HS-007.
- **F2 — Creative Editor:** **HS-019 native desktop shell and workbench UI, partial** (slice A of the desktop transformation, PR #19). Missing: desktop release pipeline, an E2E run driving the shell's own window, a signing decision.
- **F3 — Visual Scripting (current):** **HS-008 engine capability registry — done** (CI run 41152431321, PR #22): registry with Horizon's API levels, two audited profiles (`d2186eb`, `3c1d4b39`), project target selection with comparison, editor and CLI export gates; the official checker runs once per profile in CI. **Active milestone: HS-020** (AI Creator tool contract), in progress: the contract `horizon-studio.ai-tools/1` and its transactional executor exist with deterministic tests and a CLI (`ai-apply`); still missing is the editor routing its own edits through the same executor.
- **Latest release: v0.7.0** (PR #15 → tag on `c816211`, run 41136925994): `HorizonStudio-0.7.0-Windows-x64.exe`, 12 170 186 bytes, SHA-256 `3f96e67154a09a6b292a3227c26369f9024d33d6158033d9a325c23b06fcf4b9`, unsigned; verified through the API. It stays the released product until the desktop build meets the gates in [ADR 0002](../adr/0002-desktop-shell.md).

## Roadmap v2 (engineering cycle 2)

- `roadmap.json` moved to schema `horizon-studio.roadmap/2`: every milestone has purpose and scope, deliverable,
  acceptance criteria, engine requirements, validation target and design reference in EN/RU; the validator also rejects
  dependency cycles, unknown engine requirements, *done* without evidence at its target, *done* while needing a missing
  engine contract, and showcase levels verified out of order. The old v1 data migrated with every status and evidence kept.
- New milestones HS-020 to HS-034 cover AI Creator, live preview, VFX, 3D editing and animation, entities and bosses,
  engine contracts, docking and the asset ecosystem; existing HS-009, HS-013 to HS-018 were expanded instead of duplicated.
  PixelChat is the separate experimental track PC-001 to PC-005 (epic #11, PC-001 from PR #20). Showcase SC-001
  *Crystal Titan* has five acceptance levels, all planned. Map: [CREATIVE_PLATFORM.md](CREATIVE_PLATFORM.md).
- The in-app Development journey shows the whole graph: nine phases with pixel icons, every milestone with search, status
  and track filters, dependencies and dependents, engine requirements, evidence and design links; a separate tab lists what
  the installed build supports, and another the showcase (`/api/journey`, schema `horizon-studio.journey/2`).
- Test counts in the documentation are generated from the tests (`scripts/test_inventory.py`).

## Desktop transformation (cycle 4, PR #19)

| Slice | State | Evidence |
|---|---|---|
| A: ADR, working desktop shell, pixel workbench, open/save, navigation, EN/RU, lifecycle, no browser, Windows packaging test | **done as a preview** | [ADR 0002](../adr/0002-desktop-shell.md); `desktop.yml` run 41143213331: NSIS install → smoke → uninstall, portable cold 3 239 ms / warm 928 ms to editor ready, ~350–370 MB process tree; Linux Xvfb smoke; `cargo test` + clippy; 19 browser E2E |
| B: parity (shell-driven E2E, release pipeline for desktop artifacts) | **in progress**: functional E2E on the real window, durable saves, Windows Rust tests; release pipeline next | `tests/desktop/desktop.e2e.cjs` ([inventory](../DESKTOP.md#desktop-e2e)), `desktop/src/files.rs` |
| C: docking, tabs, command palette | planned | — |
| D: engine-aware editing (target selection, graph IR) | started through HS-008 | — |
| E: 3D editing, Blockbench interchange | planned (HS-009) | — |

| ID | State | Evidence |
|---|---|---|
| HS-001 official `.hmod` checker | **done** (official-static) | PRs #3, #4, #6; CI run `41121633085`; [COMPATIBILITY_EVIDENCE.md](../COMPATIBILITY_EVIDENCE.md) |
| HS-002 real-game content smoke | **blocked** | Harness ready (PRs #5, #6), never run on a real game ([GAME_CONTENT_SMOKE.md](../GAME_CONTENT_SMOKE.md)) |
| HS-003 local API hardening | **done** | PR #1 |
| HS-004 release metadata | **done** | PR #2 |
| HS-005 project document + migration | **done** | PR #7; migrated fixtures pass the pinned checker (run `41124192941`) |
| HS-006 durable workspace + undo | **done** | PR #8 (Python fault injection, Node journal); PR #10 browser E2E: autosave, fresh-browser recovery, 409 conflicts, undo/redo |
| HS-007 browser E2E + UI modules | **done** | PR #10: 13 Chromium scenarios in CI; PR #14: `editor_model.js` and `editor_render.js` (state logic and card markup) join `editor_api.js`/`editor_workspace.js`, 22 Node tests; the inline script only wires the DOM |
| HS-008 engine capability registry | **done** | PR #16 (registry, CLI); PR #19 (API levels, editor card, export gate, journey; browser E2E) |
| HS-019 desktop shell + workbench UI | **partial** | PR #19; `desktop.yml` run 41143213331; [DESKTOP.md](../DESKTOP.md) |

## Compatibility status (by level)

- `unit`: Python 3.11/3.12 on Ubuntu and Windows; Node 22 editor-module tests.
- `official-static`: **pass** for all three examples and their `studio.project/1` migrations on Horizon `d2186eb9` (CI) and upstream `main` `3a5ac7ff` (local drift probe).
<!-- roadmap:e2e-count:start -->
- `browser-e2e`: **pass** — 24 scenarios on the current master (editor, workbench and roadmap explorer, PixelChat), Chromium on Ubuntu CI ([inventory](../BROWSER_E2E.md#current-inventory)). Firefox, WebKit and Windows browsers are not covered.
<!-- roadmap:e2e-count:end -->
- `desktop-smoke`: **pass** — the real desktop application starts, reports the editor ready and stops its core cleanly: Windows portable and installed (WebView2), Linux (WebKitGTK, Xvfb). This proves the shell, not game compatibility.
<!-- roadmap:desktop-e2e-count:start -->
- `desktop-e2e`: 8 functional scenarios that drive the real application window through tauri-driver: WebKitWebDriver on Linux, msedgedriver for WebView2 on Windows ([inventory](../DESKTOP.md#desktop-e2e)). They need a test build with the cargo feature `e2e`, which answers the Save dialog from the environment; packaged builds are checked not to have it.
<!-- roadmap:desktop-e2e-count:end -->
- `game-content-load`: **not verified** — needs a legally installed client, prepared resources and a GPU session (owner-run or self-hosted runner; decision pending).
- `gameplay`: **not verified**.

## Defects found and fixed in PRs #9–#10

- Windows ≤1100 px wide hid the whole project sidebar (mod metadata, Save/Open, Undo/Redo, export, workspace status); now a drawer from the rail with `aria-expanded` and Escape.
- Phones pushed the workspace into an off-screen grid column and hid the rail.
- No favicon (404 on every page load).
- Source Workbench listed identical file names (`ruby_block.json` ×5) and an untranslated status line.
- `keepEditor` failed when the disk copy disappeared during a conflict.

## Verification of this change (PR #19)

- Python: unit, API, launcher (core `--serve` protocol and EOF shutdown), journey, capability and desktop contract tests on 3.11/3.12, Ubuntu and Windows.
- Node: 28 tests (history, workspace, model, desktop bridge, workbench markup with both real catalogs).
- Browser E2E: 21/21 locally and in CI at the merge commit `dc1a936` (this line said 19 before; the two accessibility scenarios were added in the same PR).
- Rust: `cargo test` (7) and `cargo clippy -D warnings` on Linux.
- Desktop: `desktop.yml` builds the frozen core and checks its standalone smoke test (officially checked `.hmod` bytes), then installs, runs and uninstalls the NSIS build and runs the portable build three times on Windows; the frozen-core smoke test now also fetches every bundled asset and the journey data. It caught a real defect before release: the registry validation looked for documentation files that a frozen build does not contain.

## Known open issues

- The inline script still wires forms to the DOM (~170 lines); further UI work belongs to F2.
- Undo/Redo history is in memory only; one previous-good disk snapshot is kept.
- Windows EXE and the desktop preview are unsigned.
- The desktop shell's own window is exercised by smoke runs and scripted screenshots, not yet by a full E2E suite.

## Architectural decisions in force

- Evidence levels are separate (`unit`, `official-static`, `browser-e2e`, `game-load`, `gameplay`); none implies another.
- `docs/roadmap/roadmap.json` is the source of truth for the README roadmap images and tables (`scripts/roadmap.py`). Change a milestone's status only together with its evidence, in the same PR; `tests/test_roadmap.py` rejects contradictions and stale images.
- Editor modules are UMD files with injected IO (`editor_history.js`, `editor_workspace.js`) so they run in the browser and in Node tests; new modules must be added to `studio.py`'s script allowlist, `scripts/build_windows.py` and the launcher smoke test.
- Engine facts used by Studio are cited with the upstream file and pinned SHA `d2186eb9aa022a64a8b26e6989a04e44fba99ee7`.
- ADR-0001: one canonical `studio.project/1` document; editor state and generator request are derived views.

## Next recommended tasks

1. HS-019 slice B: drive the shell's own window in E2E (WebDriver for WebView2 / WebKitGTK) and add the desktop artifacts to the gated release pipeline; record a code-signing decision.
2. HS-008: let a project choose its target revision in the editor; add a profile for the next audited pin.
3. HS-009: Blockbench `.bbmodel` cuboid import with a loss report (F2); [research note](../research/EDITOR_ECOSYSTEM_COMPARISON.md).
4. HS-002: run the content-load harness on an authorized installation and record the result.

Do not treat a CI-only pass as real Horizon game compatibility.

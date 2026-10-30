# Horizon Studio — Implementation Status

Last updated: 2026-10-31. Master before this update: `366be4cf76cb79ac5d3c76305314f5350966e298` (PR #9). Roadmap data: [`roadmap.json`](roadmap.json) → [visual roadmap](../ROADMAP_VISUAL.md).

## Roadmap position

- **F0 — Foundation:** code complete; gate still lacks a real-game load record (HS-002 blocked on an authorized Horizon installation).
- **F1 — Project Core (current):** HS-005 and HS-006 done; **HS-007 in progress** — browser E2E delivered in PR #10, splitting the rest of the inline editor script remains.

| ID | State | Evidence |
|---|---|---|
| HS-001 official `.hmod` checker | **done** (official-static) | PRs #3, #4, #6; CI run `41121633085`; [COMPATIBILITY_EVIDENCE.md](../COMPATIBILITY_EVIDENCE.md) |
| HS-002 real-game content smoke | **blocked** | Harness ready (PRs #5, #6), never run on a real game ([GAME_CONTENT_SMOKE.md](../GAME_CONTENT_SMOKE.md)) |
| HS-003 local API hardening | **done** | PR #1 |
| HS-004 release metadata | **done** | PR #2 |
| HS-005 project document + migration | **done** | PR #7; migrated fixtures pass the pinned checker (run `41124192941`) |
| HS-006 durable workspace + undo | **done** | PR #8 (Python fault injection, Node journal); PR #10 browser E2E: autosave, fresh-browser recovery, 409 conflicts, undo/redo |
| HS-007 browser E2E + UI modules | **in progress** | PR #10: 13 Chromium scenarios in CI; `editor_workspace.js` and `editor_api.js` extracted with Node tests |

## Compatibility status (by level)

- `unit`: Python 3.11/3.12 on Ubuntu and Windows; Node 22 editor-module tests.
- `official-static`: **pass** for all three examples and their `studio.project/1` migrations on Horizon `d2186eb9` (CI) and upstream `main` `3a5ac7ff` (local drift probe).
- `browser-e2e`: **pass** — 13 scenarios, Chromium on Ubuntu CI ([BROWSER_E2E.md](../BROWSER_E2E.md)). Firefox, WebKit and Windows browsers are not covered.
- `game-content-load`: **not verified** — needs a legally installed client, prepared resources and a GPU session (owner-run or self-hosted runner; decision pending).
- `gameplay`: **not verified**.

## Defects found and fixed in PRs #9–#10

- Windows ≤1100 px wide hid the whole project sidebar (mod metadata, Save/Open, Undo/Redo, export, workspace status); now a drawer from the rail with `aria-expanded` and Escape.
- Phones pushed the workspace into an off-screen grid column and hid the rail.
- No favicon (404 on every page load).
- Source Workbench listed identical file names (`ruby_block.json` ×5) and an untranslated status line.
- `keepEditor` failed when the disk copy disappeared during a conflict.

## Verification of this change (PR #10)

- Python: 157 tests on 3.11 and 3.12 (local Linux) + CI matrix on Ubuntu and Windows.
- Node: 15 tests (`editor_history`, `editor_workspace`).
- Browser E2E: 13/13 locally (Chromium, Linux) and in the new GitHub Actions job (first green run on PR head `6dc6e61`); mutation-checked (breaking uid preservation fails the rename scenario).

## Known open issues

- The editor's inline script (`index.html`) still holds rendering, forms and recipe logic (~250 lines); continue the split under HS-007.
- Undo/Redo history is in memory only; one previous-good disk snapshot is kept.
- Windows EXE is unsigned and older than the features above; no release since 0.6.0.

## Architectural decisions in force

- Evidence levels are separate (`unit`, `official-static`, `browser-e2e`, `game-load`, `gameplay`); none implies another.
- `docs/roadmap/roadmap.json` is the source of truth for the README roadmap images and tables (`scripts/roadmap.py`). Change a milestone's status only together with its evidence, in the same PR; `tests/test_roadmap.py` rejects contradictions and stale images.
- Editor modules are UMD files with injected IO (`editor_history.js`, `editor_workspace.js`) so they run in the browser and in Node tests; new modules must be added to `studio.py`'s script allowlist, `scripts/build_windows.py` and the launcher smoke test.
- Engine facts used by Studio are cited with the upstream file and pinned SHA `d2186eb9aa022a64a8b26e6989a04e44fba99ee7`.
- ADR-0001: one canonical `studio.project/1` document; editor state and generator request are derived views.

## Next recommended tasks

1. HS-007 (finish): move recipe/entry rendering and form handling out of the inline script into modules with Node tests; keep the E2E suite green.
2. HS-008: engine capability registry per engine SHA, recorded in the project document (unblocks F3).
3. HS-009: Blockbench interchange with loss reports (F2).
4. HS-002: run the content-load harness on an authorized installation and record the result.

Do not treat a CI-only pass as real Horizon game compatibility.

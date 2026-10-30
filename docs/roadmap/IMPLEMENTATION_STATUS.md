# Horizon Studio — Implementation Status

Last updated: 2026-10-31. Verified master after PR #8: `496d7d93cfb84fddd747114cae2a10a05c2d4aa7`.

## Roadmap position

- Phase: **F0 / Iteration I — Verified Mod Compatibility & Security**, all code deliverables merged; the F0 gate still lacks a real-game load record (HS-002 evidence).
- Current phase: **F1 / Iteration II — Project Graph, Durability**. HS-005 delivered in PR #7; HS-006 disk-backed workspace and browser history delivered in PR #8, with browser E2E still pending.

| ID | State | Evidence |
|---|---|---|
| HS-003 local API hardening | **done** | PR #1 → `36c3bb6`; API security tests in CI |
| HS-004 release metadata | **done** | PR #2 → `6c61770`; `scripts/check_release_metadata.py` in tests |
| HS-001 official `.hmod` checker | **done (official-static level)** | PR #3 adapter → `3ed765a`; PR #4 pinned CI → `b38b95c`; PR #6 checks every example → `156192d` (CI run `41121633085`). Real `cargo-horizon-mod` built from `d2186eb` accepted all three examples; see [COMPATIBILITY_EVIDENCE.md](../COMPATIBILITY_EVIDENCE.md) |
| HS-002 real-game content smoke | **harness ready, never run on a real game** | PR #5 → `cfab21b`; PR #6 → `156192d` makes the launch self-exiting (`--frames`, `--smoke-report`, `--home`) and corroborates files byte for byte ([GAME_CONTENT_SMOKE.md](../GAME_CONTENT_SMOKE.md)) |
| HS-005 project document + migration | **done** (PR #7; CI on the PR) | `studio_core/` — `studio.project/1` with stable UIDs and UID references, migration from schemas 2–4 with golden fixtures and byte-identical `.hmod`, `AssetGraph`, atomic writes; CLI `migrate`/`graph`; editor open/save via `/api/project/open` and `/api/project/save`. [PROJECT_FORMAT.md](../PROJECT_FORMAT.md), [ADR-0001](../adr/0001-canonical-project-document.md) |
| HS-006 durable workspace + undo | **implemented (browser E2E pending)** | PR #8 → `496d7d9`: `studio_core/workspace.py`, `/api/workspace/write` and `/api/workspace/recover`, optimistic revision checks, previous-good backup and crash recovery, browser Undo/Redo and explicit overwrite choice; [WORKSPACE_DURABILITY.md](../WORKSPACE_DURABILITY.md). Python/Node CI 41128196057; official checker 41128196066. |

## Compatibility status (by level)

- `official-static`: **pass** for `ruby_demo`, `workshop_showcase`, `voxel_showcase` on Horizon `d2186eb9` (CI run `41121633085`, all three; also local) and on upstream `main` `3a5ac7ff` (local drift probe). Their `studio.project/1` migrations build identical bytes and are checked by the same workflow.
- `game-content-load`: **not verified**. Requires a legally installed client, prepared resources and a GPU/desktop session — unavailable in public CI and in the cloud development container. Needs an owner-run or a dedicated self-hosted runner (decision pending with the project owner).
- `gameplay`: **not verified**.

## Defects fixed this cycle

- HS-002 harness (PR #6): no exit condition for the interactive client (every run timed out); `ModuleNotFoundError` when run as documented; stale resource-root files counted as evidence.
- CLI dropped editor `source_overrides`, so CLI builds differed from editor exports (HS-005; regression test in `tests/test_project_migration.py`).
- Windows builds wrote different `.hmod` bytes than Linux (`zipfile` "made by" field defaults to MS-DOS on Windows), so packages exported by the Windows EXE were not the officially checked bytes. Found by the new hash assertions failing only on Windows CI; fixed by pinning the field, with a test that simulates the Windows default on every OS.
- At 1280×720 and other viewports under ~900 px high the editor form squeezed the entry list to zero height, so entries could not be opened or deleted (found by the browser check below; fixed with a short-viewport layout rule).

## Verification of PR #7

- Unit/integration: `python -m unittest discover -s tests` — 135 tests pass locally on Python 3.11, 3.12 and 3.13 (Linux); CI matrix on the PR covers Ubuntu/Windows × 3.11/3.12.
- Official checker (local, `d2186eb`): 3 legacy examples + 3 migrated `studio.project/1` fixtures pass with identical hashes.
- Browser (local, Playwright + Chromium, not yet in CI): demo → save produces `studio.project/1`; renaming an item keeps its `uid` and recipe references; new objects get UUIDv4; opening the schema-2 example shows the migration notice; exported `.hmod` SHA-256 `ee3e1c87…` equals the officially checked package; Russian status text; no page errors.

## Known open issues

- Browser UI has no automated E2E tests in CI (C-09 / HS-007); the HS-005 browser check was run manually.
- Undo/Redo history is in-memory and resets on restart; one previous-good disk snapshot is retained. Browser now uses debounced disk autosave with explicit conflict resolution (HS-006). Full browser E2E is not yet automated (HS-007).
- Windows EXE is unsigned; manual desktop acceptance not recorded.

## Architectural decisions in force

- Evidence levels are separate fields (`unit`, `official-static`, `game-content-load`, `gameplay`); none implies another.
- Engine facts used by Studio (CLI flags, log lines, file layout) are cited with the upstream file and pinned SHA; re-check them when the pin moves.
- The pinned engine revision stays `d2186eb9aa022a64a8b26e6989a04e44fba99ee7` until a deliberate pin update with fresh evidence.
- `docs/roadmap/roadmap.json` is the source of truth for the README roadmap images and tables (`scripts/roadmap.py`). Change a milestone's status only together with its evidence, in the same PR; `tests/test_roadmap.py` rejects contradictions and stale images.
- ADR-0001: one canonical `studio.project/1` document; editor state and generator request are derived views; every entry point reads through `studio_core.migrate.upgrade`. Migrated projects must build byte-identical packages.

## Next recommended tasks

1. HS-007: browser Playwright E2E in CI, covering Undo/Redo, autosave/recover, EN/RU, source overrides, migrations and `.hmod` export; modularize the monolithic UI.
2. HS-006 refinement: typed `Command.apply/revert` operations over canonical `studio.project/1`, transaction grouping and longer-lived checkpoints where justified. Current editor history uses bounded full-state snapshots.
3. HS-008: capability registry per engine SHA, recorded in the project document.
4. HS-002 evidence: run the harness on an authorized installation and add the result to the ledger.

Do not treat a CI-only pass as real Horizon game compatibility.

## HS-006 delivery (PR #8)

- Merged commit: `496d7d93cfb84fddd747114cae2a10a05c2d4aa7`; tests and compatibility checks succeeded at the corresponding PR head `490b8185990a700ce27707e9ac4ec743fd815b13`.
- Python: 143 tests per runner, Python 3.11/3.12 on Ubuntu/Windows. JavaScript: 7 Node 22 tests. GitHub Actions CI run `41128196057`.
- Official pinned Horizon `.hmod` checker: success in GitHub Actions run `41128196066`, not a game-client execution.
- Workspace persistence: per-project hashed paths in `~/.horizon-studio/workspaces`, atomic primary/previous backup, recovery, and explicit 409 conflicts. UI: Undo/Redo, debounced local autosave, manual disk-vs-browser choice.
- Not yet verified: actual in-browser Playwright end-to-end actions, real-game load, Windows frozen executable rebuilt with new code. No version bump and no new Windows release.

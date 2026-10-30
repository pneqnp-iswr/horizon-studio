# Horizon Studio — Implementation Status

Last updated: 2026-10-30. Master before this update: `cfab21b4ffaf3d3584ce09b3cc0334f815963c09`.

## Roadmap position

- Phase: **F0 / Iteration I — Verified Mod Compatibility & Security**, all code deliverables merged; the F0 gate still lacks a real-game load record (HS-002 evidence).
- Next phase in progress: **F1 / Iteration II — Project Graph, Durability** (HS-005 next).

| ID | State | Evidence |
|---|---|---|
| HS-003 local API hardening | **done** | PR #1 → `36c3bb6`; API security tests in CI |
| HS-004 release metadata | **done** | PR #2 → `6c61770`; `scripts/check_release_metadata.py` in tests |
| HS-001 official `.hmod` checker | **done (official-static level)** | PR #3 adapter → `3ed765a`; PR #4 pinned CI → `b38b95c`. Real `cargo-horizon-mod` built from `d2186eb` accepted all three examples; see [COMPATIBILITY_EVIDENCE.md](../COMPATIBILITY_EVIDENCE.md) |
| HS-002 real-game content smoke | **harness ready, never run on a real game** | PR #5 → `cfab21b`; follow-up fixes the launch so the game exits by itself and corroborates files byte for byte ([GAME_CONTENT_SMOKE.md](../GAME_CONTENT_SMOKE.md)) |
| HS-005 project graph v1 + schema-3 migration | next | — |

## Compatibility status (by level)

- `official-static`: **pass** for `ruby_demo`, `workshop_showcase`, `voxel_showcase` on Horizon `d2186eb9` (CI run `41100332672` for ruby; local for all) and on upstream `main` `3a5ac7ff` (local drift probe).
- `game-content-load`: **not verified**. Requires a legally installed client, prepared resources and a GPU/desktop session — unavailable in public CI and in the cloud development container. Needs an owner-run or a dedicated self-hosted runner (decision pending with the project owner).
- `gameplay`: **not verified**.

## Known defects fixed in the HS-002 follow-up

- The merged harness launched `horizon-client --dev-mod <file>` without `--frames`; the client is an interactive game, so every run ended in the harness timeout (`indeterminate`).
- `python scripts/game_content_smoke.py` failed with `ModuleNotFoundError: horizon_cli` when run from the repository root as documented.
- The resource-root check accepted any `*.json` under `data/<id>/`, including stale files from older builds.

## Known open issues

- `horizon_cli.load_project` drops `source_overrides`, so a project saved by the editor with JSON overrides builds a different `.hmod` from the CLI than from the editor (to be fixed with HS-005 migration).
- Browser UI has no automated E2E tests (C-09 / HS-007).
- Windows EXE is unsigned; manual desktop acceptance not recorded.

## Architectural decisions in force

- Evidence levels are separate fields (`unit`, `official-static`, `game-content-load`, `gameplay`); none implies another.
- Engine facts used by Studio (CLI flags, log lines, file layout) are cited with the upstream file and pinned SHA; re-check them when the pin moves.
- The pinned engine revision stays `d2186eb9aa022a64a8b26e6989a04e44fba99ee7` until a deliberate pin update with fresh evidence.

## Next recommended tasks

1. HS-005: canonical project document v1 with stable object IDs and reference-based recipes; migration from `.hstudio.json` schemas 2–4 with golden fixtures; identical `.hmod` bytes for migrated projects; fix the `source_overrides` loss.
2. HS-006: atomic workspace save, backups and undo journal on top of HS-005.
3. HS-007: split `index.html`, Playwright smoke suite (EN/RU, save/import, export).
4. HS-002 evidence: run the harness on an authorized installation and add the result to the ledger.

Do not treat a CI-only pass as real Horizon game compatibility.

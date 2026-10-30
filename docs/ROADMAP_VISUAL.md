# Horizon Studio — Development Journey

<p align="center">
  <img src="../assets/roadmap/roadmap-overview.svg" alt="Development journey from F0 Foundation to F8 Creative Platform with derived phase statuses and verification levels" width="100%" />
</p>

<p align="center">
  <img src="../assets/roadmap/current-phase.svg" alt="Current phase card with its milestones and their verified status" width="100%" />
</p>

This page and both images are generated from [`docs/roadmap/roadmap.json`](roadmap/roadmap.json), which follows the phases and backlog of the [Master Engineering Roadmap](roadmap/master-2026-10-30.md). Day-to-day engineering notes live in [IMPLEMENTATION_STATUS.md](roadmap/IMPLEMENTATION_STATUS.md).

## How to read it

| Mark | Milestone meaning | Requirement checked by `scripts/roadmap.py` |
|---|---|---|
| **Done** (gold) | Implemented and its acceptance evidence exists | At least one non-documentation evidence link; every dependency done |
| **Partially verified** (half gold) | Implemented, some acceptance evidence missing | Evidence links plus a `missing` note |
| **In progress** (cyan) | Being built now | Only in the current phase; dependencies started |
| **Blocked** (red) | Cannot be verified because of an outside dependency | A `blocker` note |
| **Planned** (stone) | Scheduled, not started | — |

A **phase** is *done* when all of its milestones are done, *in progress* when it is the current phase, *partially verified* when work started but is incomplete, otherwise *planned*. Counts such as `3/4 DONE` are the only numbers shown; there are no estimated percentages.

The **verification levels** at the bottom of the map are separate evidence: unit/CI tests, the official `cargo-horizon-mod` static check, browser end-to-end tests, loading in a real Horizon client, and gameplay. A level can only be *verified* when every level below it is.

"Rust tooling" is not a separate phase in the master roadmap: the Rust editor bridge (HS-011) belongs to F2 and native `.hnmod` builds (HS-010) to F3. F6 and F8 have no backlog tickets yet.

## Updating

1. Edit `docs/roadmap/roadmap.json` in the same pull request as the code and tests that justify the change. Link evidence (pull requests, CI runs, documents in this repository).
2. Run `python scripts/roadmap.py` to regenerate the images, this page's table and the status tables in both READMEs.
3. `tests/test_roadmap.py` rejects unknown statuses, duplicate or missing IDs, references to missing milestones or phases, contradictory states (for example *done* depending on *planned*), missing evidence, and stale generated files.

## Phases and milestones

<!-- roadmap:details:start -->
### F0 — Foundation · Partially verified

Official validator, secure local API, release metadata, real-game smoke harness.  
**Gate:** A generated .hmod passes the official checker AND loads in a real game.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-001 Official .hmod checker with pinned engine | Done | — | official-static: [PR #4, #6; CI run 41121633085](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41121633085)<br>docs: [Compatibility evidence ledger](../docs/COMPATIBILITY_EVIDENCE.md) |  |
| HS-002 Real-game content-load smoke | Blocked | HS-001 | unit: [Harness + fake-client contract tests, PR #6](https://github.com/pneqnp-iswr/horizon-studio/pull/6)<br>docs: [Game content smoke procedure](../docs/GAME_CONTENT_SMOKE.md) | Needs a legally installed Horizon client, prepared resources and a GPU session; harness ready (PR #5, #6), never run on a real game |
| HS-003 Local API threat hardening | Done | — | unit: [PR #1, API security tests](https://github.com/pneqnp-iswr/horizon-studio/pull/1) |  |
| HS-004 Release metadata consistency | Done | — | unit: [PR #2, release metadata check](https://github.com/pneqnp-iswr/horizon-studio/pull/2) |  |

### F1 — Project Core · Done

Canonical project document, migrations, durable workspace, undo, browser E2E.  
**Gate:** Import old project, edit, crash, recover, identical output.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-005 Canonical studio.project/1 + migration | Done | — | unit: [PR #7: golden migrations, byte-identical .hmod](https://github.com/pneqnp-iswr/horizon-studio/pull/7)<br>official-static: [Migrated fixtures pass the pinned checker](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41124192941)<br>docs: [Project format](../docs/PROJECT_FORMAT.md) |  |
| HS-006 Durable workspace, undo/redo, recovery | Done | HS-005 | browser-e2e: [PR #10: autosave, fresh-browser recovery, 409 conflicts, undo/redo in Chromium](https://github.com/pneqnp-iswr/horizon-studio/pull/10)<br>unit: [PR #8; CI run 41128196057 (Python + Node)](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41128196057)<br>docs: [Workspace durability](../docs/WORKSPACE_DURABILITY.md) |  |
| HS-007 Browser E2E in CI + UI modules | Done | HS-006 | browser-e2e: [PR #10: 13 Chromium scenarios in CI; workspace sync and API client extracted](https://github.com/pneqnp-iswr/horizon-studio/pull/10)<br>unit: [PR #14: editor_model.js and editor_render.js extracted with Node tests; inline script reduced to DOM wiring](https://github.com/pneqnp-iswr/horizon-studio/pull/14)<br>docs: [Browser E2E scope and limits](../docs/BROWSER_E2E.md) |  |

### F2 — Creative Editor · Planned

Modular UI, docking, search, 3D selection, Blockbench interchange, Rust code bridge (HS-011).  
**Gate:** Edit a Rust file with diagnostics; model round-trip with a declared loss report.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-009 Blockbench adapter with loss reports | Planned | HS-005 | — |  |
| HS-011 Monaco + rust-analyzer + Cargo | Planned | HS-007 | — |  |

### F3 — Visual Scripting · In progress

Capability registry, typed graph IR, .hmod and trusted native .hnmod backends (HS-010).  
**Gate:** One graph builds a native mod only on a supported hook contract.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-008 Engine capability registry per SHA | In progress | HS-005 | — | **Active.** |
| HS-010 Trusted native .hnmod build | Planned | HS-008 | — |  |
| HS-012 Gameplay IR v1 + event graph | Planned | HS-008 | — |  |

### F4 — Gameplay Systems · Planned

Entities, components, AI behaviour trees, events, RPG and automation.  
**Gate:** A smart animal or boss in game with persistence and sync.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-014 AI behaviour trees with budgets | Planned | HS-012 | — |  |

### F5 — World & VFX · Planned

Shader graph over .hshader, particles, physics sandbox, dimensions.  
**Gate:** A visual effect scales across quality profiles; gameplay damage stays independent.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-013 .hshader checker + shader graph | Planned | HS-008 | — |  |
| HS-015 Physics sandbox with debug overlay | Planned | HS-012 | — |  |
| HS-016 Dimension and noise editor | Planned | HS-008 | — |  |

### F6 — Engine Bridge · Planned

Upstream-accepted engine capabilities: entities, server events, worldgen, physics, rendering.  
**Gate:** Real engine integration matrix with no undocumented patches.

_No backlog tickets yet; this phase depends on earlier phases and upstream engine work._

### F7 — Ecosystem · Planned

Secure plugin SDK, templates, signed releases, publishing.  
**Gate:** A third party adds a new asset type and editor without core edits.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-017 Secure plugin host SDK | Planned | HS-007, HS-008 | — |  |
| HS-018 Community publishing | Planned | HS-017 | — |  |

### F8 — Creative Platform · Planned

Advanced animation, procedural worlds, team assets, eight end-to-end demos.  
**Gate:** Eight demo projects run end to end.

_No backlog tickets yet; this phase depends on earlier phases and upstream engine work._

### Verification levels

| Level | Status | Scope | Evidence |
|---|---|---|---|
| Unit/CI | Verified | Python 3.11/3.12 on Ubuntu and Windows, Node history tests | [CI run 41128196057](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41128196057) |
| Official check | Verified | Pinned cargo-horizon-mod accepts all example packages | [CI run 41121633085](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41121633085)<br>[Evidence ledger](../docs/COMPATIBILITY_EVIDENCE.md) |
| Browser E2E | Verified | 13 editor scenarios in Chromium on Ubuntu CI; Firefox, WebKit and Windows browsers not covered | [PR #10 CI: Browser E2E (Chromium)](https://github.com/pneqnp-iswr/horizon-studio/pull/10)<br>[Scope and limits](../docs/BROWSER_E2E.md) |
| Game load | Blocked | No authorized game installation available to CI yet | — |
| Gameplay | Planned | No in-game behaviour has been asserted | — |
<!-- roadmap:details:end -->

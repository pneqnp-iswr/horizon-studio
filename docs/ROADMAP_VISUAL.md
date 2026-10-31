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

"Rust tooling" is not a separate phase in the master roadmap: the Rust editor bridge (HS-011) belongs to F2 and native `.hnmod` builds (HS-010) to F3. The creative-platform families (AI Creator, live preview, VFX, models and animation, entities and bosses, worlds and physics, the ecosystem) are mapped to milestones in [CREATIVE_PLATFORM.md](roadmap/CREATIVE_PLATFORM.md). PixelChat is a separate experimental track (PC-001 to PC-005) and is not counted in phase progress.

Every milestone (schema `horizon-studio.roadmap/2`) records its purpose and scope, deliverable, acceptance criteria, engine requirements, validation target and design document in English and Russian. The same data drives this page, the README tables, both images and the **Development journey** inside Horizon Studio, where every phase and milestone can be searched, filtered and followed through its dependencies offline.

## Updating

1. Edit `docs/roadmap/roadmap.json` in the same pull request as the code and tests that justify the change. Link evidence (pull requests, CI runs, documents in this repository).
2. Run `python scripts/roadmap.py` to regenerate the images, this page's table and the status tables in both READMEs.
3. `tests/test_roadmap.py` rejects unknown statuses, duplicate or missing IDs, references to missing milestones or phases, dependency cycles, contradictory states (for example *done* depending on *planned*, *done* without evidence at its validation target, or *done* while it needs an engine contract no audited engine has), missing governance fields, unknown engine requirements, showcase levels verified out of order, a non-canonical file and stale generated files.

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

### F2 — Creative Editor · Partially verified

Modular UI, docking, search, 3D selection, Blockbench interchange, Rust code bridge (HS-011).  
**Gate:** Edit a Rust file with diagnostics; model round-trip with a declared loss report.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-009 Blockbench adapter with loss reports | Planned | HS-005 | — |  |
| HS-011 Monaco + rust-analyzer + Cargo | Planned | HS-007 | — |  |
| HS-019 Native desktop shell (Tauri 2) and workbench UI | Done | HS-007 | desktop-e2e: [Functional E2E on the real window: Linux (WebKitWebDriver) 8/8 and Windows (WebView2 through msedgedriver) 8/8 in CI run 41165780619, PR #24: handshake, editing with stable uids, undo/redo, native save and reopen, officially checked .hmod, Source Workbench, cancelled save, EN/RU, journey, refused export, restart recovery, failure screen](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41165780619)<br>desktop-smoke: [Windows: frozen core, NSIS install, smoke run, uninstall; portable cold/warm runs (CI run 41143213331)](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41143213331)<br>unit: [Rust shell tests, core protocol and lifecycle tests (desktop/src, tests/test_launcher.py, tests/test_desktop.py)](../tests/test_desktop.py)<br>browser-e2e: [Workbench layout, empty states, journey, Russian UI without English leftovers](../tests/e2e/workbench.e2e.cjs)<br>docs: [ADR 0002: decision matrix and measurements](../docs/adr/0002-desktop-shell.md)<br>unit: [Release pipeline: windows-release.yml builds the desktop app through desktop.yml (release channel) and publishes installer, portable ZIP and desktop-manifest.json with the EXE under one SHA256SUMS.txt; publication refuses non-ready, foreign-commit or unsigned-but-not-prerelease builds and API verification covers every desktop asset; parity gates judged from evidence (signing decision file, migration note); real v0.7.0 files open, build identical packages and join the history (tests/test_release.py, tests/test_desktop_release.py, tests/test_migration_0_7.py)](../tests/test_release.py)<br>docs: [Migration from the 0.7 EXE (EN/RU), the code-signing policy and the owner's recorded decision (unsigned prerelease, docs/releases/signing-decision.json)](../docs/MIGRATING_FROM_0.7.md)<br>desktop-e2e: [v0.8.0 published by windows-release.yml run 41216054418 on 07f74ae: the release's own desktop job ran the functional E2E on the real window (Linux 10/10, Windows 10/10, including twelve reloads), Rust tests, install, smoke and uninstall and the portable ZIP as shipped; desktop-manifest.json release_ready with all four parity gates (desktop-e2e, release-pipeline, signing-decision, migration-note); installer, portable ZIP and EXE published as an unsigned prerelease and verified downloadable through the GitHub API](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41216054418)<br>desktop-smoke: [Release v0.8.0: installer, portable ZIP, EXE, both manifests and SHA256SUMS.txt (Authenticode: NotSigned)](https://github.com/pneqnp-iswr/horizon-studio/releases/tag/v0.8.0) |  |
| HS-028 3D viewport editing | Planned | HS-005, HS-019 | — |  |
| HS-029 Rigging and animation timeline | Planned | HS-028 | — |  |
| HS-033 Docking workspace, tabs, command palette and onboarding | Partially verified | HS-019 | browser-e2e: [Command palette (Ctrl+K): every top-bar and rail command reachable, the enabled ones offered, keyboard navigation, focus return, Russian labels, axe (tests/e2e/palette.e2e.cjs)](../tests/e2e/palette.e2e.cjs)<br>browser-e2e: [Asset search in the command palette: typing finds blocks, items, recipes, structures and effects by name or kind:id (never with an empty query); choosing one opens it for editing, effects in VFX Studio (tests/e2e/palette.e2e.cjs)](../tests/e2e/palette.e2e.cjs) | Docking, tabs and saved layouts with reset are not built; the palette is the first part |

### F3 — Visual Scripting · In progress

Capability registry, typed graph IR, .hmod and trusted native .hnmod backends (HS-010).  
**Gate:** One graph builds a native mod only on a supported hook contract.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-008 Engine capability registry per SHA | Done | HS-005 | official-static: [CI run 41152431321: the official checker built at d2186eb and at 3c1d4b39 accepts every example and migration fixture (one matrix leg per profile, PR #22)](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41152431321)<br>unit: [First slice: registry, project requirements, CLI capabilities (tests/test_capabilities.py)](../docs/ENGINE_CAPABILITIES.md)<br>unit: [Registry fields from Horizon's API levels: API version, stability, side, backend, permissions, contract](../studio_core/engine_profiles.json)<br>browser-e2e: [In the editor: engine card, the journey's 'In this build', export blocked with the reason and data kept](../tests/e2e/workbench.e2e.cjs)<br>official-static: [Second profile 3c1d4b39: official checker built at that revision accepts all examples and migration fixtures; CI matrix leg per profile](../docs/COMPATIBILITY_EVIDENCE.md)<br>browser-e2e: [Target selection, profile differences, undo, save/open, unknown revision blocks export (tests/e2e/workbench.e2e.cjs)](../tests/e2e/workbench.e2e.cjs)<br>unit: [Target schema, editor round trip, CLI export gate, workflow matrix equals registry (tests/test_capabilities.py)](../tests/test_capabilities.py) |  |
| HS-010 Trusted native .hnmod build | Planned | HS-008 | — |  |
| HS-012 Gameplay IR v1 + event graph | Planned | HS-008 | — |  |
| HS-020 AI Creator: typed tool contract and transactional executor | Done | HS-005, HS-006, HS-008 | unit: [HS-020 acceptance on a real workspace folder: a person's edit, an AI proposal on the same item, its per-field diff, approval, undo, redo, autosave, restart with history, a stale proposal refused, a second tab refused, a failed multi-operation transaction that changes nothing, effects and plugin data byte for byte, consistent .hmod; crash and backup recovery of the journal; 300 random exact diffs; the HTTP command protocol (tests/test_transactions.py)](../tests/test_transactions.py)<br>unit: [create_vfx_asset through the shared transactions: preview, accept, undo, redo, a manual edit, restart, deterministic particles, the officially checked package unchanged; invalid effects and unknown presets refused (tests/test_transactions.py)](../tests/test_transactions.py)<br>unit: [The editor's command client: chained revisions, undo/redo, late answers, conflicts, focus checks, project switches, AI approve/stale/reject (tests/test_editor_workspace.cjs)](../tests/test_editor_workspace.cjs)<br>browser-e2e: [AI Creator panel in Chromium against the real core with the fixture provider (labelled simulated): a person's edit and an AI proposal on the same item, per-field diff, apply as one step, undo, redo, reload with history; stale, rejected and cancelled proposals change nothing; a material set and an Impact Spark effect (create_vfx_asset) through the same transactions with unchanged .hmod bytes for the effect; Russian and axe (tests/e2e/ai.e2e.cjs)](../tests/e2e/ai.e2e.cjs)<br>browser-e2e: [Chromium against the real core: undo and redo from buttons and shortcuts reach the disk and survive a reload; a stale tab gets a conflict; Keep editor is an explicit commit (tests/e2e/editor.e2e.cjs)](../tests/e2e/editor.e2e.cjs)<br>unit: [Tool contract horizon-studio.ai-tools/1 and transactional executor: schema, reference and generator validation, revision preconditions, preview, cancel, rollback, audit log, privileged export, engine capability gate; the fixture provider's Ruby set builds the officially checked bytes ee3e1c87 (tests/test_ai_creator.py)](../tests/test_ai_creator.py)<br>unit: [CLI: horizon_cli.py ai-apply writes a new project and a JSONL audit, never the input; a refused transaction writes nothing](../horizon_cli.py)<br>docs: [ADR 0003 and the transaction protocol: ownership, commands, checks, undo/redo, conflicts, crashes, limits](../docs/architecture/TRANSACTIONS.md)<br>docs: [Architecture: contract, transactions, providers and privacy plan](../docs/architecture/AI_CREATOR.md) |  |
| HS-021 AI providers, credentials and privacy | In progress | HS-020 | unit: [Provider interface, offline mode, consent, OS credential store (Windows Credential Manager, Secret Service via stdin, memory for tests), minimal context, exact payload preview, Claude provider on the official SDK (streamed, cancellable, retries, refusal fallback, usage and cost) against a stand-in client; keys never in any written file or response (tests/test_providers.py). Not exercised against the live API](../tests/test_providers.py)<br>browser-e2e: [AI Creator: Claude is used only after a stored key, consent and online mode; the exact payload is shown first; the key never reaches the page, browser storage or a response (tests/e2e/ai.e2e.cjs)](../tests/e2e/ai.e2e.cjs)<br>docs: [Providers and privacy](../docs/architecture/AI_CREATOR.md) | **Active.** |

### F4 — Gameplay Systems · Planned

Entities, components, AI behaviour trees, events, RPG and automation.  
**Gate:** A smart animal or boss in game with persistence and sync.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-014 AI behaviour trees with budgets | Planned | HS-012 | — |  |
| HS-030 Entity, animal and prefab studio | Planned | HS-012, HS-028, HS-029 | — |  |
| HS-031 Combat, abilities and boss phases | Planned | HS-030, HS-014, HS-026 | — |  |

### F5 — World & VFX · Partially verified

Shader graph over .hshader, particles, physics sandbox, dimensions.  
**Gate:** A visual effect scales across quality profiles; gameplay damage stays independent.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-013 .hshader checker + shader graph | Planned | HS-008 | — |  |
| HS-015 Physics sandbox with debug overlay | Planned | HS-012 | — |  |
| HS-016 Dimension and noise editor | Planned | HS-008 | — |  |
| HS-025 VFX asset model and Studio preview | Done | HS-005, HS-006 | browser-e2e: [VFX Studio in Chromium: deterministic Impact Spark preview and timeline checked against the core's fixture, Studio-preview label, validation refuses bad values, undo/redo, save and reopen through studio.project/1, the .hmod stays byte-identical, Russian UI, axe (tests/e2e/vfx.e2e.cjs)](../tests/e2e/vfx.e2e.cjs)<br>unit: [studio.vfx/1 validation, seeded closed-form simulation, editor and core agree particle by particle, canonical project round trip, never exported (tests/test_vfx.py, tests/test_vfx_engine.cjs)](../tests/test_vfx.py)<br>docs: [Model, determinism and what Horizon can do with an effect at 3c1d4b39 (no particle stage in .hshader; native_send_particles is server-side and vanilla-only)](../docs/architecture/VFX.md) |  |
| HS-026 Emitter graph, modules, presets and quality profiles | Planned | HS-025, HS-012 | browser-e2e: [Vertical slice ahead of HS-012: emitters added from templates, duplicated, reordered and deleted; bursts, shape, axis, blending and size/opacity/colour keyframes edited; per-profile particle budgets; undo/redo, save/reopen and identical frames; Python and the editor agree on a four-emitter effect to 1e-12 (tests/e2e/vfx.e2e.cjs, tests/fixtures/vfx_ember_storm.json). No module graph or quality-profile field in studio.vfx/1 yet](../tests/e2e/vfx.e2e.cjs)<br>docs: [Editor and measured preview cost (scripts/vfx_bench.cjs)](../docs/architecture/VFX.md) |  |

### F6 — Engine Bridge · Partially verified

Upstream-accepted engine capabilities: entities, server events, worldgen, physics, rendering.  
**Gate:** Real engine integration matrix with no undocumented patches.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-023 Horizon Preview Bridge | Partially verified | HS-001, HS-008 | unit: [Against stand-ins for horizon-ctl and horizon-client: Launch API check, approval, isolated game and home folders, --dev-mod package, screenshot, state, content confirmed by the game, safe end on every failure, evidence levels (tests/test_preview_bridge.py)](../tests/test_preview_bridge.py)<br>unit: [PB-001 strict content check against the upstream inventory schema (3c1d4b39): only package-defined ids, a control id the game must refuse, an exact +1 in real slots with counts cross-checked, polling for the server's update; lying, ambiguous and malformed stand-ins (give succeeding with nothing added, ids in components, prefixed ids, wrong quantities, 8-slot hotbars, duplicate slots, mismatched counts, list replies, any-id games) never reach game-load; evidence bound to package, build and session; ownership-checked process stop (tests/test_preview_bridge.py)](../tests/test_preview_bridge.py)<br>docs: [Session steps mapped to horizon-ctl at 3c1d4b39; what the evidence may claim; no real client driven yet](../docs/architecture/PREVIEW_BRIDGE.md) | No real Horizon client driven yet: needs an authorized installation (the same blocker as HS-002), so game-load is not reached |
| HS-027 VFX engine backends | Planned | HS-025, HS-013, HS-010, HS-008 | — |  |
| HS-032 Engine contracts for entities, worlds and physics | Planned | HS-010, HS-008 | — |  |

### F7 — Ecosystem · Planned

Secure plugin SDK, templates, signed releases, publishing.  
**Gate:** A third party adds a new asset type and editor without core edits.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-017 Secure plugin host SDK | Planned | HS-007, HS-008 | — |  |
| HS-018 Community publishing | Planned | HS-017 | — |  |
| HS-034 Templates, asset packages and preset libraries | Planned | HS-017, HS-025 | — |  |

### F8 — Creative Platform · Planned

Advanced animation, procedural worlds, team assets, eight end-to-end demos.  
**Gate:** Eight demo projects run end to end.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| HS-022 AI authoring across models, animation, VFX, entities, graphs and Rust | Planned | HS-020, HS-021, HS-012, HS-026, HS-029, HS-030 | browser-e2e: [First piece: the AI Creator review panel; AI output (assets, an effect) stays editable in the same UI and every AI change is one reversible step (tests/e2e/ai.e2e.cjs). Live models, animation, entities, graphs and Rust are not started](../tests/e2e/ai.e2e.cjs) |  |
| HS-024 AI-assisted live preview loop | Planned | HS-022, HS-023 | — |  |

### PixelChat · experimental track ([epic #11](https://github.com/pneqnp-iswr/horizon-studio/issues/11))

A separate prototype track. The browser relay is not a Horizon mod; game integration needs the contracts listed below.

| Milestone | Status | Depends on | Evidence | Notes |
|---|---|---|---|---|
| PC-001 PixelChat native HUD bridge (source proof) | Partially verified | — | unit: [Rust geometry and manifest tests; deterministic source package (PR #20)](../tests/test_pixelchat_native.py) | horizon-mixins plan/apply, a native game build and an in-game screenshot have not been performed |
| PC-002 PixelChat media pipeline and relay prototype | Partially verified | — | unit: [Relay protocol, rate limits and GIF validation (PR #13)](../tests/test_pixelchat.py)<br>browser-e2e: [Two Chromium clients share an animated GIF (PR #18)](../tests/e2e/pixelchat.e2e.cjs) | Runs only as a local browser prototype; no Horizon transport, identity or persistence |
| PC-003 PixelChat multiplayer transport in Horizon | Planned | PC-001, PC-002 | — |  |
| PC-004 PixelChat in-game rendering and fallback | Planned | PC-001, PC-003 | — |  |
| PC-005 PixelChat real-game compatibility tests | Planned | PC-003, PC-004 | — |  |

### Engine contracts not yet in a capability profile

| Contract | State | Notes | Source |
|---|---|---|---|
| `game.agent_control` | available | Preview stability, unversioned; control socket from HORIZON_CONTROL; --offscreen renders without a window | horizon-rust/horizon@3c1d4b39 docs/agent-control.md, docs/horizon-ctl-commands.md |
| `render.custom_particles` | missing | No renderer hook for mod-defined particles at the audited revisions | docs/roadmap/CREATIVE_PLATFORM.md |
| `entity.animation_runtime` | missing | No content or native contract for animated custom models | docs/roadmap/CREATIVE_PLATFORM.md |
| `worldgen.dimension` | missing | Not verified at the audited revisions | docs/roadmap/CREATIVE_PLATFORM.md |
| `physics.authoritative` | missing | No mod-facing physics contract at the audited revisions | docs/roadmap/CREATIVE_PLATFORM.md |
| `network.custom_channel` | missing | Needed by PixelChat and server events; not available to mods | docs/PIXELCHAT.md |

### Showcase SC-001: Crystal Titan

An original multi-phase crystal boss: custom model, rig, animations, AI, attacks, health bar, damage particles, phase transitions and a cinematic death sequence with rewards and multiplayer-safe events.  
**Milestones:** HS-028, HS-029, HS-030, HS-014, HS-031, HS-025, HS-026, HS-013, HS-027, HS-023, HS-022.

| Level | Meaning | Status |
|---|---|---|
| 1 | Editable in Studio | Planned |
| 2 | Rendered in the Studio preview | Planned |
| 3 | A supported engine backend compiles it | Planned |
| 4 | The real Horizon client loads it | Planned |
| 5 | Gameplay, events and multiplayer verified | Planned |

### Verification levels

| Level | Status | Scope | Evidence |
|---|---|---|---|
| Unit/CI | Verified | Python 3.11/3.12 on Ubuntu and Windows, Node history tests | [CI run 41128196057](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41128196057) |
| Official check | Verified | Pinned cargo-horizon-mod accepts all example packages | [CI run 41121633085](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41121633085)<br>[Evidence ledger](../docs/COMPATIBILITY_EVIDENCE.md) |
| Browser E2E | Verified | Editor, workbench and roadmap-explorer scenarios in Chromium on Ubuntu CI on every change; Firefox, WebKit and Windows browsers not covered | [PR #10 CI: Browser E2E (Chromium)](https://github.com/pneqnp-iswr/horizon-studio/pull/10)<br>[Scope and limits](../docs/BROWSER_E2E.md) |
| Game load | Blocked | No authorized game installation available to CI yet | — |
| Gameplay | Planned | No in-game behaviour has been asserted | — |
<!-- roadmap:details:end -->

# Creative platform: feature families on the roadmap

How the creative-platform ambitions (AI Creator, live preview, VFX, models and animation, entities and bosses,
worlds and physics, PixelChat, the creator ecosystem) map onto the one structured roadmap,
[`roadmap.json`](roadmap.json). That file is the only status source. This page explains scope and design rules;
it never states that something works. The in-app *Development journey* and the GitHub roadmap images are rendered
from the same file.

The [master engineering roadmap](master-2026-10-30.md) already named many of these ideas (§6 taxonomy, §10 rendering,
physics and AI, §19 demos). Where a milestone existed, it was **expanded**, not duplicated: HS-009 (Blockbench),
HS-011 (Rust), HS-013 (shaders), HS-014 (behaviour trees), HS-015 (physics), HS-016 (worlds), HS-017 (plugins) and
HS-018 (publishing) keep their IDs and gained scope. New IDs start at HS-020.

## Rules every family follows

1. **Authoring is not runtime.** A finished editor panel never implies that Horizon can load or run its output.
   Each milestone lists `engine_requirements`; `scripts/roadmap.py` refuses to mark a milestone done when any of them
   is missing from every audited engine.
2. **Evidence levels stay separate:** unit, official-static, browser-e2e, desktop-smoke, desktop-e2e, game-load,
   gameplay. A milestone is done only with evidence at its `validation_target`.
3. **Engine facts come from upstream source** at an audited revision, recorded in the capability registry
   (`studio_core/engine_profiles.json`) or, while no profile covers them yet, in `engine_contracts` of `roadmap.json`.
4. **One transaction layer.** AI, plugins and people change projects through the same validated, reversible
   operations on the canonical `studio.project/1` document.
5. **Native code is never trusted silently.** Generated or imported Rust builds outside the Studio process after an
   explicit approval; Studio never approves Horizon's native-code trust boundary on the user's behalf.

## Families → milestones

| Family | Milestones | Engine contracts that gate the runtime |
|---|---|---|
| **A. AI Creator** — natural-language project generation and editing; Claude, other compatible providers and optional local models; typed tools; validation and repair; audit trail; change preview; rollback; privacy and offline modes | HS-020 (tool contract, transactional executor), HS-021 (providers, credentials, privacy), HS-022 (authoring across all asset types) | none for content; `native.hook_mod` for generated Rust |
| **B. Live preview** — local Studio preview, engine-backed preview, isolated real test sessions, screenshots, state inspection, scenarios, error collection, AI evaluation, performance feedback | HS-023 (Preview Bridge over `horizon-ctl`), HS-024 (AI-assisted loop), HS-002 (first real content load) | `game.agent_control` (available upstream, preview) |
| **C. VFX Studio** — reusable effect assets, emitter graph, spawn/update modules, shapes, curves, gradients, colour/opacity/size over life, velocity, noise, trails and ribbons, sparks, debris, shards, smoke, fire, fog, shockwaves, energy rings, materials and shaders, texture animation, light and bloom, camera reactions, post-processing, sound sync, sub-effects, timeline, sequencing, presets, quality profiles, budgets, profiling, capability-aware export | HS-025 (asset model and Studio preview), HS-026 (emitter graph, modules, presets, quality), HS-013 (`.hshader` stages), HS-027 (engine backends) | `native.particles` (vanilla particle types only), `shader.pack`, `render.custom_particles` (missing) |
| **D. Model & Animation Studio** — 3D editing, Blockbench import/export, cuboids and meshes, gizmos, outliner, UV editing, texture painting, pivots and bones, rigging, keyframes, timeline, blending, state machines, event tracks, procedural animation, preview and performance tools | HS-028 (viewport editing), HS-009 (Blockbench adapter with loss reports), HS-029 (rigging and animation timeline) | `entity.animation_runtime` (missing) |
| **E. Entity, Animal & Boss Studio** — templates and prefabs, models and materials, attributes, health, colliders, animations, behaviour trees, perception, pathfinding, navigation, combat, abilities, boss phases, damage reactions, hit and death effects, loot, sync, persistence, debugging | HS-030 (entity and prefab studio), HS-014 (behaviour trees, perception, pathfinding), HS-031 (combat, abilities, boss phases), HS-032 (engine contracts) | `entity.custom` (unsupported at every audited revision) |
| **F. World, Dimension & Physics Studio** — biomes, structures, procedural generation, noise graphs, terrain previews, dimensions, portals, environment lighting, weather; game physics, collisions, constraints, vehicles, fictional rockets and spacecraft, machinery, dynamic simulations, game-only explosions and destruction, performance and network diagnostics | HS-016 (worlds), HS-015 (physics sandbox), HS-032 (engine contracts) | `worldgen.dimension`, `physics.authoritative` (missing) |
| **G. PixelChat** (separate experimental track, epic #11) — pixel emoji, GIF stickers, multiplayer distribution, content-addressed media, caching and rate limits, identity and permissions, client rendering, dedicated and LAN servers, fallback for clients without the feature, accessibility and reduced motion, real-game tests | PC-001 (native HUD source proof), PC-002 (media pipeline and browser relay), PC-003 (multiplayer transport), PC-004 (in-game rendering and fallback), PC-005 (real-game tests) | `network.custom_channel` (missing), `native.hook_mod` |
| **H. Creator ecosystem** — plugin SDK, templates, reusable asset packages, AI tool extension SDK, VFX preset libraries, community content, package publishing, secure plugin execution, collaboration where justified, versioned interchange | HS-017 (secure plugin SDK incl. AI tool extensions), HS-034 (templates, packages, presets, interchange), HS-018 (publishing) | none |
| Workbench UI — docking, tabs, contextual inspectors, command palette, shortcuts, asset search, onboarding | HS-033, HS-019 | none |

The PixelChat browser relay (`pixelchat/`) is a protocol and UI prototype. It is **not** a Horizon mod; only PC-003 to
PC-005 can make it one.

## Engine contracts

`native.particles` is in the capability registry (unsupported at `d2186eb`, engine-only at `3c1d4b3`); the others are
recorded in `roadmap.json` → `engine_contracts` until a capability profile covers them (a test keeps the two lists disjoint).

| Contract | State | Source |
|---|---|---|
| `native.particles` | available: `GameLevel::native_send_particles(options, state, at, spread, speed, count)` since native hooks API 11; vanilla `ParticleType` values on an authoritative level; `Item`, `Trail` and `Vibration` refused; the result means accepted, not delivered | `horizon-rust/horizon@3c1d4b39` `crates/horizon-client/src/game/native_hooks.rs` (API 22 at that revision; the audited pin `d2186eb` has API 7 and no particle hook) |
| `game.agent_control` | available, preview: `horizon-ctl launch [--offscreen] [--wait]`, `wait-ready`, `screenshot`, `state`, `events`, `logs`, `quit` over the control socket | `docs/agent-control.md`, `docs/horizon-ctl-commands.md` at `3c1d4b39` |
| `render.custom_particles` | missing: no hook for mod-defined particle textures, shapes, ribbons or GPU simulation | — |
| `entity.animation_runtime` | missing | — |
| `worldgen.dimension` | missing | — |
| `physics.authoritative` | missing | — |
| `network.custom_channel` | missing | — |

`native.particles` does **not** mean custom GPU particles, scripted boss-death events or custom entity registration.

## Showcase SC-001: Crystal Titan

One shared end-to-end scenario across HS-028, HS-029, HS-030, HS-014, HS-031, HS-025, HS-026, HS-013, HS-027, HS-023
and HS-022: an original multi-phase crystal boss with its own model, rig, animations, attributes and AI, several
attacks, a configurable health bar, damage particles, phase-transition effects, sound, rewards, multiplayer-safe event
ownership and performance profiles. Its death sequence: final hit reaction → crystalline cracking → fragment burst →
expanding energy shockwave → secondary particles and sound → camera and lighting response → fade-out → loot handoff.

| Level | Meaning |
|---|---|
| 1 | Editable in Studio |
| 2 | Rendered in Studio's own preview |
| 3 | A supported engine backend compiles the relevant parts |
| 4 | The real Horizon client loads the result |
| 5 | Gameplay, events and multiplayer behaviour verified |

A level is never marked verified before the level below it, and the showcase never marks its milestones complete.

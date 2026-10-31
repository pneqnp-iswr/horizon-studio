# Capability matrix — Horizon Studio 0.8

A Rust game engine does not make an algorithm impossible in Java. **Do not label a feature "Rust-only" without a comparable implementation study and proof.** "Rust engine integration" means the feature is specifically integrated with Horizon's Rust internals.

| Feature | Local code | Real Horizon game | Scope |
|---|---|---|---|
| Blocks, items, custom PNGs, recipes | Implemented, tested; official static check passes for the examples | Not verified | `.hmod` API 0.2 |
| Canonical `studio.project/1`, stable IDs, migration of schemas 2–4 | Implemented, tested (golden files, byte-identical builds) | Not applicable | project files |
| Disk workspace, crash recovery, revision conflicts, Undo/Redo | Implemented, tested (Python, Node, browser E2E) | Not applicable | local editor |
| One transaction protocol for people and AI (HS-020): shared, persistent undo/redo, stale and cross-tab refusal | Implemented, tested (Python integration, Node, browser and desktop E2E) | Not applicable | project core |
| AI Creator panel with the deterministic fixture provider | Implemented, tested (browser E2E); labelled simulated | Not applicable | local authoring |
| Claude provider (official SDK, consent, OS credential store, offline mode) | Implemented; **not exercised against the live API** | Not applicable | remote authoring, optional |
| VFX Studio: multi-emitter effects, keyframed curves, budgets (Studio preview) | Implemented, tested; Python and the editor agree to 1e-12 | **Not exported**: Horizon has no custom-particle contract | Studio-only `studio.vfx/1` |
| Preview Bridge (`horizon-ctl`): isolated session, strict inventory evidence | Implemented, tested against stand-ins | **No real client driven yet** | development tool |
| Native desktop app (Tauri 2): installer, portable folder | Implemented; installer, portable ZIP and real-window E2E tested on Windows and Linux | Not applicable | Windows x64 (unsigned prerelease) |
| `en_us`/`ru_ru` game names | Implemented, tested | Not verified | content mod resources |
| Mining tool + minimum-tier tags | Implemented, tested | Not verified | content mod data tags |
| Six procedural building generators | Implemented, tested | Not verified | vanilla-format NBT |
| Export rotation/mirroring, reproducible seeds | Implemented, tested | Not verified | editor geometry |
| Isometric canvas preview and Y layers | Browser smoke tested | Not applicable | local editor |
| Mod Doctor / recipe diagnostics | Implemented, tested | Not equivalent to official check | local analysis |
| Headless build/check CLI | Implemented, tested; local checks only | Generated package unverified | developer automation |
| Source Workbench JSON overrides | Implemented, tested | Content runtime compatibility not verified | editor and `.hmod` resources |
| Local 3D cuboid model viewer | Implemented; manual browser E2E not yet verified | Not a game-runtime test | WebGL + software fallback |
| User-provided resource pack import | Selective ZIP/JAR processing implemented | Not a game feature | local-only assets; no redistributed originals |
| Place structures automatically in worlds | **Not implemented** | Not verified | structure pools/sets |
| Live scripted custom behaviors | **Not implemented** | Requires verified native/server mod APIs | Rust-native integration |
| Real-time shader graph and hot reload | **Not implemented** | Requires pinned renderer/shader API | Rust-native integration |
| Parallel world edits and ECS internals | **Not implemented** | Requires pinned engine version and performance/safety tests | Rust-native integration |
| Java impossibility of the above | **Not claimed** | No proof | Not a valid feature label |

## Release gates

1. Local tests and independent NBT decoding.
2. Official `cargo horizon-mod check` against a version-pinned checkout.
3. Actual Horizon game load test and placement check.
4. Compatibility documentation and repeatable automated CI.
5. Only after these steps: declare a feature verified in-game.

`unlicensed-horizon` has **not** been patched for this release. Data-only features require no engine modification and do not justify introducing unnecessary fork incompatibilities.

Official reference: [Horizon content mods](https://playhorizon.dev/docs/content-mods).

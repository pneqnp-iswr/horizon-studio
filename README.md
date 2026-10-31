<p align="center">
  <img src="assets/branding/horizon-studio-banner.svg" alt="Horizon Studio — pixel-art banner: a floating voxel workshop where a block is forged and edited. Build worlds. Create systems. Shape the impossible." width="100%" />
</p>

<p align="center">
  <a href="README.ru.md">Русская версия</a> ·
  <a href="docs/ROADMAP_VISUAL.md">Roadmap</a> ·
  <a href="docs/COMPATIBILITY_EVIDENCE.md">Compatibility evidence</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

<p align="center">
  <img alt="version" src="https://img.shields.io/badge/version-0.7.0-blue" />
  <img alt="status" src="https://img.shields.io/badge/status-alpha-orange" />
  <img alt="tests" src="https://github.com/pneqnp-iswr/horizon-studio/actions/workflows/tests.yml/badge.svg" />
  <img alt="official check" src="https://github.com/pneqnp-iswr/horizon-studio/actions/workflows/official-content-check.yml/badge.svg" />
  <img alt="license" src="https://img.shields.io/badge/license-MIT-16a34a" />
</p>

**Horizon Studio** is an open-source visual workshop for making content mods for [Horizon](https://github.com/horizon-rust/horizon), the Rust re-implementation of Minecraft Java Edition. You design blocks, items, crafting recipes and procedural structures in a local editor; Studio packages them as `.hmod` files that the **official Horizon checker accepts**. The long-term goal is one project that serves beginners (forms), creators (visual logic) and professionals (Rust), with every capability shown together with the evidence that it works.

> **Unofficial project.** Not affiliated with Mojang, Microsoft or the Horizon developers. No game binaries, account bypasses or game assets are included.

## Latest Windows release

<!-- roadmap:release:start -->
**[Horizon Studio v0.7.0 — Project Core](https://github.com/pneqnp-iswr/horizon-studio/releases/tag/v0.7.0)** · alpha prerelease · published 2026-10-30  
⬇ **[HorizonStudio-0.7.0-Windows-x64.exe](https://github.com/pneqnp-iswr/horizon-studio/releases/download/v0.7.0/HorizonStudio-0.7.0-Windows-x64.exe)** · 11.6 MB · [SHA256SUMS.txt](https://github.com/pneqnp-iswr/horizon-studio/releases/download/v0.7.0/SHA256SUMS.txt)  
SHA-256 `3f96e67154a09a6b292a3227c26369f9024d33d6158033d9a325c23b06fcf4b9` · built from [`c816211`](https://github.com/pneqnp-iswr/horizon-studio/commit/c816211b01670d06411ef5a4acd336b8658cdd6a) · unsigned

**In this build** (release gates on the tagged commit (Python, Node, browser E2E, official checker), frozen self-test twice and GUI launch on Windows; run 41136925994, verified through the GitHub API on 2026-10-31):

- Canonical studio.project/1 with stable object IDs; older projects open and migrate
- Disk workspace with crash recovery, revision-conflict choice and Undo/Redo
- Modular editor with drawer and phone layouts for narrow windows
- Hardened local API (session token, Host/Origin checks)
- .hmod export identical to the officially checked packages, also from this Windows build
- Blocks, items, recipes, textures, structures, Source Workbench and Mod Doctor from 0.6
<!-- roadmap:release:end -->

Release rules and verification: [docs/RELEASING.md](docs/RELEASING.md). Every release carries `SHA256SUMS.txt`; releases from 0.7.0 on also carry `build-manifest.json`.

## Where we are now

<p align="center">
  <img src="assets/roadmap/current-phase.svg" alt="Current phase: F3 Visual Scripting. HS-008 engine capability registry in progress; HS-010 and HS-012 planned." width="100%" />
</p>

- **In development:** Version **0.7 — Project Core** (`VERSION` on `master`). The panel above shows the newest release whose executable has been verified through the GitHub API; a version counts as released only after that.
- **Proven:** the example mods pass the official `cargo-horizon-mod check` built from a pinned Horizon revision, in CI and locally.
- **Proven in a browser:** editor, workbench and roadmap workflows run in Chromium on every pull request (Ubuntu CI), including autosave, recovery, revision conflicts, the exported package bytes and an accessibility audit ([current inventory](docs/BROWSER_E2E.md#current-inventory)).
- **Not yet proven:** loading a Studio mod in the running game, and any gameplay behaviour.

## Roadmap

<p align="center">
  <img src="assets/roadmap/roadmap-overview.svg" alt="Development journey from F0 Foundation to F8 Creative Platform. F0 partially verified, F1 done, F3 in progress, other phases planned. Verification levels: unit and CI verified, official check verified, browser E2E verified, game load blocked, gameplay planned." width="100%" />
</p>

<!-- roadmap:status:start -->
| Phase | Focus | Status | Milestones done |
|---|---|---|---|
| F0 Foundation | Official validator, secure local API, release metadata, real-game smoke harness | Partially verified | 3 / 4 |
| F1 Project Core | Canonical project document, migrations, durable workspace, undo, browser E2E | Done | 3 / 3 |
| F2 Creative Editor | Modular UI, docking, search, 3D selection, Blockbench interchange, Rust code bridge (HS-011) | Partially verified | 0 / 6 |
| F3 Visual Scripting | Capability registry, typed graph IR, .hmod and trusted native .hnmod backends (HS-010) | **In progress** | 2 / 5 |
| F4 Gameplay Systems | Entities, components, AI behaviour trees, events, RPG and automation | Planned | 0 / 3 |
| F5 World & VFX | Shader graph over .hshader, particles, physics sandbox, dimensions | Partially verified | 1 / 5 |
| F6 Engine Bridge | Upstream-accepted engine capabilities: entities, server events, worldgen, physics, rendering | Partially verified | 0 / 3 |
| F7 Ecosystem | Secure plugin SDK, templates, signed releases, publishing | Planned | 0 / 3 |
| F8 Creative Platform | Advanced animation, procedural worlds, team assets, eight end-to-end demos | Planned | 0 / 2 |

**Verification levels:** Unit/CI — verified → Official check — verified → Browser E2E — verified → Game load — blocked → Gameplay — planned
<!-- roadmap:status:end -->

Phase states are derived from milestone states in [`docs/roadmap/roadmap.json`](docs/roadmap/roadmap.json); every *done* or *partially verified* milestone links its evidence. Details, dependencies and evidence: **[docs/ROADMAP_VISUAL.md](docs/ROADMAP_VISUAL.md)**. Strategy: [Master Engineering Roadmap](docs/roadmap/master-2026-10-30.md).

## What works today

| Capability | State | Strongest evidence |
|---|---|---|
| Blocks and items from vanilla templates, custom PNG textures, EN/RU names | Works in Studio | Unit tests; official check of examples |
| Shaped and shapeless recipes, mining tool tags, loot tables | Works in Studio | Unit tests; official check of examples |
| Voxel Architect: six seeded structure generators, rotation and mirroring, NBT export | Works in Studio | Unit tests; official check of `voxel_showcase` |
| `.hmod` packaging, byte-identical on every OS | Works | Official `cargo-horizon-mod check` (pinned engine) |
| Canonical `studio.project/1` with stable IDs; migration of older projects | Works | Golden migration tests, byte-identical builds |
| Disk workspace with crash recovery, revision conflicts, Undo/Redo | Works in Studio | Python, Node and browser E2E tests |
| Source Workbench: validated JSON overrides, cuboid 3D preview | Works in Studio | Unit tests; browser E2E (override reaches the `.hmod`) |
| Mod Doctor static diagnostics, CLI (`build`, `verify`, `migrate`, `graph`…) | Works | Unit tests |
| Native desktop window: Tauri 2 shell, Windows installer and portable build, native Save As | **Preview** (CI builds, not released) | Windows CI: install, smoke run, uninstall ([DESKTOP.md](docs/DESKTOP.md)) |
| Workbench UI: explorer, canvas, inspector, status bar, pixel icons; in-app development journey | Works in Studio | Browser E2E, including a Russian UI with no English leftovers |
| Engine capability check (HS-008): export blocked with the reason when the target cannot load the project | Works in Studio | Unit tests; browser E2E |
| Loading in the Horizon game | **Not verified** | Harness ready, needs an authorized installation |
| Visual scripting, entities/AI, native Rust mods, shaders | **Not implemented** | Planned in F2–F5 |

## Screenshots

Captured from the running application, not mock-ups: the desktop shell with its frozen core (Linux WebKitGTK,
driven like a user), and the same editor in Chromium. More sizes in [docs/screenshots/desktop](docs/screenshots/desktop).

<p align="center">
  <img src="docs/screenshots/desktop/desktop-1440x900-recipes.png" alt="Desktop window: top bar with project actions and Export .hmod, activity rail with pixel icons, project explorer with counts, recipe canvas with a shaped and a shapeless recipe, recipe properties on the right, status bar showing the engine target and the desktop shell version" width="100%" />
</p>
<p align="center">
  <img src="docs/screenshots/desktop/desktop-1440x900-journey-ru.png" alt="Development journey in Russian: the pixel-art roadmap and phase list on the left, and on the right what this build supports, grouped into available, engine-only with a native-code warning, and unsupported" width="49%" />
  <img src="docs/screenshots/source-workbench-en.png" alt="Source and 3D workbench editing generated JSON next to a WebGL reference-cube preview" width="49%" />
</p>

## Quick start

**Windows (no Python needed):** download `HorizonStudio-<version>-Windows-x64.exe` from [Releases](https://github.com/pneqnp-iswr/horizon-studio/releases), optionally check it against `SHA256SUMS.txt`, and run it. The executable is portable and unsigned, so SmartScreen may warn. The latest release predates the features above that are marked as newer than 0.6.

**Desktop preview (Windows):** every change builds an installer and a portable folder in the
[Desktop shell workflow](https://github.com/pneqnp-iswr/horizon-studio/actions/workflows/desktop.yml) (artifact
`desktop-windows-preview-build`). They are previews, unsigned and not releases — see [DESKTOP.md](docs/DESKTOP.md).

**From source (Python 3.11+, standard library only):**

```sh
python3 studio.py            # or start_windows.bat / ./start_linux_macos.sh
# open http://127.0.0.1:8787 — the server listens on loopback only
```

**Command line:**

```sh
python horizon_cli.py build   examples/workshop_showcase.hstudio.json -o dist/workshop_showcase.hmod
python horizon_cli.py doctor  examples/workshop_showcase.hstudio.json
python horizon_cli.py migrate examples/ruby_demo.hstudio.json -o my_project.hstudio.json
python horizon_cli.py graph   examples/workshop_showcase.hstudio.json
python horizon_cli.py verify  examples/ruby_demo.hstudio.json --direct-validator --validator-bin /path/to/cargo-horizon-mod
```

Every command reads both `studio.project/1` and older `.hstudio.json` files — see [PROJECT_FORMAT.md](docs/PROJECT_FORMAT.md). Workspaces and recovery: [WORKSPACE_DURABILITY.md](docs/WORKSPACE_DURABILITY.md).

## Compatibility and verification

Each level is separate evidence; passing one never implies the next.

| Level | Meaning | Status |
|---|---|---|
| Unit / CI | Studio's own tests on Ubuntu and Windows, Python 3.11/3.12, Node 22 | Verified on every PR |
| Official static check | Real `cargo-horizon-mod check --json` from Horizon `d2186eb` accepts the exact package bytes | Verified for all examples ([ledger](docs/COMPATIBILITY_EVIDENCE.md)) |
| Browser end-to-end | Editor workflows driven in a real browser | Verified in CI on every change, Chromium on Ubuntu ([current inventory](docs/BROWSER_E2E.md#current-inventory)) |
| Game content load | A real Horizon client loads the package | Not verified — [procedure](docs/GAME_CONTENT_SMOKE.md) |
| Gameplay | Behaviour asserted in a running game | Not verified |

## Development

```sh
python -m unittest discover -s tests -v          # Python suite (CI: Ubuntu + Windows)
node --test tests/test_editor_*.cjs             # editor history and workspace sync (CI: Node 22)
node --test tests/e2e/*.e2e.cjs                  # browser E2E, needs Playwright Chromium (docs/BROWSER_E2E.md)
python scripts/roadmap.py                        # re-render roadmap images and tables from roadmap.json
python scripts/render_branding.py                # re-render the pixel-art banner and mark
```

The banner, mark and roadmap are drawn pixel by pixel by these scripts (no external images or fonts); tests fail if a committed image is stale. Visual language: [DESIGN_SYSTEM.md](docs/branding/DESIGN_SYSTEM.md).

```text
studio.py            local editor server and API      studio_core/   project document, migration, graph, workspaces
index.html, *.js     browser editor (EN/RU)           horizon_compat/ official checker adapter
voxel_architect.py   structure generators             scripts/       CLI helpers, evidence, smoke, image renderers
mod_doctor.py        static diagnostics               tests/         Python and Node tests
```

Releases: the `VERSION` file is canonical; changing it on `master` builds, smoke-tests and publishes a Windows prerelease without overwriting existing tags.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and [SECURITY.md](SECURITY.md). Compatibility claims need evidence: update [`roadmap.json`](docs/roadmap/roadmap.json) together with the code and its tests.

## License

MIT. Horizon Studio is an independent, unofficial project; Minecraft is a trademark of Mojang Synergies AB, and Horizon belongs to its developers. See [LEGAL_AND_DISTRIBUTION.md](docs/roadmap/LEGAL_AND_DISTRIBUTION.md).

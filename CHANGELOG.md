# Changelog

## Unreleased — Engineering hardening

- HS-003: protect local API POST operations with per-process session tokens and same-origin Host/Origin/Fetch-Metadata checks; add API security regression tests and update all built-in clients.
- HS-004: correct versioned release documents and enforce release metadata consistency using an automated test.
- HS-001: CI builds the official `cargo-horizon-mod` from pinned Horizon `d2186eb` and checks every example; all three examples pass (official static check only, not a game load).
- HS-002: opt-in real-game content-load harness with a bounded, self-exiting launch and byte-for-byte resource corroboration; not yet run on a real game.
- HS-005: canonical project document `studio.project/1` with stable object UIDs and UID-based recipe references; automatic migration of `.hstudio.json` schemas 2–4 (byte-identical `.hmod` output), `migrate` and `graph` CLI commands, editor open/save through the new format, atomic file writes.
- Fixed: the CLI dropped editor `source_overrides`, so CLI builds differed from editor exports.
- Fixed: `.hmod`/source ZIPs built on Windows differed byte-for-byte from Linux builds (ZIP "made by" field); every OS now writes the officially checked bytes.
- Fixed: at 1280×720 and similar short screens the editor form covered the entry list, making entries unreachable.
- These post-0.6.0 development changes do not imply a newly published Windows binary.

## 0.6.0 — Source Workbench and model preview (2026-10-30)

- Added Source Workbench for bounded JSON overrides of generated content files, with validation and export integration.
- Added WebGL model preview and software fallback, plus local user-supplied resource-pack texture selection.
- Continued the 0.5 Recipe Lab, Voxel Architect, Mod Doctor and CLI workflows.
- `.hmod` exports remain experimental pending official checker and real-game validation.

## 0.5.0 — Recipe Lab + portable Windows release (2026-10-30)

- Standalone Windows x64 `.exe` launcher, local desktop control window, EN/RU toggle, no Python installation required.
- Automated PyInstaller Windows build, frozen executable smoke test, SHA-256 checksums and versioned GitHub Releases.
- Versioned release workflow uses `VERSION` and does not overwrite already published tags.
- Existing CI branch filter corrected to `master`.

### Added
- New **Recipe Lab** UI direction inspired by a modern recipe-browser layout.
- Large recipe cards, search-driven gallery view, left navigation rail, explorer sidebar and workspace shell.
- SVG banner asset for GitHub presentation: `docs/banner.svg`.
- Additional static-file serving path in `studio.py` for future local `/assets/*` usage.
- README overhaul for GitHub publishing, release presentation and future repository growth.

### Changed
- English remains the default UI; Russian switch remains available and persistent.
- Default startup view now opens the recipe workspace first.
- Cards for recipes, blocks, items and structures now share a more polished visual style.

### Preserved
- `.hmod` export flow
- source ZIP export
- Mod Doctor
- CLI workflows
- Voxel Architect and structure export transforms
- bilingual exported names and mining tags

### Verification
- Local Python regression suite still passes: **59 tests / 105 subtests**.
- In-game verification and official `cargo horizon-mod check` verification are still pending.

## 0.4.0 — Mod Workshop (2026-10-30)

- Three additional procedural NBT generators: floating island, crystal grove, battle arena (six total).
- Two new material palettes: End and Quartz (six total).
- True export transformations: quarter-turn rotations and X/Z mirroring, applied to generated voxel coordinates and NBT.
- EN/RU in-game display names (`en_us` and `ru_ru`) with explicit fallback behavior.
- Generated vanilla tool mining and minimum-tier tags for custom blocks.
- Mod Doctor: validation errors, potential recipe conflicts, craft-only bootstrap warnings, statistics and HTTP API.
- Headless `horizon_cli.py` for doctor, inspect, `.hmod` and source ZIP builds.
- New multi-feature workshop sample project; regressions and browser smoke test.
- **Not verified in the running game or by the official cargo validator.** No engine fork changes.

## 0.3.0 — 2026-10-30

- Voxel Architect: 3 deterministic structure generators (sky dome, spiral tower, seeded labyrinth).
- Four material themes, isometric preview with rotation and per-Y-layer inspector.
- Compressed Java structure NBT export inside `.hmod` and source ZIP.
- Structure-only projects, backward-compatible project import and schema version 3.
- English/Russian strings for all new controls.
- Independent NBT decoder tests, deterministic archive tests and preview API tests.
- Feature matrix that distinguishes actual editor capabilities from unimplemented Rust-native hooks.

## 0.2.0 — 2026-10-30

- Block/item/recipe editing, shaped/shapeless crafting, PNGs, editable project files and experimental `.hmod` export.
- Local API, archive generation and tests.

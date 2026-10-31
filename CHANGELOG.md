# Changelog

## Unreleased — Desktop transformation, slice A

Not in a published release yet; the verified 0.7.0 EXE is unchanged.

- HS-023 Preview Bridge (partial): `studio_core/preview_bridge.py` and `horizon_cli.py preview` drive upstream's `horizon-ctl` to start an already-installed Horizon client with the project as a development mod in an isolated folder and test world, after a Launch API check and the person's approval; they take a screenshot and the state, ask the game to confirm the project's items, always end the session and write evidence that never treats a screenshot as proof of loading. Tested against stand-ins; no real client has been driven yet ([PREVIEW_BRIDGE.md](docs/architecture/PREVIEW_BRIDGE.md)).
- HS-033 (partial): a command palette (Ctrl+K, or the search button on the rail) with every top-bar and rail command, translated labels taken from the controls themselves, prefix/word/fuzzy ranking in English and Russian, keyboard navigation and focus return; it runs the real control, so it behaves exactly like the UI.
- HS-025 VFX Studio: particle effects as canonical project objects (`studio.vfx/1`, kind `vfx`) with a seeded, closed-form simulation shared by the editor (`vfx_engine.js`) and the core (`studio_core/vfx.py`), checked particle by particle against one fixture; an Impact Spark preset; an animated pixel preview with play, restart and an exact timeline; validation with budgets; undo/redo, save, reopen and autosave through the normal project. The preview is labelled *Studio preview — not in-game rendering*, effects are never exported (the `.hmod` stays byte-identical), and the panel states what the target engine lacks: at `3c1d4b39` shader packs have no particle stage and `native_send_particles` only queues vanilla particles from authoritative server code ([VFX.md](docs/architecture/VFX.md)).
- Roadmap v2: governance fields for every milestone (scope, deliverable, acceptance, engine requirements, validation target, design reference, EN/RU), cycle and contradiction checks, creative-platform milestones HS-020 to HS-034, the PixelChat track PC-001 to PC-005 and the Crystal Titan showcase ([CREATIVE_PLATFORM.md](docs/roadmap/CREATIVE_PLATFORM.md)).
- The Development journey becomes a full roadmap explorer: phases with pixel icons, every milestone, search, status and track filters, dependencies, evidence links; installed capabilities and the showcase on separate tabs.
- HS-019 slice B: functional E2E on the real desktop window (`tests/desktop/`), driven through tauri-driver — WebKitWebDriver on Linux, msedgedriver for WebView2 on Windows — covering the core handshake, editing with stable uids, undo/redo, native saves and reopening, the officially checked `.hmod`, a cancelled save, EN/RU, the journey, a refused export, recovery after a restart, the core stopping with its window and the failure screen. They use a test build (cargo feature `e2e`); packaged builds are checked not to be one. Saving is now durable: a uniquely named temporary file is flushed and replaces the target with `MoveFileExW(…WRITE_THROUGH)` on Windows or a rename plus folder sync elsewhere, is removed on any failure, and is capped at 256 MiB; Rust tests for interruption, concurrent saves, Unicode and long names, cancelled dialogs and core shutdown run on Linux and Windows.
- Desktop security review ([docs/security/DESKTOP_REVIEW.md](docs/security/DESKTOP_REVIEW.md)): the desktop core's session token now reaches the editor only through the shell (private handshake pipe, `core_session` command) and `/api/session` is refused in desktop mode, so another local process cannot authorize itself; the core's socket is exclusive; a core that dies takes the window to the failure screen and its origin stops being trusted; startup cannot hang on a mute core; saves accept only `.hmod`, `.hstudio.json` and `.zip` names without invisible format characters or device names, keep Unix permissions and work beyond 260 characters on Windows; one Save dialog at a time; the shell-page check is exact per platform.
- Desktop release candidates: every Windows run of `desktop.yml` now launches the portable ZIP exactly as shipped, records each file's Authenticode status and writes a verified `desktop-manifest.json` and `SHA256SUMS.txt` (`scripts/desktop_release.py`) with the ADR 0002 parity gates and `release_ready` (false until all pass). Nothing is published and VERSION is unchanged ([RELEASING.md](docs/RELEASING.md#desktop-release-candidates-preview-not-published)).
- HS-020 (in progress): the AI Creator tool contract `horizon-studio.ai-tools/1` and a transactional executor (`studio_core/ai_tools.py`): inspect, list, create, update, delete, validate, capabilities, build, rollback; every change is a previewable proposal validated against the schema, references, the package generator and the target engine, committed only against the expected revision, audited (arguments hashed, not stored) and reversible. Exporting needs a person's approval; there is no tool for shell commands, arbitrary files or native code. A deterministic fixture provider and `horizon_cli.py ai-apply` exercise it; its Ruby set builds the officially checked bytes ([AI_CREATOR.md](docs/architecture/AI_CREATOR.md)).
- Documentation test counts are generated from the test files instead of being typed by hand.
- HS-008: a second audited engine profile (`3c1d4b39`, native hooks API 22, server particles through `native_send_particles` for vanilla types only); projects choose their target engine in the editor (undoable, saved in `studio.project/1`) and see what differs; unknown revisions are kept but every export is refused; `horizon_cli.py build`/`source` apply the same gate; the official checker runs once per profile in CI.
- Desktop shell (preview): a Tauri 2 application (`desktop/`) shows the editor in one native window. It starts the bundled project core (`launcher.py --serve`) on a private loopback port, ties the core's lifetime to the window, restricts navigation to the core's origin, grants the editor two commands (`desktop_ready`, `save_file`) for that origin only, and replaces browser downloads with a native Save As that writes atomically. CI builds an NSIS installer and a portable folder, installs, smoke-tests and uninstalls them on Windows ([docs/DESKTOP.md](docs/DESKTOP.md), [ADR 0002](docs/adr/0002-desktop-shell.md)).
- Workbench UI: top bar, activity rail with original 16×16 pixel icons, project explorer, canvas with empty states, inspector, status bar; design tokens from the pixel-art palette; stepped 100–240 ms motion with reduced-motion support; icon-only toolbars on narrow windows.
- In-app Development journey: the roadmap from `docs/roadmap/roadmap.json` and, separately, what this build supports from the capability registry.
- HS-008: registry entries carry Horizon's API version, stability, side, backend, permissions and contract; the editor shows the project's needs and blocks export with the reason when the target engine cannot load something.
- Fixed: Russian UI leftovers (hardness, mod ID, rarity names, rail tooltips, Undo/Redo in the save note).
- Fixed: a frozen build would have failed to load the capability registry, because its validation required documentation files that are not bundled.

## 0.7.0 — Project Core (2026-10-31)

- HS-003: protect local API POST operations with per-process session tokens and same-origin Host/Origin/Fetch-Metadata checks; add API security regression tests and update all built-in clients.
- HS-004: correct versioned release documents and enforce release metadata consistency using an automated test.
- HS-001: CI builds the official `cargo-horizon-mod` from pinned Horizon `d2186eb` and checks every example; all three examples pass (official static check only, not a game load).
- HS-002: opt-in real-game content-load harness with a bounded, self-exiting launch and byte-for-byte resource corroboration; not yet run on a real game.
- HS-005: canonical project document `studio.project/1` with stable object UIDs and UID-based recipe references; automatic migration of `.hstudio.json` schemas 2–4 (byte-identical `.hmod` output), `migrate` and `graph` CLI commands, editor open/save through the new format, atomic file writes.
- Fixed: the CLI dropped editor `source_overrides`, so CLI builds differed from editor exports.
- Fixed: `.hmod`/source ZIPs built on Windows differed byte-for-byte from Linux builds (ZIP "made by" field); every OS now writes the officially checked bytes.
- Fixed: at 1280×720 and similar short screens the editor form covered the entry list, making entries unreachable.
- GitHub presentation: original pixel-art banner and mark, an evidence-backed roadmap map generated from `docs/roadmap/roadmap.json` (validated, with derived phase states and separate verification levels), real editor screenshots, redesigned English and Russian READMEs, and a design system. Replaces the old `docs/banner.svg` and the 0.4 screenshot.
- HS-007: browser E2E suite (13 Chromium scenarios) in CI; editor split into tested modules (`editor_api`, `editor_workspace`, `editor_model`, `editor_render`).
- Fixed: narrow windows (≤1100 px) hid the whole project sidebar; phones pushed the workspace off screen; missing favicon; ambiguous Source Workbench file labels; stale "0.5" window title.
- Release engineering: gated, idempotent Windows release workflow (same-commit test gates, draft-then-verify publication, `build-manifest.json`), corrected v0.6.0 release notes, `docs/RELEASING.md`.

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

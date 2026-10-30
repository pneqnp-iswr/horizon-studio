# Changelog

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

## [0.3.0] - 2026-10-30

### Added
- Voxel Architect: 3 deterministic structure generators (sky dome, spiral tower, seeded labyrinth).
- Four material themes, isometric preview with rotation and per-Y-layer inspector.
- Compressed Java 26.3 structure NBT export inside `.hmod` and source ZIP.
- Structure-only projects, backward-compatible project import and schema version 3.
- English/Russian strings for all new controls.
- Independent NBT decoder tests, deterministic archive tests and preview API tests.
- Feature matrix that distinguishes actual editor capabilities from unimplemented Rust-native hooks.

### Limitations
- Does not yet place structures automatically in worlds. Official Horizon game/CLI validation not performed.


All notable changes are documented here. Horizon Studio follows the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) style when practical.

## [Unreleased] — GitHub-ready i18n update

### Added

- English default interface and persistent 🇬🇧 EN / 🇷🇺 RU language selector
- 89 translation keys for page UI, controls, feedback and validation messages
- Additional Python unit tests and Chromium UI smoke validation
- English README, Russian README, contribution guidelines, security policy and CI configuration

### Changed

- The local HTTP server now serves the self-contained `/i18n.js` asset

## [0.2.0] — 2026-10-30

- Block/item/recipe editing, shaped/shapeless crafting, PNGs, editable project files and experimental `.hmod` export
- Local API, archive generation and tests

The release is still alpha; in-game integration has not been verified.

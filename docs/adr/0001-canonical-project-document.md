# ADR-0001: Canonical project document with stable object identities

- Status: accepted (HS-005, 2026-10-30)
- Roadmap: master roadmap §8, §23 ADR-001

## Context

Projects were saved as the browser editor's internal state (`.hstudio.json` schemas 2–4): objects were identified only by their names, recipes referred to them by `@name`, and the CLI and editor each had their own loader. Renaming an item required rewriting every recipe, the CLI silently dropped Source Workbench overrides, and there was no place for data owned by future object kinds or plugins.

## Options

1. **Keep the editor state as the file format** and add fields as needed — no migration, but names stay identities and every new feature edits the same untyped blob.
2. **Directory workspace** (one file per object plus an index) — git-friendly at scale, but requires workspace storage, locking and a file layout decision before anything else can use stable IDs.
3. **Single versioned JSON document with stable `uid`s and UID references**, convertible to/from the editor state and to the generator request.

## Decision

Option 3. `studio.project/1` (see [PROJECT_FORMAT.md](../PROJECT_FORMAT.md)) is the one canonical representation. The editor state and the generator request are *derived* views produced by `studio_core.migrate`. All entry points (CLI, HTTP API, editor) read through `upgrade()`, so legacy files keep working without a separate code path.

Objects are a flat, ordered list with `kind`, so a directory workspace (option 2) can later split the same objects into files without another identity change.

## Consequences

- Renames are local edits; dependency queries (`AssetGraph`) work on `uid`s.
- Unknown kinds, extensions and fields survive every load/save path, including the editor (via `carry`).
- Byte-identical builds for migrated projects are a tested invariant, tied to packages the official checker accepted.
- Cost: one more conversion layer, and golden fixtures to update whenever the document shape changes deliberately.
- Revisit when projects outgrow one file (thousands of objects) or when multi-user editing needs per-object storage.

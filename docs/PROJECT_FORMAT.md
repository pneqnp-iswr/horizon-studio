# Project format — `studio.project/1`

Horizon Studio stores a project as one JSON document (file extension `.hstudio.json`). Since HS-005 the canonical format is `studio.project/1`; files written by older Studio versions (schemas 2, 3 and 4) still open everywhere and are migrated in memory.

Implementation: [`studio_core/`](../studio_core). Decision record: [ADR-0001](adr/0001-canonical-project-document.md).

## Document

```json
{
  "format": "horizon-studio",
  "schema": "studio.project/1",
  "project": {"id": "ruby_demo", "name": "Ruby Demo", "version": "0.1.0", "author": "Creator", "description": "…"},
  "objects": [
    {"uid": "46e2add5-6199-59c8-a0e2-e099ee79df6b", "kind": "block", "id": "ruby_block",
     "props": {"name": "Block of Ruby", "template": "minecraft:iron_block", "hardness": 4, "light": 3}},
    {"uid": "8b03ca85-7f82-5cce-8341-9e419bd69a90", "kind": "item", "id": "ruby", "props": {"name": "Ruby", "…": "…"}},
    {"uid": "743a94d3-6aab-5005-b9e3-43d67678a736", "kind": "recipe", "id": "ruby_block",
     "props": {"type": "shaped", "count": 1,
               "result": {"ref": "46e2add5-6199-59c8-a0e2-e099ee79df6b"},
               "grid": [{"ref": "8b03ca85-7f82-5cce-8341-9e419bd69a90"}, null, "minecraft:stick", "…"]}}
  ],
  "source_overrides": {"assets/ruby_demo/models/item/ruby.json": "{…json text…}"},
  "extensions": {},
  "provenance": {"migrations": [{"from": 2, "to": "studio.project/1"}]}
}
```

| Field | Meaning |
|---|---|
| `project` | Mod metadata. `id` becomes the mod namespace. Unknown keys are kept. |
| `objects[]` | Every authored object. Order is preserved and is part of the build input (it fixes the order of translation keys and tag values). |
| `objects[].uid` | Stable identity: lowercase UUID, unique in the document, **never changes on rename**. |
| `objects[].kind` | `block`, `item`, `recipe`, `structure`. Other kinds (future plugins) are kept, reported as `UNSUPPORTED_OBJECT_KIND` and left out of builds. |
| `objects[].id` | The name used in the generated mod (`<mod>:<id>`). Blocks and items share one namespace. |
| `objects[].props` | Kind-specific fields, as the generator reads them. Recipe `result` and `grid` slots hold `{"ref": "<uid>"}` for this project's blocks/items, a resource name such as `minecraft:stick` for vanilla ones, or `null` for an empty slot. |
| `source_overrides` | Source Workbench JSON overrides, path → text. |
| `extensions` | Namespaced data owned by plugins or future features; never interpreted or dropped by the core. |
| `provenance.migrations` | Log of format conversions applied to this document. |

Unknown top-level fields are preserved as-is, so a newer Studio can add fields without older ones destroying them.

## Identifiers

- New objects created in the editor get a random UUID (v4).
- Migration from older files derives a UUID v5 from `(mod id, kind, object id)`, so migrating the same legacy file twice gives the same identifiers.
- Renaming an object changes only `id`; recipes that use it keep pointing at the same `uid`.

## Diagnostics (`python horizon_cli.py graph <project>`)

| Code | Level | Meaning |
|---|---|---|
| `MISSING_REFERENCE` | error | A recipe refers to a `uid` that is not in the document |
| `INVALID_REFERENCE_KIND` | error | A recipe refers to something that is not a block or item |
| `UNRESOLVED_LOCAL_NAME` | error | A legacy `@name` reference that matched no object (kept as `<mod>:<name>`) |
| `UNSUPPORTED_OBJECT_KIND` | warning | An object kind this Studio version does not build |

Structural problems (bad UUIDs, duplicate `uid`s or names, wrong types) make the file unreadable with an explicit error instead.

## Migration

| From | How |
|---|---|
| schema 2, 3, 4 | `metadata` → `project`; each entry → object with derived `uid`; `@name` and `<mod>:<name>` references → `{"ref": uid}`; empty slots → `null`; unknown top-level fields → `extensions["horizon-studio.legacy-fields"]` |

Guarantee, enforced by `tests/test_project_migration.py`: a migrated project builds a **byte-identical** `.hmod` to the one the legacy file built. For the three examples these are exactly the packages the official `cargo-horizon-mod` accepted ([COMPATIBILITY_EVIDENCE.md](COMPATIBILITY_EVIDENCE.md)). Golden migrated documents live in `tests/fixtures/migration/`.

Commands:

```sh
python horizon_cli.py migrate old.hstudio.json                 # print the migrated document
python horizon_cli.py migrate old.hstudio.json -o new.hstudio.json [--force]
python horizon_cli.py migrate old.hstudio.json -o old.hstudio.json   # in place, keeps old.hstudio.json.schema<N>.bak
```

Files are written atomically (temporary file, flush, rename), so an interrupted write leaves the previous file intact. In-place migration refuses to run if the backup file already exists.

## Editor

- **Open project** sends the file to the local server (`POST /api/project/open`), which migrates it if needed and returns the editor state; the status line says when a file came from an older schema. The original file is not modified.
- **Save project** sends the editor state to `POST /api/project/save` and downloads the canonical document.
- The editor keeps each object's `uid` while editing and renaming. Everything it does not edit (unknown kinds, extensions, extra metadata, provenance, unknown fields) travels in an opaque `carry` object and is written back unchanged.
- Both routes use the same local API protections as every other POST route (loopback Host, Origin/Fetch-Metadata checks, session token, JSON content type).

The browser's local autosave still stores the editor state, not the canonical document; durable workspace storage with undo is HS-006.

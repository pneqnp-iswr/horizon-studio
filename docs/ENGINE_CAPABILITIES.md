# Engine capability registry (HS-008)

Studio must never produce output that silently does nothing. `studio_core/engine_profiles.json` lists, per pinned Horizon revision, what that engine can load and what Studio can build for it; `studio_core/capabilities.py` compares a project against it.

| Status | Meaning |
|---|---|
| `official-static` | Studio builds it and the real `cargo-horizon-mod` accepted such packages ([evidence](COMPATIBILITY_EVIDENCE.md)) |
| `engine-only` | Horizon supports it, Studio cannot produce it yet (e.g. native `.hnmod`, shader packs) |
| `unsupported` | Horizon has no way to load it at this revision (e.g. custom entities) |

None of these says the game loads or runs the content; that is the separate game-load level (HS-002).

Every capability also records what Horizon itself says about the surface (read from `docs/api/stability.md`,
`docs/mods.md`, `docs/native-mods.md` and `docs/shaders.md` at the pinned revision):

| Field | Meaning | Example (`native.hook_mod`) |
|---|---|---|
| `api` | the API line or version a package names | `native hooks 7 (NATIVE_HOOKS_API) or a pinned horizon_revision` |
| `stability` | Horizon's level: `experimental`, `preview`, `stable`, or `not-started` | `experimental` |
| `side` | `both`, `client` or `server` | `client` |
| `backend` | the package Studio would emit: `hmod`, `hnmod`, `hshader`, or none | `hnmod` |
| `permissions` | what the package is allowed to do | `native code with the player's rights, not sandboxed` |
| `contract` | the files or hooks the engine reads | `horizon-mixin.toml plus .rs helpers …` |
| `source`, `evidence`, `note`, `note_ru` | where each fact comes from; why it is not buildable | — |

`validate_registry` refuses an entry without these fields, an unknown stability, side or backend, and an
`official-static` entry without a backend or an evidence document. Evidence documents are checked in the repository
(tests pass the repository root); the frozen application ships the registry without the documents it cites and
validates only the structure.

```sh
python horizon_cli.py capabilities examples/workshop_showcase.hstudio.json
```

lists what the project needs (`content.block`, `content.recipe`, `content.block_tag`, …) and reports `ENGINE_CAPABILITY_MISSING` for anything the profile cannot build, or `ENGINE_PROFILE_UNKNOWN` when the project targets a revision without a profile. A project selects a revision with an optional top-level field, kept by every load/save path:

```json
"target": {"engine": "horizon", "revision": "d2186eb9aa022a64a8b26e6989a04e44fba99ee7"}
```

Without it the registry's default (the audited pin) is used. Every profile entry cites the upstream source it was read from; profiles are added only with fresh evidence for that revision.

## In the editor

- The **Engine target** card in the project explorer and the status bar show the profile (`Horizon d2186eb · API 0.2`)
  and every capability the open project needs, refreshed after each edit (`POST /api/capabilities/check`).
- **Export is blocked** when the check reports an error: the status bar names each missing capability and its reason,
  nothing is written and the project is kept as it is (browser E2E: `tests/e2e/workbench.e2e.cjs`).
- The **Development journey** dialog lists, under *In this build*, every capability of the profile grouped by status,
  with its backend, API and stability, and a warning on native code. It is the same data, so the app cannot promise
  more than the registry.

**Status of HS-008:** registry with Horizon's API levels, requirement analysis, CLI, editor diagnostics and the export
gate exist. Still to do: let a project choose its target revision in the editor, and add a second profile when the
pin moves (the upstream `main` drift probe `3a5ac7ff` is not a profile yet).

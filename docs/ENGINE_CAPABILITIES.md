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

## Profiles

| Profile | Revision | Native hooks | What differs |
|---|---|---|---|
| Default (audited pin) | `d2186eb9aa022a64a8b26e6989a04e44fba99ee7` | API 7 | no particle hook (`native.particles` unsupported) |
| Second profile (upstream `main`, 2026-10-31) | `3c1d4b39c6823dca9751118a0b13e6084d019d64` | API 22 | `native.particles` engine-only: `GameLevel::native_send_particles` (API 11+) emits vanilla particle types from an authoritative level; `Item`, `Trail` and `Vibration` are refused and the result means accepted, not delivered |

Both profiles mark every content capability `official-static`: the official checker built at each revision accepts every
example and migration fixture (`official-content-check.yml` runs one matrix leg per profile; see
[COMPATIBILITY_EVIDENCE.md](COMPATIBILITY_EVIDENCE.md)). Custom entities stay unsupported in both. A test keeps the
workflow matrix and the registry's revisions identical, so a profile cannot be added without its official check.

## Choosing a target

A project names its engine in the canonical document:

```json
"target": {"engine": "horizon", "revision": "3c1d4b39c6823dca9751118a0b13e6084d019d64"}
```

`validate_document` accepts only `{"engine": "horizon", "revision": <40 lowercase hex characters>}`. The field is kept
through editor round trips, saving, opening, migration and the CLI; without it the registry default applies. The editor's
**Build for** selector in the Engine target card writes it as an undoable edit and lists the capabilities whose status
differs from the default profile. A project whose revision has no profile keeps its target ("Unknown revision … kept
as saved"); every export is then refused with `ENGINE_PROFILE_UNKNOWN`, because nothing can be promised for it.

`python horizon_cli.py build` and `source` apply the same gate and write nothing when the target cannot load the project.
The target never changes the package bytes: the Ruby demo builds `ee3e1c87…` for either profile.

## In the editor

- The **Engine target** card in the project explorer and the status bar show the profile (`Horizon d2186eb · API 0.2`)
  and every capability the open project needs, refreshed after each edit (`POST /api/capabilities/check`).
- **Export is blocked** when the check reports an error: the status bar names each missing capability and its reason,
  nothing is written and the project is kept as it is (browser E2E: `tests/e2e/workbench.e2e.cjs`).
- The **Development journey** dialog lists, under *In this build*, every capability of the profile grouped by status,
  with its backend, API and stability, and a warning on native code. It is the same data, so the app cannot promise
  more than the registry.

**Status of HS-008:** registry with Horizon's API levels, requirement analysis, two audited profiles, project target
selection with comparison, the editor diagnostics and export gate, and the CLI gate exist. Further profiles are added
only with a fresh source audit and an official-check matrix leg.

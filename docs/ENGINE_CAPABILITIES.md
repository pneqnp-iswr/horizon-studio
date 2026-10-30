# Engine capability registry (HS-008)

Studio must never produce output that silently does nothing. `studio_core/engine_profiles.json` lists, per pinned Horizon revision, what that engine can load and what Studio can build for it; `studio_core/capabilities.py` compares a project against it.

| Status | Meaning |
|---|---|
| `official-static` | Studio builds it and the real `cargo-horizon-mod` accepted such packages ([evidence](COMPATIBILITY_EVIDENCE.md)) |
| `engine-only` | Horizon supports it, Studio cannot produce it yet (e.g. native `.hnmod`, shader packs) |
| `unsupported` | Horizon has no way to load it at this revision (e.g. custom entities) |

None of these says the game loads or runs the content; that is the separate game-load level (HS-002).

```sh
python horizon_cli.py capabilities examples/workshop_showcase.hstudio.json
```

lists what the project needs (`content.block`, `content.recipe`, `content.block_tag`, …) and reports `ENGINE_CAPABILITY_MISSING` for anything the profile cannot build, or `ENGINE_PROFILE_UNKNOWN` when the project targets a revision without a profile. A project selects a revision with an optional top-level field, kept by every load/save path:

```json
"target": {"engine": "horizon", "revision": "d2186eb9aa022a64a8b26e6989a04e44fba99ee7"}
```

Without it the registry's default (the audited pin) is used. Every profile entry cites the upstream source it was read from; profiles are added only with fresh evidence for that revision.

**Status of HS-008:** the registry, project requirement analysis and CLI exist. Still to do: show the diagnostics in the editor, block export on missing capabilities, and add a second profile when the pin moves.

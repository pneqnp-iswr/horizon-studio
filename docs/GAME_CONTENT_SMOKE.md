# HS-002 — Authorized Game Content-Load Smoke Probe

This experimental harness can **launch a trusted, user-supplied Horizon game executable** against a generated Studio `.hmod` and record conservative evidence.

It does **not** download game assets, authenticate accounts, bypass licensing, distribute proprietary files, or replace full visual/gameplay testing.

## Requirements

1. A locally installed and legally usable Horizon game and its required assets.
2. A Studio project and **matching successful official static-check evidence**, created by `python horizon_cli.py verify ... --evidence ...`.
3. Explicit authorization to execute the selected local game process.
4. An existing game working directory and its `logs/latest.log` path.

Example (adjust all paths for your legally installed game):

```sh
python scripts/game_content_smoke.py \
  --game /path/to/horizon-client \
  --project examples/ruby_demo.hstudio.json \
  --official-evidence dist/official/ruby-check.json \
  --workdir /path/to/game-working-directory \
  --game-log /path/to/game-working-directory/logs/latest.log \
  --timeout 300 \
  --output dist/game-content-smoke.json \
  --confirm-authorized
```

The official static check must be for **identical package bytes**; a changed project invalidates its evidence.

## Evidence levels

- `content_loaded`: the real game process exited normally, the log reported content-mod resources, and the reported resource-root directory physically contained Studio's `data/<mod-id>/...` JSON files. This proves a **content-load observation only**, not gameplay or correct rendering.
- `rejected`: game log contains an explicit content-load rejection for this mod.
- `indeterminate`: timeout, stale/unavailable logs, missing resource-root files, or lack of sufficient evidence.
- `failed`: the game process exits with a nonzero code.

The harness does not claim to prove a block can be placed, a recipe works, a world saves correctly, or entity behavior is correct. Those require separate **manual or automated gameplay assertions**.

**This workflow is opt-in and is not run in public CI**, because legally obtained game assets and a live desktop environment are required. No user files, logs or licensed resources are uploaded automatically.

Source grounding: at audited Horizon SHA `d2186eb9aa022a64a8b26e6989a04e44fba99ee7`, `mods.rs` logs `Horizon: content from N mod(s) in <resource_root>`, and `cargo horizon-mod run` launches `horizon-client --dev-mod <file>`. These observations are version-sensitive and should be updated when the engine changes.

# HS-002 — Authorized Game Content-Load Smoke Probe

This experimental harness can **launch a trusted, user-supplied Horizon game executable** against a generated Studio `.hmod` and record conservative evidence.

It does **not** download game assets, authenticate accounts, bypass licensing, distribute proprietary files, or replace full visual/gameplay testing.

## Requirements

1. A locally installed and legally usable Horizon game and its prepared resources.
2. A Studio project and **matching successful official static-check evidence**, created by `python horizon_cli.py verify ... --evidence ...`.
3. Explicit authorization to execute the selected local game process (`--confirm-authorized`).
4. An existing game working directory. The game builds its content cache (`.horizon-cache/mod-content`) there.

Example (adjust all paths for your legally installed game):

```sh
python scripts/game_content_smoke.py \
  --game /path/to/horizon-client \
  --project examples/ruby_demo.hstudio.json \
  --official-evidence dist/official/ruby-check.json \
  --workdir /path/to/game-working-directory \
  --frames 300 \
  --timeout 300 \
  --output dist/game-content-smoke.json \
  --confirm-authorized
```

Add `--resources /path/to/prepared-resources` if the game does not find its prepared resources by default.

The official static check must be for **identical package bytes**; a changed project invalidates its evidence.

## How the run is bounded

The harness launches:

```
horizon-client --dev-mod <tmp>/<id>.hmod --home <tmp>/home \
  --frames N --timeout-seconds S --smoke-report <tmp>/smoke-report.json [--resources PATH]
```

so the game exits by itself after `N` frames (or reports `frame-limited run timed out` after `S` seconds). The harness stops the process itself only `S + 60` seconds after launch. `--home` points at a fresh temporary folder, so the log read afterwards (`<tmp>/home/logs/latest.log`) is always this run's, never a previous session's.

## Evidence levels

- `content_loaded`: the game exited with code 0, its smoke report has no `error`, its log contains `Horizon: content from N mod(s) in <root>`, and **every** file the game copies verbatim from this exact package is present in `<root>` with identical bytes. Files the game rewrites — merged tag JSON (`data/*/tags/*.json`) and the block/item declarations under `data/<mod-id>/horizon/` — are not compared. This proves a **content-load observation only**, not gameplay or correct rendering.
- `rejected`: the game log contains `Horizon: mod <id> content not loaded: …` for this mod.
- `indeterminate`: harness timeout, missing smoke report, no content line, or resource-root files missing/different (listed in `problems`).
- `failed`: the game exited with a nonzero code or its smoke report contains an `error`.

The harness does not claim to prove a block can be placed, a recipe works, a world saves correctly, or entity behavior is correct. Those require separate **manual or automated gameplay assertions**.

**This workflow is opt-in and is not run in public CI**, because legally obtained game assets and a desktop/GPU environment are required. No user files, logs or licensed resources are uploaded automatically. Unit tests drive the harness against a fake client script that imitates the launch contract; they are not game evidence.

## Source grounding

Read from Horizon `d2186eb9aa022a64a8b26e6989a04e44fba99ee7` and re-checked unchanged at `3a5ac7ffed8a149aedaeffab2abe55fefc040af8` (2026-10-30):

| Behaviour | Source |
|---|---|
| `--dev-mod`, `--frames`, `--timeout-seconds`, `--smoke-report` options; report JSON with `error` | `crates/horizon-client/src/game.rs` (`parse` options, `write_report`) |
| `--home DIR` → `DIR/logs/latest.log`; Horizon messages also on stderr | `crates/horizon-client/src/main.rs`, `crates/horizon-client-render/src/logging.rs` |
| `content from N mod(s) in <root>` / `mod <id> content not loaded:` log lines; cache in `<cwd>/.horizon-cache` | `crates/horizon-client/src/game/mods.rs` |
| Mod files written verbatim except tags and `data/<id>/horizon/` declarations | `crates/horizon-client/src/mod_content.rs` (`build`, `Overlay::write`) |

These observations are version-sensitive and must be re-checked when the pinned engine changes.

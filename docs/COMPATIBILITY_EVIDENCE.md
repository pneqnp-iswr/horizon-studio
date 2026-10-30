# Compatibility Evidence Ledger

Every compatibility statement about Horizon Studio output is recorded here with the engine revision, the checker, the exact package hash and where the evidence lives. Levels are independent: passing one never implies the next.

| Level | Meaning |
|---|---|
| `unit` | Studio's own tests; mocked external tools |
| `official-static` | Real upstream `cargo-horizon-mod check --json` accepted the exact `.hmod` bytes |
| `game-content-load` | A real Horizon client loaded the package's content (`scripts/game_content_smoke.py`) |
| `gameplay` | Behaviour asserted in a running game (placing, crafting, saving…) |

## Official static check (`cargo-horizon-mod check --json`)

Packages are deterministic: the same project yields the same bytes on every machine (all hashes below are identical in GitHub Actions and in an independent Linux run). Projects migrated to `studio.project/1` build the same bytes (`tests/test_project_migration.py`).

**Windows caveat (fixed in PR #7):** before PR #7, Python's `zipfile` wrote a different "made by" system field on Windows, so Windows builds — including the 0.5/0.6 Windows EXE — produced different bytes with identical file contents (`ruby_demo`: `8143d989beb2583913f5288770fa5e61f800009f9a63b5b2a60bf6b2aa183173`). Those Windows-built bytes were never run through the official checker. Since PR #7 the field is pinned and every OS writes the hashes below; a test simulates the Windows default on every platform.

| Example | `.hmod` SHA-256 | Bytes | Engine `d2186eb9` (audited pin) | Engine `3a5ac7ff` (upstream `main`, 2026-10-30) |
|---|---|---:|---|---|
| `ruby_demo` | `ee3e1c878ea41fbf710f749896bfdb92b23b18e21e67b016b57b95b96a8797e2` | 3128 | **pass** — CI + local | **pass** — local |
| `workshop_showcase` | `b5fc8c688000531b78cf47fee60d158ce046b90be415f2b6e47e7e8093488452` | 13994 | **pass** — CI + local | **pass** — local |
| `voxel_showcase` | `56e6945d1885e154bfef96e22cb6b770e880e5059df9240a87ebade8e82df6ce` | 8209 | **pass** — CI + local | **pass** — local |

All reports: `kind = "mod"`, `api = "0.2"`, `capabilities = ["registries"]`, `side = "both"`, `signed = false`.

### Evidence sources

- **CI, `d2186eb9aa022a64a8b26e6989a04e44fba99ee7`**: GitHub Actions run [`41100332672`](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41100332672) (PR #4, head `e2c398b`). Checker compiled from the verified checkout with `cargo build --locked --package cargo-horizon-mod`; binary SHA-256 `aeae52a138386081fe1051c7f56256accbb6878f80db648b3949b34808d6599a`; artifact `horizon-official-content-check` (ID `12998931220`, retained until 2027-01-28) holds the raw report, toolchain versions and attestation. Covers `ruby_demo` only.
- **CI, `d2186eb9aa022a64a8b26e6989a04e44fba99ee7`, all examples**: GitHub Actions run [`41121633085`](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41121633085) (PR #6, head `15b3e40`); artifact `horizon-official-content-check` ID `13009195982` with one report and one attestation per example. Same three package hashes as the local runs.
- **Local, `d2186eb9aa022a64a8b26e6989a04e44fba99ee7`**: Linux container, rustc/cargo 1.97.0, same build command; checker binary SHA-256 `2ad85a6467f07c15895e8d0debb284a573a87f805e439b40d31bd494027e2c28` (debug binaries differ by build path, so this hash is not expected to equal CI's). All three examples passed and `scripts/record_official_evidence.py` produced attestations.
- **Local, `3a5ac7ffed8a149aedaeffab2abe55fefc040af8`**: upstream `main` at the time of the check; checker binary SHA-256 `fbffc28d60ab11348dad59d0d03f52b47964244398055edff9db5c580e74afa5`. All three examples passed. This is a drift probe, not a new pin.

Local runs are reproducible with the commands in [OFFICIAL_VERIFICATION.md](OFFICIAL_VERIFICATION.md); their raw JSON was not committed because it embeds temporary paths.

## Game content load

No real-game run has been recorded. The opt-in harness ([GAME_CONTENT_SMOKE.md](GAME_CONTENT_SMOKE.md)) needs a legally installed client with prepared resources and a desktop/GPU session, which public CI does not have. **No Studio mod is claimed to load in the game yet.**

## Gameplay

Not verified for any package.

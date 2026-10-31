# IDE-001 — Horizon game readiness check

**Status:** read-only readiness probe only. It does not start Minecraft, verify a mod in a running game, or embed the game.

## Why it exists

Horizon IDE's goal is two working panes in one desktop window: a playable native Horizon viewport and a code/AI workbench. A browser screenshot, a successful build or a game launch-API response is not evidence that the game is playable in Tauri.

Before designing the integrated host, Studio should identify a real user-installed Horizon executable and check the specific protocol already used by the existing Preview Bridge.

## Usage

Use your own legally installed Horizon binary and prepared resources:

```sh
python -m studio_core.ide_preflight --ctl "/absolute/path/to/horizon-ctl" --json
```

On Windows, choose the installed `horizon-ctl.exe` beside `horizon-client.exe`. Omit `--ctl` to let the existing Preview Bridge search `HORIZON_CTL` and then `PATH`.

Output contains `schema`, `status`, `checks`, `launch_api`, optional `installation`, and an error with a stable code when blocked. Exit 0 means `compatible_for_preview`; exit 1 means blocked.

**An exit code 0 only means** the client responded to `horizon-client --launch-api` with a compatible protocol and required `--game-dir`, `--home` options. It does *not* prove the client has working resources, its GPU renderer starts, any `.hmod` content loads, or a window is embeddable.

**Security:** this command executes the local game binary with `--launch-api`. Run only binaries you trust; do not enter arbitrary downloads. Nothing is uploaded. It does not access user accounts or start/modify worlds.

## Next real-game acceptance test

After preflight passes, **the user** must run the existing Preview Bridge on the installed Horizon binary with their prepared assets and explicit permission:

```sh
python horizon_cli.py preview examples/ruby_demo.hstudio.json \
  --ctl "/absolute/path/to/horizon-ctl" --yes -o preview.json
```

This starts a **disposable** `StudioPreview` world, uses `horizon-ctl` to verify an actual item inventory delta, records the selected game's version, package SHA-256 and an evidence file, then shuts down. The session may fail if the selected build lacks the expected content-mod protocol or ready resources; that failure is useful evidence and must not be misrepresented.

Only after the real content-load gate passes should IDE-002 pursue an actually playable child game viewport on Windows with proper native input, DPI, resize, and process ownership. Further functionality such as native Rust source-mixin mods is a different **compile + restart** workflow and requires explicit trust.

Related references: [ADR 0004, draft PR #37](https://github.com/pneqnp-iswr/horizon-studio/pull/37), [Preview Bridge](architecture/PREVIEW_BRIDGE.md), [Game Content Smoke](GAME_CONTENT_SMOKE.md).

## Test coverage

`python -m unittest tests.test_ide_preflight` uses stand-in game executables for protocol checks and error handling. It does **not** claim that CI ran actual Minecraft or embedded a native renderer.

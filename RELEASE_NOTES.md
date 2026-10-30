# Horizon Studio 0.7.0 — Project Core

Windows portable alpha release of the Horizon Studio offline editor.

## Download

Download **`HorizonStudio-0.7.0-Windows-x64.exe`** from the `v0.7.0` release assets and run it on Windows 10/11 x64; Python is not required. Compare its SHA-256 with `SHA256SUMS.txt`. `build-manifest.json` records the commit, toolchain, test gates and smoke-test checks of this exact build.

## New since 0.6.0

- **Canonical project format `studio.project/1`** with stable object IDs: renaming a block or item keeps its identity and recipe references. Older `.hstudio.json` files (schemas 2–4) open and migrate automatically and build byte-identical `.hmod` packages.
- **Disk workspaces**: debounced autosave next to the browser copy, recovery after a crash or in a fresh browser, and an explicit *Restore disk* / *Keep editor* choice when another tab changed the project (no silent overwrite).
- **Undo / Redo** for edits, recipes, structures and Source Workbench overrides (buttons, Ctrl+Z, Ctrl+Shift+Z / Ctrl+Y).
- `.hmod` exports are byte-identical on Windows and Linux; for the bundled examples these are exactly the packages the official `cargo-horizon-mod` checker (pinned Horizon `d2186eb`) accepted.
- Command line: `migrate` and `graph` (reference diagnostics).
- Narrow windows keep every control: the project sidebar becomes a drawer below 1100 px, and phones get a top bar. Source Workbench shows unique file paths. The editor has its own icon.
- Hardened local API: per-session token, loopback Host and Origin checks for every request.

## How this build was verified

Before the executable was built, the tagged commit passed: Python tests on 3.11/3.12 (Ubuntu and Windows), the editor's Node tests, 13 browser end-to-end scenarios in Chromium and the official Horizon checker on all example projects. The built executable then passed its self-test twice (scripts, EN/RU, project open/save, workspace persistence across launches, export of the officially checked package bytes, clean shutdown) and a normal GUI launch.

## Important limitations

- Loading Studio mods in the **Horizon game has not been verified** (HS-002); passing the official static check is not the same as loading in game.
- Projects saved by 0.7 use `studio.project/1`, which 0.6 cannot open. 0.7 opens all older files.
- The executable is **unsigned**; SmartScreen may warn. No game executables, accounts, resource packs or authentication bypasses are included.
- The executable is an **editor/launcher**, not the Horizon game client.

See [README](https://github.com/pneqnp-iswr/horizon-studio#readme), [CHANGELOG](https://github.com/pneqnp-iswr/horizon-studio/blob/master/CHANGELOG.md) and [Releasing](https://github.com/pneqnp-iswr/horizon-studio/blob/master/docs/RELEASING.md).

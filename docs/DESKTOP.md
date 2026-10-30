# Horizon Studio desktop application (preview)

Horizon Studio runs as **one native window**: a Tauri 2 shell (`desktop/`) hosts the same editor the browser build
uses, served by the bundled project core on a private loopback port. Why this design, the alternatives and the
measurements: [ADR 0002](adr/0002-desktop-shell.md).

> **Status: preview.** CI builds a Windows installer and a portable folder for every change (`desktop.yml`, artifacts
> kept 14 days). They are not published releases. The verified release stays the 0.7 single EXE until the gates in
> ADR 0002 are met. The installer and executables are **unsigned**.

<p align="center">
  <img src="screenshots/desktop/desktop-1440x900-recipes.png" alt="Horizon Studio desktop window at 1440 by 900: top bar with project actions, activity rail, project explorer, recipe canvas with two recipe cards, recipe properties on the right, status bar showing the desktop shell version" width="100%" />
</p>

## Using it

- **Windows installer:** `HorizonStudio-Desktop-<version>-preview-<sha>-Windows-x64-setup.exe` installs per user (no
  administrator rights) into `%LOCALAPPDATA%\Horizon Studio`, in English or Russian, and adds an uninstaller.
- **Portable:** unzip `HorizonStudio-Desktop-…-Windows-x64.zip` and run `HorizonStudio.exe`; keep the `core` folder
  next to it.
- Projects open with **Open project** and save with **Save project** through native file dialogs. Exports
  (`.hmod`, source ZIP) use the native *Save as* dialog; cancelling writes nothing.
- Autosaved workspaces are shared with the browser build and 0.7: `~/.horizon-studio/workspaces`.
- WebView2 is required (part of current Windows 10 and 11).

## How it is put together

| Part | File | Role |
|---|---|---|
| Shell | `desktop/src/main.rs` | window, navigation guard, IPC commands, smoke report |
| Core process | `desktop/src/core.rs` | finds and starts the core, checks its handshake, stops it |
| Options | `desktop/src/options.rs` | `--smoke-report`, `--smoke-hold`, `--smoke-timeout`, `--window-size` |
| Splash | `desktop/splash/` | bundled loading screen; shows the core's error and log path if it cannot start |
| Core | `launcher.py --serve` | protocol `horizon-studio.core/1`: one JSON line with the URL, then serves until stdin closes |
| Bridge | `desktop_bridge.js` | in the editor: native *Save as*, the ready signal; inactive in a browser |
| Icons | `desktop/icons/` | generated from the pixel mark by `scripts/make_desktop_icons.py` |

### Security

- The window shows only the bundled splash and the core's exact origin (`http://127.0.0.1:<port>`); every other
  navigation is refused. `https` links open in the system browser.
- The editor can call two commands, `desktop_ready` and `save_file`. They are declared in an app manifest
  (`desktop/build.rs`), so the ACL applies, and granted at runtime to the core's origin and the `main` window only.
  The splash page has none.
- `save_file` accepts a bare file name (no paths or reserved characters), at most 256 MiB, shows a native dialog and
  writes atomically (temporary file, then rename).
- The core keeps its own protections: random port, session token, Host and Origin checks, loopback only.
- No arbitrary code runs in the shell or the core. Native `.hnmod` authoring is not part of this build (HS-010).

### Lifecycle

The shell starts the core with piped stdin and stdout and waits up to 60 s for the handshake. Closing the window
closes the core's stdin; the core shuts its server down and exits with 0. If the shell crashes or is killed, the
operating system closes the pipe and the core exits the same way. The core's stderr goes to `core.log` in the
application's log directory (`%LOCALAPPDATA%\io.github.pneqnp-iswr.horizonstudio\logs` on Windows).

## Building

Prerequisites: Rust 1.90+, Python 3.11+, Node 22 (only for the Tauri CLI), and on Linux WebKitGTK 4.1
(`libwebkit2gtk-4.1-dev libgtk-3-dev libsoup-3.0-dev librsvg2-dev`).

```sh
# development: the shell starts `python launcher.py --serve` from the repository
cd desktop && cargo run

# release: freeze the core, then build the shell and installer with the core bundled as core/
python -m pip install pyinstaller==6.16.0
python scripts/build_desktop.py
cd desktop && npx --yes @tauri-apps/cli@2.12.4 build --bundles nsis --config tauri.release.conf.json
```

Release builds never fall back to a Python interpreter found on the system; only debug builds do.

## Tests and evidence

| What | Where |
|---|---|
| Shell unit tests (handshake, navigation guard, file names, atomic writes, options) | `cd desktop && cargo test` |
| Core protocol and lifecycle | `tests/test_launcher.py` |
| Shell contracts without Rust (versions, commands vs ACL, CSP, icons, splash) | `tests/test_desktop.py` |
| Bridge | `tests/test_desktop_bridge.cjs` |
| Real application runs | `scripts/desktop_probe.py` in `desktop.yml`: Linux (Xvfb) and Windows (portable cold, warm, 960×600; installed) |

`desktop_probe.py` starts the real executable with `--smoke-report`, waits for the editor's ready signal, records the
process tree's memory and a screenshot, then waits for the shell to exit on its own; the report includes the core's
exit code.

Screenshots of the running desktop application (release shell with the frozen core, Linux WebKitGTK, captured by
driving the real window with `xdotool`): [`screenshots/desktop/`](screenshots/desktop/). Windows screenshots are in
each `desktop.yml` run's `desktop-windows-evidence` artifact.

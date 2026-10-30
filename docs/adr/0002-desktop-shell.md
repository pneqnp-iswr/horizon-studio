# ADR 0002: The desktop shell is Tauri 2 around the existing editor and Python core

- **Status:** accepted for migration slice A (preview builds); the verified 0.7 Windows EXE stays the released product until the desktop build reaches parity (gates below)
- **Date:** 2026-10-30
- **Deciders:** maintainer (repository owner) on the recommendation of this ADR
- **Supersedes:** nothing. Builds on [ADR 0001](0001-canonical-project-document.md): one canonical project model, `studio.project/1`

## Context

Up to 0.7, Horizon Studio was two windows: a small Tk launcher that started a loopback server on port 8787, and the
user's own browser, which showed the editor. The screenshot audit of 0.7 found: two unrelated windows, browser chrome
around the editor, a fixed port that collides with a second copy, and nothing that looked like the product's
pixel-art identity. The goal is one native window that opens, saves and exports like a desktop application.

Constraints:

1. **Do not lose verified behaviour.** The Python core is the only code with official-static evidence: the
   `cargo-horizon-mod check` at Horizon `d2186eb` accepted its packages byte for byte
   (`ee3e1c87…` for the Ruby demo), and 202 Python tests, 28 Node tests and 19 browser E2E scenarios cover the editor.
   A rewrite would discard that evidence until it is rebuilt.
2. **Head towards Rust.** Horizon is a Rust engine. Later milestones (an in-process checker, a wgpu viewport,
   native mod authoring) benefit from a Rust host.
3. **Trust boundaries stay explicit.** No remote content in the window, no arbitrary code in the application
   process, and native `.hnmod` authoring stays a separate, warned capability (HS-010).
4. **Windows first**, without breaking Linux and macOS development.

## Options

| | Option | What it would mean here |
|---|---|---|
| A | **Tauri 2 + existing web editor + Python core as a child process** | A Rust shell with the system web view (WebView2 / WebKitGTK / WKWebView) shows the editor, which is served by the frozen core on a private loopback port. |
| B | egui / eframe + wgpu | Rewrite the whole editor UI in immediate-mode Rust; reuse the core over a protocol or port it to Rust. |
| C | Slint | Rewrite the UI in `.slint` markup with a Rust backend. |
| D | Qt / QML (PySide6) | Rewrite the UI in QML, keep the core in-process in Python. |
| E | Electron | Same web editor, bundled Chromium and Node. |
| F | pywebview | Python-native window around the same web editor. |

## Decision matrix

Scores from 1 (poor) to 5 (best). **Only option A was prototyped and measured**; the other options are rated from
their documented properties and the size of the rewrite they need, and are marked as such.

| Criterion (weight) | A Tauri 2 | B egui | C Slint | D Qt/QML | E Electron | F pywebview |
|---|---|---|---|---|---|---|
| Keeps verified behaviour without a rewrite (25) | **5**, measured: same editor, same core, all suites pass | 1 (full UI rewrite) | 1 (full UI rewrite) | 2 (UI rewrite, core kept) | 5 | 5 |
| Native desktop experience: one window, native dialogs, installer (15) | **4**, measured: single window, native Save As, NSIS install and uninstall | 4 | 4 | 5 | 3 | 3 |
| Fit with Rust and Horizon (15) | **5**: Rust host; can link Horizon crates later | 5 | 4 | 1 | 1 | 1 |
| Security model (10) | **5**, measured: navigation guard, runtime IPC capability for one origin and window | 4 | 4 | 3 | 2 | 2 |
| Footprint (10) | **4**, measured: installer 8.05 MB, ~350 MB RSS for the process tree | 5 | 5 | 2 | 1 | 4 |
| 3D and pixel-art rendering ceiling (10) | 4: WebGL now, wgpu later in the Rust host | 5 | 3 | 4 | 4 | 3 |
| Packaging and CI on Windows (10) | **5**, measured: CI builds, installs, smoke-tests and uninstalls in ~6 min | 4 | 4 | 3 | 4 | 3 |
| Accessibility, ecosystem, velocity (5) | 4: browser accessibility tree (UIA through WebView2) | 2 | 2 | 4 | 4 | 3 |
| **Weighted total (out of 500)** | **460** | 335 | 300 | 270 | 330 | 330 |

Totals are the sum of score × weight. The ranking holds even if "keeps verified behaviour" is halved: A still leads,
because it is the only option that is also a Rust host.

## Measured evidence for option A

All numbers are from real runs of the real application, not estimates.

**Windows** ([run 41143213331](https://github.com/pneqnp-iswr/horizon-studio/actions/runs/41143213331), `windows-latest`,
WebView2; `scripts/desktop_probe.py` launches the app, waits until the editor reports ready, then records the
process tree and a screenshot):

| Run | Core ready | Editor ready | Process-tree RSS |
|---|---|---|---|
| Portable, first launch | 2,836 ms | 3,239 ms | 370 MB |
| Portable, second launch | 740 ms | 928 ms | 362 MB |
| Portable, 960×600 window | 604 ms | 783 ms | 349 MB |
| Installed with NSIS (`/S`), first launch | 875 ms | 1,237 ms | 352 MB |

Process tree at the second launch: shell 29 MB, core 26 MB, WebView2 (6 processes) 299 MB, `conhost` 8 MB.
Sizes: shell 4.32 MB, frozen core folder 20.04 MB, portable zip 10.36 MB, installer 8.05 MB. For comparison, the
0.7.0 single-file EXE is 12.17 MB and unpacks itself to a temporary folder on every launch.

**Linux** (WebKitGTK 2.52 under Xvfb, release shell with the frozen core): core ready 145 ms, editor ready 819 ms,
process tree 375 MB. A forced `kill -9` of the shell makes the core exit through stdin EOF (no orphan server).

The first Windows launch is slower because the system scans the freshly unpacked executables; later launches stay
under one second. The memory is mostly the system web view.

## Architecture

```
HorizonStudio.exe (Rust, Tauri 2)                 core/horizon-studio-core.exe (frozen Python, launcher.py --serve)
 ├─ splash page (bundled)                          ├─ binds 127.0.0.1:<random port>, prints one JSON handshake line
 ├─ spawns the core with piped stdin/stdout  ───►  │   {"protocol":"horizon-studio.core/1","event":"ready","url":…}
 ├─ checks the handshake (loopback http only)      ├─ serves the editor and the API (session token, Host/Origin checks)
 ├─ grants editor commands to that origin only     └─ exits on stdin EOF: shell exit or crash stops it
 ├─ navigates the window to the editor
 └─ native Save As (atomic write), https links → system browser
```

- **Navigation guard.** The window may show only the bundled splash and the core's exact origin; everything else is
  refused, and `https` links open in the system browser.
- **IPC.** The editor reaches two commands, `desktop_ready` and `save_file`. They are declared in an app manifest, so
  the ACL applies, and granted at runtime to `http://127.0.0.1:<port>/*` and the `main` window only. The splash has
  no commands.
- **Core lifetime.** The shell holds the core's stdin. Closing it is the shutdown signal; the shell also waits
  (10 s) and kills as a last resort. Core stderr goes to `core.log` in the app's log directory.
- **No fixed port.** Each launch picks a free port, so two copies, or the 0.7 app, do not collide.
- **Same editor, same core.** `index.html` and the core are the same files the browser build uses; `desktop_bridge.js`
  switches downloads to the native dialog only when it runs in the shell.

## Consequences

- The release keeps two products for a while: the verified 0.7 single EXE (Tk launcher + browser) and the
  desktop preview (installer or portable zip from `desktop.yml`). Only the first is published.
- The Rust toolchain and a web view become build requirements; WebView2 is present on current Windows 10 and 11.
- The editor stays HTML, CSS and JavaScript for now. Panels that need native performance (a wgpu viewport,
  in-process validation) can move into the Rust host one at a time behind the same IPC boundary.
- Memory is dominated by the system web view (~300 MB). That is the price of keeping the verified editor; it is
  tracked as a budget below rather than hidden.

## Budgets (tracked by `desktop.yml`)

| Metric | Budget | Measured |
|---|---|---|
| Editor ready, second launch, Windows | ≤ 1,500 ms | 928 ms |
| Editor ready, first launch, Windows | ≤ 5,000 ms | 3,239 ms |
| Process-tree RSS after start | ≤ 450 MB | 349–370 MB |
| Installer size | ≤ 15 MB | 8.05 MB |
| Core shutdown after the window closes | ≤ 2,000 ms, exit code 0 | 75–405 ms, exit code 0 |

## Gates before the desktop build replaces the 0.7 EXE

1. Parity: every 0.7 workflow passes in the shell. Open, save, export `.hmod` and source ZIP, the Source Workbench,
   undo/redo, workspace recovery and EN/RU are covered today by the same E2E suite in a browser, and by smoke runs
   in the shell. Still missing: an E2E run driving the shell's own window (WebDriver for WebView2).
2. Release pipeline: `windows-release.yml` builds, smoke-tests and publishes the desktop artifacts with the same
   same-commit gates and API verification as the EXE (rules in [RELEASING.md](../RELEASING.md)).
3. Code signing decision recorded, so the installer can be honest about signing (it is unsigned today).
4. A user-visible migration note: settings and autosaved workspaces are shared (`~/.horizon-studio/workspaces`),
   which the shell already does.

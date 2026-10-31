# Horizon Studio 0.8.0 — Desktop Studio

The first release of the native desktop app, published **as an unsigned prerelease**. The classic single-file
launcher stays available in the same release.

## Download

| File | What it is |
|---|---|
| `HorizonStudio-0.8.0-Windows-x64-setup.exe` | Installer for the desktop app (per user, no administrator rights) |
| `HorizonStudio-0.8.0-Windows-x64-portable.zip` | Portable desktop app: extract the **whole** archive and run `HorizonStudio.exe`. It needs the `core\` folder next to it; it is not a single-file executable |
| `HorizonStudio-0.8.0-Windows-x64.exe` | The classic launcher, which opens the editor in your browser |
| `desktop-manifest.json`, `build-manifest.json` | What each build proved: commit, gates, smoke runs, signing status, SHA-256 |
| `SHA256SUMS.txt` | Checksums of every file above |

Windows 10/11 x64. Python is not required. Compare SHA-256 values with `SHA256SUMS.txt`.

**Unsigned.** There is no code-signing certificate, so Windows SmartScreen will warn ("Windows protected your PC" →
*More info* → *Run anyway*). Each manifest records the Authenticode status Windows reported for every executable
(`NotSigned`), and nothing claims a publisher. The repository owner chose this policy (docs/SIGNING.md).

## New

- **Desktop app.** The editor in its own window: a Tauri 2 shell around the same project core.
  - The core gets a private session token over a pipe, and its socket is exclusive.
  - The shell owns the core's processes: a Windows Job Object stops them even if the app crashes.
  - Saves to disk are durable.
  - When the core is lost, the window shows a failure screen instead of a blank page.
  - It reopens your last project in your language at every launch.
- **One history for you and the AI (HS-020).**
  - Every edit is a transaction the core checks against the revision you started from.
  - Undo and redo survive restarts.
  - A second tab or window can never overwrite newer work silently.
  - Plugin data, effects and the engine target survive every step byte for byte.
- **AI Creator.**
  - Ask for a material set, a change to a block or item, or an effect.
  - See every field it would change, then apply it as one undoable step or reject it.
  - The built-in provider is a deterministic **simulation**, and is labelled as one.
  - A Claude provider is included: it needs the `anthropic` package, your API key in the system credential store, and
    your consent; it never runs offline. **It has not been tested against the live API.**
- **VFX Studio.**
  - Effects with several emitters: sparks, flash and smoke templates; duplicate, reorder, delete.
  - Bursts, shape and direction, blending, and keyframed size, opacity and colour curves.
  - Particle budgets per quality profile, and burst marks on the timeline.
  - Effects are a Studio preview and are not exported to the game: Horizon has no custom-particle contract.
- **Preview Bridge** (developer tool, `horizon_cli.py preview`). Game content counts as confirmed only when the
  package's own items appear in real inventory slots, and an item the package does not define is refused. A `give`
  that merely answers OK is not proof.
- **Security.**
  - Scripts only from the app itself: no inline scripts.
  - Content from opened files is escaped wherever it is shown.
  - External links open only for `https://github.com`.
  - The core log is private.

## Fixed

- **On Windows the editor could start without one of its scripts.** A page load opens up to six connections to
  the local core at once, and the core's listen backlog was 5, so Windows sometimes refused one. The desktop window
  then started without its bridge and showed a workspace error. The backlog is now 128, in the browser launcher and
  the desktop app; a test fills it before the core accepts anything.

## Moving from 0.7

Project files, autosaved workspaces and packages carry over unchanged: tested on files written by the 0.7.0 core. Your
browser tab's own copy does not move, and undo history starts fresh. See *Moving from the 0.7 EXE*
(docs/MIGRATING_FROM_0.7.md).

## How this build was verified

All gates ran on the tagged commit before anything was published:
- 333 Python tests (3.11 and 3.12, Ubuntu and Windows);
- 50 Node tests and 38 browser end-to-end scenarios in Chromium;
- Rust tests: 27 on Linux and 25 on Windows;
- the official Horizon checker on every example project.

The desktop app then passed:
- smoke runs of the portable build (cold, warm and four window sizes);
- the portable ZIP launched exactly as shipped;
- an install, smoke and uninstall cycle;
- ten functional scenarios on the real window, including twelve reloads in a row.

The classic launcher passed its self-test twice and a normal GUI launch. Every asset was then verified through the
GitHub API.

## Important limitations

- Loading Studio mods in the **Horizon game has not been verified** (HS-002). Passing the official static check is
  not the same as loading in game, and the Preview Bridge has not driven a real client yet.
- The executables are **unsigned**.
- VFX effects stay in the project and are never exported.
- No game executables, accounts, resource packs or authentication bypasses are included. The app is an editor, not
  the Horizon game client.

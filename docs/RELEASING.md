# Releasing Horizon Studio

## Rules

1. **Every version bump requires a verified Windows EXE GitHub release.** Changing `VERSION` on `master` is a promise to ship `HorizonStudio-<version>-Windows-x64.exe`; the version is not released until that file is downloadable from its GitHub release.
2. **A release is not complete until its assets, checksums and metadata are verified through the GitHub API** (`scripts/release.py verify`). "Workflow started" or "build succeeded" is not a release.
3. **All release claims correspond to the exact tagged source commit.** Notes, README panels and the build manifest describe only what that commit contains.
4. **No version bump without updated release notes and test evidence.** `RELEASE_NOTES.md` must be about the new version (checked by `scripts/release.py check-notes` and `tests/test_release.py`), and every release gate must pass on that commit.
5. **Development continues after the release.** A release is a delivery, not the end of the roadmap.
6. **The pixel-art roadmap reflects verified engineering status.** Update `docs/roadmap/roadmap.json` with evidence; never mark HS-002 or any game-level claim done without in-game evidence.

## How a release runs

`.github/workflows/windows-release.yml` runs on a push to `master` that changes `VERSION` (or manually on `master`; any other ref is refused):

| Job | What must succeed |
|---|---|
| `guard` | ref is `master`; `scripts/check_release_metadata.py`; `RELEASE_NOTES.md` names this version and its executable only |
| `tests` | the whole `tests.yml` on the same commit: Python 3.11/3.12 on Ubuntu and Windows, Node 22 editor modules, Playwright Chromium E2E |
| `official` | `official-content-check.yml` on the same commit: pinned `cargo-horizon-mod` accepts every example and migrated fixture |
| `build` (Windows, read-only) | PyInstaller one-file build from `studio.BUNDLED_FILES`; frozen `--smoke-test` (all scripts and assets, EN/RU, session, project open/save, workspace write/recover across a server restart, exported `.hmod` equals the officially checked bytes, clean shutdown); a second launch must recover the first launch's workspace; a normal GUI launch must serve the editor on `127.0.0.1:8787`; then `build-manifest.json` and `SHA256SUMS.txt` are produced from this build |
| `publish` (only job with `contents: write`) | `scripts/release.py publish`: tag must not point elsewhere; a **draft** release is created on the tested commit, all three assets uploaded, re-read and compared (size and SHA-256), and only then published; `scripts/release.py verify` re-reads everything independently and fetches the download URL |

Only artifacts built in the same run are published; nothing from pull requests reaches the privileged job.

## Re-runs and failures

- Release already published and consistent → `already verified`; nothing is uploaded or replaced, even if a rebuild produced different bytes.
- Published release missing an asset, or with checksums that do not match → the run fails with an integrity error. Fixing it needs a human decision (for example a new patch version); assets are never replaced silently.
- Tag pointing to another commit → the run stops. Tags are never moved or deleted by automation.
- Interrupted run leaving a **draft** → a re-run completes it if the draft's existing assets are byte-identical to the new build; otherwise it stops and the draft must be inspected (it is not public).
- Wrong notes on an already published release → fix `docs/releases/v<version>.md` and run **Repair published release notes** (`release-notes-repair.yml`), which changes the description only.

## Preparing a version

1. Finish and verify the milestone work; CI green on `master`.
2. In one pull request: bump `VERSION`; write `RELEASE_NOTES.md` for that version (title `# Horizon Studio <version> — <name>`, executable `HorizonStudio-<version>-Windows-x64.exe`); update `CHANGELOG.md`, `docs/FEATURE_MATRIX.md`, the README version strings; copy the notes to `docs/releases/v<version>.md`.
3. After merge, watch the release run to the end and confirm `scripts/release.py verify` passed. Then record the verified release (size, SHA-256, commit) in `docs/releases/releases.json` so both READMEs show it.

## Signing and provenance

Executables are **unsigned**; `build-manifest.json` says so. The manifest records version, tag, commit, platform, Python and PyInstaller versions, executable size and SHA-256, build time (UTC), gate results and smoke-test checks. It is evidence of how this build was made, not a code signature.

## Desktop release candidates (preview, not published)

The Tauri desktop build is not released yet; the verified 0.7 EXE stays the released product until every gate in
[ADR 0002](adr/0002-desktop-shell.md) holds. Every `desktop.yml` run on Windows still builds a full candidate, so the
pipeline is proven before it is trusted:

1. The core is frozen and smoke-tested. The shell and the NSIS installer are built, the portable folder is zipped, and
   the build's own smoke runs, an install–smoke–uninstall cycle and functional E2E on the real window all pass.
2. The portable ZIP is launched exactly as shipped (extracted to a fresh folder).
3. `Get-AuthenticodeSignature` records each shipped file's signing status. Nothing is described as signed unless
   Windows says `Valid`.
4. `scripts/desktop_release.py` writes `desktop-manifest.json` (`horizon-studio.desktop-manifest/1`) and
   `SHA256SUMS.txt`, then verifies every artifact against both. The manifest holds:
   - the commit;
   - each artifact's size and SHA-256;
   - the portable ZIP's layout (the shell needs its `core/` folder; it is not a single-file executable);
   - the smoke results;
   - the signing status;
   - every ADR 0002 parity gate with `passed` true or false;
   - `release_ready`, which is true only when all of them pass and the signing state is not mixed.
5. The candidate and its manifest are kept as a workflow artifact for 14 days.

The script cannot publish: it has no GitHub client, and a test checks that. Publishing desktop artifacts will be added
to `windows-release.yml` with the same same-commit gates and API verification as the EXE, and only together with a
recorded signing decision and a migration note. No VERSION bump comes before that.

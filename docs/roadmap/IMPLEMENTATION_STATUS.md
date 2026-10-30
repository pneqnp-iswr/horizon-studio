# Horizon Studio — Implementation Status

Last verified repository baseline before this work: `4d8c5e7cab8781690e92f74157cd2448d89f67f1` (2026-10-30).

## Roadmap

- Phase: **F0 / Iteration I — Verified Mod Compatibility & Security**.
- HS-003: **completed** in PR #1, merged at `36c3bb6964e5476831de47499ae0610dca738855`; CI passed on Python 3.11/3.12 on Ubuntu and Windows.
- HS-001: **adapter implemented** in PR #3 (`3ed765a6c9c91b69b73f2f3fe7161006fd5d69f5`). CLI `verify` checks official JSON status, kind/API, size and SHA-256; contract tests pass. **Not complete** as an end-to-end milestone until a real pinned official checker run is recorded.
- HS-002: pending — controlled real-game smoke fixture/evidence.
- HS-004: **completed** in PR #2, merged at `6c61770c02d68d53c10035314405f1dba72c2c3d`; CI passed on Windows and Ubuntu.

## Current verified vs experimental

- Existing Studio builds content `.hmod` ZIPs and offers local editor previews; these are NOT equivalent to in-game verification.
- New API security checks: exact loopback Host:port, Origin, Fetch Metadata and per-server CSRF token for POST; strict upload media type.
- The `/api/session` endpoint is only intended for same-origin local clients. Tokens are per HTTP-server process and never persisted in project storage.
- No official Horizon validator or real-game smoke test has been executed as part of HS-003.
- Engine profile used by roadmap audit: upstream `d2186eb9aa022a64a8b26e6989a04e44fba99ee7`. This is reference-only, not a passing compatibility result.

## Next concrete steps

1. Execute the new pinned official checker GitHub Actions workflow, inspect the real report and archive evidence. Fix any detected `.hmod` incompatibilities instead of weakening checks.
2. Add opt-in game-load smoke tests where legally prepared game data exists (HS-002).
3. Track actual compatibility evidence by engine SHA; do not promote local smoke to in-game validation.

Latest merged development commit at this checkpoint: `3ed765a6c9c91b69b73f2f3fe7161006fd5d69f5`. Python CI at this commit: 88 tests on Ubuntu Python 3.12, all four OS/Python jobs passed (GitHub Actions run `41076736098`). The run used a mocked validator, not installed official Cargo tooling.

Do not treat a CI-only pass as real Horizon game compatibility.

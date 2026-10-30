# Horizon Studio — Implementation Status

Last verified repository baseline before this work: `4d8c5e7cab8781690e92f74157cd2448d89f67f1` (2026-10-30).

## Roadmap

- Phase: **F0 / Iteration I — Verified Mod Compatibility & Security**.
- HS-003: **completed** in PR #1, merged at `36c3bb6964e5476831de47499ae0610dca738855`; CI passed on Python 3.11/3.12 on Ubuntu and Windows.
- HS-001: pending — official pinned `.hmod` validator integration.
- HS-002: pending — controlled real-game smoke fixture/evidence.
- HS-004: in progress — docs corrected to 0.6.0; new CI assertions pending.

## Current verified vs experimental

- Existing Studio builds content `.hmod` ZIPs and offers local editor previews; these are NOT equivalent to in-game verification.
- New API security checks: exact loopback Host:port, Origin, Fetch Metadata and per-server CSRF token for POST; strict upload media type.
- The `/api/session` endpoint is only intended for same-origin local clients. Tokens are per HTTP-server process and never persisted in project storage.
- No official Horizon validator or real-game smoke test has been executed as part of HS-003.
- Engine profile used by roadmap audit: upstream `d2186eb9aa022a64a8b26e6989a04e44fba99ee7`. This is reference-only, not a passing compatibility result.

## Next concrete steps

1. Verify HS-004 release-metadata checks and merge only after CI is green.
2. Integrate a pinned official `cargo horizon-mod check` adapter and capture reliable logs (HS-001).
3. Add opt-in game-load smoke tests where legally prepared game data exists (HS-002).

Do not treat a CI-only pass as real Horizon game compatibility.

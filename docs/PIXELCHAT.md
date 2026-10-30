# PixelChat — two-client network proof of concept

**Status:** prototype (PC-001/PC-002 groundwork), **NOT a Horizon `.hmod`, `.hnmod`, Fabric mod, or Paper plugin**. This demo proves server-mediated sharing of original pixel emoji shortcodes and small GIF/PNG assets **between browsers**, not rendering in the actual game. A native implementation requires the engine hooks and compatibility tests below. Tracking: [PixelChat epic #11](https://github.com/pneqnp-iswr/horizon-studio/issues/11).

## Try it (Python 3.11+, no dependencies)

```sh
python -m pixelchat.demo_server --port 8788
# Open http://127.0.0.1:8788/ in two tabs; join as Alice and Bob.
# Send :heart: or pick a pixel emoji. Attach a small GIF or PNG.
python -m unittest discover -s tests -p test_pixelchat.py -v
```

**What is real in the demo:** a real loopback HTTP relay, independently joined browser sessions, content-addressed file upload, GIF/PNG bounded inspection, identity bound to server-issued *demo* session tokens (not Minecraft player authentication), message sequencing, fallback text, 2-client HTTP delivery, and visual playback by the browser's native GIF decoder. Uploaded bytes stay in memory and disappear when the process exits. Original 5×5 pixel emoji glyphs are drawn locally from code. No URLs, tracking or remote media search.

**Limits:** local-only HTTP prototype; no TLS, persistence, server-moderated accounts, recipient mod negotiation, signed Minecraft chat binding, distributed cache, reconnect gap recovery, partial upload streaming, professional GIF decoding certification or frame-level rendering engine. No WebP or remote URLs in this version. The server does not prove that a GIF's LZW data or PNG compression stream fully decodes; visual decoding remains the recipient browser's responsibility. Not for public network exposure or untrusted players. GIF upload size ≤512 KiB; width/height ≤256; frames ≤64; total full-screen frame-pixels ≤4,194,304. Retains at most 16 unique media files (8 MiB) and 200 recent messages; per-token 8 messages/10 s.

**Tests and evidence:** 11 `unittest` cases passed locally (including independent HTTP connections simulating two players, malicious sender fields, rate limits, origin protection and invalid GIFs); inline JavaScript passes `node --check`. **Full Chromium browser E2E was not verified:** Playwright's local Chromium was blocked from loopback by the execution environment's administrator policy. No real-game tests have been run. CI should run Python tests on the PR.

## Real-game bridge: feasibility gate

At inspected upstream Horizon source, `NATIVE_HOOKS_API` is 21 and there is a `native_chat` helper for adding a **local line**, but this does not establish a public way for a third-party native mod to render inline animated media, capture signed player messages or deliver asset bytes through a mod channel. Existence of protocol `CUSTOM_PAYLOAD` types is also not enough: need upstream-supported, tested hooks for each direction and for both dedicated and LAN servers. No current `.hmod` content-only feature can supply arbitrary code.

| Required contract | Current evidence | Status |
| --- | --- | --- |
| Content-only `.hmod` JSON | Official `cargo-horizon-mod check` verifies sample content; not executable scripts | Insufficient |
| Native mod installation | `.hnmod` mixin bundles exist, executed with player's OS privileges | Experimental, pinned revision |
| Native local text append | `Game::native_chat(&str)` helper in `native_hooks.rs` | Only text; not an external GIF hook |
| Client media layers, chat input hook, controlled frame animation | No verified stable publicly exposed hook for this feature | Gap: inspect and prototype |
| Authenticated client↔server media channel | Play custom payload packet structures exist, no proven mod hook contract | Gap: inspect and prototype |
| Dedicated + LAN enforcement, signed chat association | Server commands hook exists (API 8); arbitrary attachment transport not demonstrated | Gap: verify |
| Vanilla/non-modded fallback | Plain text can be emitted, recipient must not require asset decoder | Design only |

**Future order:** native engine hook feasibility with exact upstream commit pin and 2-client in-game test → server-authoritative asset protocol and identity → inline GUI render with bounded animation/caching and reduced-motion mode → compatibility matrix (Horizon native vs Java/Fabric/Paper adapters) → release. Keep native code gated off until an end-to-end game client/server smoke test exists. Never replace vanilla signed messages with forged payloads or claim a plain client can render arbitrary GIF without a mod.

**Releases:** independently versioned Studio releases must include a tested Windows `.exe`, SHA-256 manifest and release notes. This prototype does **not** change the product version; it is not a release.

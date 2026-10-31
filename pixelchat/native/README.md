# PixelChat Native HUD — experimental bridge

This is the **first source-level Horizon-native PixelChat renderer proof**, not a complete animated GIF multiplayer mod. The separate `pixelchat/` HTTP browser prototype remains available.

The native bundle draws **four original five-by-five pixel emoji** (heart, star, smile, spark) in a top-right HUD panel using Horizon's `native_hud`, `native_fill`, `native_text`, and `Corners` hooks. It registers a mod under Options → Mods, remembers a show/hide setting, and provides `/pixelchat` as a local command. It does not transmit emoji, intercept signed chat, or decode GIF in Horizon.

## Verification levels

1. **Source / manifest:** injected hook target names and helper paths are checked in `tests/test_pixelchat_native.py`.
2. **Rust unit tests:** pixel geometry, render batching, bounds, original glyphs, and visibility persistence logic (`cargo test --manifest-path pixelchat/native/Cargo.toml`).
3. **Pending:** actual `horizon-mixins plan/apply` against pinned Horizon, compiling the modified game and proving HUD pixels via an in-game screenshot.
4. **Not started:** animated media runtime decode, authenticated server transport and actual network delivery in Horizon.

A successful Cargo unit test only proves the standalone logic. It **does not prove this native mixin builds into or runs in Horizon**. Do not distribute this source as a verified `.hnmod` until the actual engine integration gate passes.

## Compatibility

Adapted in architecture and hook names (not copied game art) from the MIT-licensed official [Coordinates HUD native mod](https://github.com/horizon-rust/horizon-mods/tree/main/native/coords-hud). `compatibility.json` pins the **reference mod's** tested Horizon commit and mixins revision. The new PixelChat mod **has not** independently passed those native build tests.

- Horizon engine reference: `4baa571566e39bfd6594988d3bb2bc85440c30e7` (Minecraft 26.3).
- Native hooks minimum: `1`.
- Horizon-mixins reference: `0d6b103c70633d8fd9443d8d0acd3aadaacedb06`.

## Developer checks

```sh
python -m unittest discover -s tests -p test_pixelchat_native.py -v
cargo +1.95.0 fmt --manifest-path pixelchat/native/Cargo.toml -- --check
cargo +1.95.0 test --manifest-path pixelchat/native/Cargo.toml --offline
```

The source-mixin packaging format is documented in [Horizon native mods](https://github.com/horizon-rust/horizon/blob/main/docs/native-mods.md), and the upstream source template in [horizon-native-mod-template](https://github.com/horizon-rust/horizon-native-mod-template). Full builds require separately pinned Horizon and horizon-mixins checkouts, the correct toolchain and player-provided prepared game resources; they have not been performed here.

## Next engineering step

Create an engine-side native adapter or upstream hook proposal for: (1) message arrival/render lifecycle and independent rich attachment entities; (2) client/server authenticated bounded binary channel; (3) a tested image atlas or texture upload route with GIF frame timing. Only then bind the existing `pixelchat/1` HTTP proof's semantics to actual Horizon player sessions. Keep vanilla signed chat intact and provide readable fallback for non-modded peers.

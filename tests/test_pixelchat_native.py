"""Static contract checks for experimental Rust-native PixelChat HUD source."""
from __future__ import annotations

import json
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "pixelchat" / "native"
MIXINS = NATIVE / "mixins" / "pixelchat_hud"


class NativePixelChatContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads((MIXINS / "horizon-mixin.toml").read_text(encoding="utf-8"))
        self.compat = json.loads((NATIVE / "compatibility.json").read_text(encoding="utf-8"))

    def test_declares_an_explicit_native_pin_not_a_content_only_mod(self):
        self.assertEqual(self.manifest["mod"]["id"], "pixelchat_hud")
        self.assertEqual(self.manifest["mod"]["version"], "0.1.0")
        self.assertEqual(self.manifest["compatibility"]["horizon_revision"], self.compat["horizon_revision"])
        self.assertEqual(self.compat["hooks"], 1)
        self.assertIn("horizon-mixins", self.compat["horizon_mixins_repository"])

    def test_every_module_and_hook_helper_file_exists(self):
        for module in self.manifest["module"]:
            self.assertEqual(module["file"], "crates/horizon-client/src/game.rs")
            self.assertTrue((MIXINS / module["source"]).is_file())
        hook_set = {e["id"]: e for e in self.manifest["injection"]}
        self.assertEqual(set(hook_set), {"hud", "command", "list", "settings", "settings-click"})
        for entry in hook_set.values():
            self.assertEqual(entry["kind"], "HEAD")
            self.assertTrue(entry["target"].startswith("horizon_client::game::native_hooks::"))
            self.assertTrue((MIXINS / entry["helper"]).is_file())
            self.assertTrue(entry["bindings"])

    def test_contract_does_not_falsely_claim_network_or_signed_chat(self):
        hook_targets = " ".join(e["target"] for e in self.manifest["injection"])
        for unexpected in ("custom_payload", "server_chat", "send_packet", "signed_chat", "net_recv"):
            self.assertNotIn(unexpected, hook_targets)
        # Native HUD is intentionally only a graphics / command surface.
        self.assertNotIn("native_server_tick", hook_targets)

    def test_standalone_library_uses_exact_injected_runtime_source(self):
        cargo = tomllib.loads((NATIVE / "Cargo.toml").read_text(encoding="utf-8"))
        self.assertEqual(cargo["lib"]["path"], "mixins/pixelchat_hud/runtime.rs")
        self.assertEqual(cargo["package"]["name"], "horizon-pixelchat-hud")
        self.assertIn("mod tests", (MIXINS / "runtime.rs").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

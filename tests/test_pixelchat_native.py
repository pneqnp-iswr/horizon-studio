"""Static contract checks for experimental Rust-native PixelChat HUD source."""
from __future__ import annotations

import json
import re
import io
import zipfile
import importlib.util
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

    def test_native_source_bundle_is_reproducible_and_contains_only_owned_source(self):
        source = NATIVE / "package.py"
        spec = importlib.util.spec_from_file_location("pixelchat_native_package", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        name, one = module.make_package()
        self.assertEqual(name, "pixelchat_hud-0.1.0.hnmod")
        _, two = module.make_package()
        self.assertEqual(one, two, "source package bytes must be deterministic")
        with zipfile.ZipFile(io.BytesIO(one)) as archive:
            names = set(archive.namelist())
            manifest = json.loads(archive.read("horizon-native.json"))
            self.assertEqual(manifest["id"], self.manifest["mod"]["id"])
            self.assertEqual(manifest["horizon"], self.compat["horizon_revision"])
            self.assertEqual(manifest["hooks"], 1)
            self.assertIn("mixins/pixelchat_hud/horizon-mixin.toml", names)
            self.assertIn("mixins/pixelchat_hud/runtime.rs", names)
            self.assertEqual(len(names), 8)
            self.assertTrue(all(name == "horizon-native.json" or name.endswith((".rs", ".toml")) for name in names))

    def test_native_palette_and_shape_match_browser_emojis(self):
        browser = (ROOT / "pixelchat" / "demo.html").read_text(encoding="utf-8")
        runtime = (MIXINS / "runtime.rs").read_text(encoding="utf-8")
        names = ["heart", "star", "smile", "spark"]
        shape_data = re.search(r"const shapes\\s*=\\s*\\{(.*?)\\};", browser, re.DOTALL)
        self.assertIsNotNone(shape_data)
        rust_data = re.search(r"pub const GLYPHS[^=]*=\\s*\\[(.*?)\\];", runtime, re.DOTALL)
        self.assertIsNotNone(rust_data)
        rust_rows = re.findall(r"\\[\\s*(0b[01]{5}(?:\\s*,\\s*0b[01]{5}){4})\\s*,?\\s*\\]", rust_data.group(1))
        self.assertEqual(len(rust_rows), 4)
        color_line = re.search(r"pub const COLORS[^;]+;", runtime)
        self.assertIsNotNone(color_line)
        colors = [int(value.replace("_", ""), 16) & 0xFFFFFF
                  for value in re.findall(r"0x[0-9A-F_]+", color_line.group(0))]
        self.assertEqual(len(colors), 4)
        for index, name in enumerate(names):
            with self.subTest(name=name):
                shape = re.search(rf"\\b{name}:\\[([^]]+)\\]", shape_data.group(1))
                self.assertIsNotNone(shape)
                js_rows = re.findall(r'"([01]{5})"', shape.group(1))
                native_rows = [value[2:] for value in re.findall(r"0b[01]{5}", rust_rows[index])]
                self.assertEqual(js_rows, native_rows)
                color = re.search(rf"\\b{name}:'#([0-9a-f]{{6}})'", browser)
                self.assertIsNotNone(color)
                self.assertEqual(colors[index], int(color.group(1), 16))


if __name__ == "__main__":
    unittest.main()

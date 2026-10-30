"""Desktop shell (desktop/, Tauri 2) contracts that can be checked without building Rust."""
import json
import re
import struct
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import render_ui_icons  # noqa: E402
from launcher import CORE_PROTOCOL  # noqa: E402

DESKTOP = ROOT / "desktop"
SVG_NS = "{http://www.w3.org/2000/svg}"


class DesktopShellContractTests(unittest.TestCase):
    def test_versions_match_the_release(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        cargo = (DESKTOP / "Cargo.toml").read_text(encoding="utf-8")
        self.assertIn(f'\nversion = "{version}"\n', cargo)

    def test_core_protocol_is_shared(self):
        core = (DESKTOP / "src" / "core.rs").read_text(encoding="utf-8")
        self.assertIn(f'pub const PROTOCOL: &str = "{CORE_PROTOCOL}";', core)

    def test_every_editor_command_is_declared_and_granted(self):
        build = (DESKTOP / "build.rs").read_text(encoding="utf-8")
        main = (DESKTOP / "src" / "main.rs").read_text(encoding="utf-8")
        declared = set(re.findall(r'"(\w+)"', re.search(r"commands\(&\[(.*?)\]\)", build).group(1)))
        handled = {name.strip() for name in re.search(r"generate_handler!\[(.*?)\]", main).group(1).split(",")}
        granted = set(re.findall(r'\.permission\("allow-([\w-]+)"\)', main))
        self.assertEqual(declared, handled)
        self.assertEqual({name.replace("_", "-") for name in declared}, granted)
        splash = json.loads((DESKTOP / "capabilities" / "splash.json").read_text(encoding="utf-8"))
        self.assertEqual(splash["permissions"], [], "the bundled splash page needs no commands")

    def test_config_is_locked_down(self):
        config = json.loads((DESKTOP / "tauri.conf.json").read_text(encoding="utf-8"))
        self.assertEqual(config["build"]["frontendDist"], "splash")
        self.assertNotIn("devUrl", config["build"])
        self.assertFalse(config["app"]["withGlobalTauri"])
        self.assertEqual(config["app"]["windows"], [], "the window is built in code with a navigation guard")
        csp = config["app"]["security"]["csp"]
        self.assertNotIn("unsafe-eval", csp)
        self.assertIn("script-src 'self'", csp)
        for icon in config["bundle"]["icon"]:
            self.assertTrue((DESKTOP / icon).is_file(), icon)

    def test_icons_are_rgba_pngs(self):
        for path in sorted((DESKTOP / "icons").glob("*.png")):
            with self.subTest(path.name):
                raw = path.read_bytes()
                self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")
                width, height, depth, color = struct.unpack(">IIBB", raw[16:26])
                self.assertEqual((width, depth, color), (height, 8, 6), "Tauri needs square 8-bit RGBA icons")

    def test_splash_is_self_contained(self):
        html = (DESKTOP / "splash" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>", html, "inline scripts would violate the shell CSP")
        for asset in re.findall(r'(?:src|href)="([^"]+)"', html):
            self.assertFalse(asset.startswith(("http:", "https:", "//")), asset)
            self.assertTrue((DESKTOP / "splash" / asset).is_file(), asset)
        self.assertEqual((DESKTOP / "splash" / "wordmark.svg").read_bytes(),
                         (ROOT / "assets" / "branding" / "horizon-studio-wordmark.svg").read_bytes())


class UiIconTests(unittest.TestCase):
    def test_committed_icons_are_current(self):
        self.assertEqual(render_ui_icons.main(["--check"]), 0)

    def test_icons_are_single_ink_crisp_masks(self):
        files = sorted((ROOT / "assets" / "editor" / "icons").glob("*.svg"))
        self.assertEqual({p.stem for p in files}, set(render_ui_icons.ICONS))
        for path in files:
            with self.subTest(path.name):
                raw = path.read_text(encoding="utf-8")
                tree = ET.fromstring(raw)
                self.assertEqual((tree.get("width"), tree.get("height")), ("16", "16"))
                self.assertEqual(tree.get("shape-rendering"), "crispEdges")
                self.assertEqual({p.get("fill") for p in tree.iter(f"{SVG_NS}path")}, {"#ffffff"})
                for banned in ("<script", "href=", "<image", "url("):
                    self.assertNotIn(banned, raw)


if __name__ == "__main__":
    unittest.main()

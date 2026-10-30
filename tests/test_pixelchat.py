"""PixelChat media contract, authenticated demo relay and two-client smoke tests."""
from __future__ import annotations

import base64
import http.client
import json
import threading
import struct
import zlib
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pixelchat.demo_server import DemoState, create_server  # noqa: E402
from pixelchat.media import MediaError, inspect_media  # noqa: E402
from pixelchat.protocol import PROTOCOL, ProtocolError, validate_message  # noqa: E402

# Independently decodable minimal GIF, commonly-used 1x1 white sample.
GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==")


class MediaTests(unittest.TestCase):
    def test_valid_gif_has_content_address_and_dimensions(self):
        m = inspect_media(GIF)
        self.assertEqual((m.mime, m.width, m.height, m.frames), ("image/gif", 1, 1, 1))
        self.assertEqual(len(m.digest), 64)
        self.assertEqual(m, inspect_media(GIF))

    def test_rejects_truncation_trailer_and_trailing_bytes(self):
        for invalid in (GIF[:-1], GIF + b"evil", b"GIF89a", GIF[:12], b"<svg/>"):
            with self.subTest(invalid=invalid[:15]), self.assertRaises(MediaError):
                inspect_media(invalid)

    def test_rejects_size_and_gif_header_bomb(self):
        with self.assertRaises(MediaError):
            inspect_media(GIF + b"x" * (512 * 1024))
        blown = bytearray(GIF)
        blown[6:10] = b"\xff\xff\xff\xff"
        with self.assertRaises(MediaError):
            inspect_media(bytes(blown))

    def test_rejects_65_gif_frames(self):
        # Replay the one sample image block 65 times; must stop at frame budget.
        frame = GIF[19:-1]
        oversized = GIF[:19] + frame * 65 + b"\x3b"
        with self.assertRaises(MediaError):
            inspect_media(oversized)

    def test_rejects_invalid_png(self):
        with self.assertRaises(MediaError):
            inspect_media(b"\x89PNG\r\n\x1a\n" + b"\0" * 60)

    def test_png_crc_accepts_valid_and_rejects_mutation(self):
        def chunk(typ: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data))
        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\xff")) + chunk(b"IEND", b""))
        meta = inspect_media(png)
        self.assertEqual((meta.mime, meta.width, meta.height), ("image/png", 1, 1))
        corrupt = bytearray(png)
        corrupt[44] ^= 1  # mutate compressed IDAT bytes; chunk CRC no longer matches
        with self.assertRaisesRegex(MediaError, "CRC"):
            inspect_media(bytes(corrupt))
        unsupported = png.replace(b"IHDR", b"IHDS", 1)
        with self.assertRaises(MediaError):
            inspect_media(unsupported)


class ProtocolTests(unittest.TestCase):
    def test_valid_text_and_known_attachment(self):
        sha = "a" * 64
        self.assertEqual(validate_message({"schema": PROTOCOL, "text": ":heart:", "sha256": sha, "alt": "cat"}, {sha}), (":heart:", sha, "cat"))

    def test_malicious_identity_and_unknown_hash_rejected(self):
        for body in (
            {"schema": PROTOCOL, "text": "hi", "sender": "admin"},
            {"schema": PROTOCOL, "text": "hi", "sha256": "a" * 64},
            {"schema": PROTOCOL, "text": "", "alt": "unused"},
            {"schema": "pixelchat/2", "text": "hi"},
            {"schema": PROTOCOL, "text": "hi\x00"},
        ):
            with self.subTest(body=body), self.assertRaises(ProtocolError):
                validate_message(body, set())


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.server = create_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, path, payload=None, token=None, content_type="application/json", origin=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        data = json.dumps(payload).encode() if content_type == "application/json" and payload is not None else payload
        headers = {"Content-Type": content_type}
        if token:
            headers["X-PixelChat-Session"] = token
        if origin:
            headers["Origin"] = origin
        if host:
            headers["Host"] = host
        conn.request(method, path, body=data, headers=headers)
        resp = conn.getresponse()
        result = resp.read()
        code = resp.status
        conn.close()
        if result.startswith(b"{"):
            return code, json.loads(result)
        return code, result

    def join(self, name):
        status, result = self.request("POST", "/api/join", {"name": name})
        self.assertEqual(status, 201, result)
        return result["token"]

    def test_two_clients_see_same_gif_and_pixel_shortcode(self):
        alice = self.join("Alice")
        bob = self.join("Bob")
        status, asset = self.request("POST", "/api/assets", GIF, alice, "application/octet-stream")
        self.assertEqual(status, 201, asset)
        sha = asset["asset"]["sha256"]
        status, sent = self.request("POST", "/api/messages", {"schema": PROTOCOL, "text": ":heart: Hello", "sha256": sha, "alt": "Dancing cat"}, alice)
        self.assertEqual(status, 201, sent)
        self.assertEqual(sent["message"]["sender"], "Alice")
        status, data = self.request("GET", "/api/messages?since=0", token=bob)
        self.assertEqual(status, 200, data)
        self.assertEqual(len(data["messages"]), 1)
        message = data["messages"][0]
        self.assertEqual(message["sha256"], sha)
        self.assertEqual(message["text"], ":heart: Hello")
        self.assertIn("[GIF/image: Dancing cat]", message["fallback"])
        status, raw = self.request("GET", "/api/assets/" + sha, token=bob)
        self.assertEqual(status, 200)
        self.assertEqual(raw, GIF)
        status, after = self.request("GET", "/api/messages?since=1", token=bob)
        self.assertEqual(after["messages"], [])

    def test_rejects_cross_origin_spoofed_sender_and_unauthorized_upload(self):
        alice = self.join("Alice")
        status, _ = self.request("POST", "/api/messages", {"schema": PROTOCOL, "text": "hello", "sender": "Bob"}, alice)
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/assets", GIF, None, "application/octet-stream")
        self.assertEqual(status, 401)
        status, _ = self.request("POST", "/api/join", {"name": "Mallory"}, origin="https://attacker.example")
        self.assertEqual(status, 403)
        status, _ = self.request("GET", "/", host="attacker.example")
        self.assertEqual(status, 403)

    def test_rate_limit_does_not_corrupt_history(self):
        alice = self.join("Alice")
        for _ in range(8):
            status, _ = self.request("POST", "/api/messages", {"schema": PROTOCOL, "text": "ok"}, alice)
            self.assertEqual(status, 201)
        status, _ = self.request("POST", "/api/messages", {"schema": PROTOCOL, "text": "one too many"}, alice)
        self.assertEqual(status, 400)
        status, result = self.request("GET", "/api/messages?since=0", token=alice)
        self.assertEqual(status, 200)
        self.assertEqual(len(result["messages"]), 8)

    def test_asset_deduplicated_and_not_executable_html(self):
        alice = self.join("Alice")
        for _ in range(2):
            status, _ = self.request("POST", "/api/assets", GIF, alice, "application/octet-stream")
            self.assertEqual(status, 201)
        status, _ = self.request("POST", "/api/assets", b"<script>x</script>", alice, "application/octet-stream")
        self.assertEqual(status, 400)

    def test_media_get_requires_session_and_publication(self):
        alice = self.join("Alice")
        bob = self.join("Bob")
        status, r = self.request("POST", "/api/assets", GIF, alice, "application/octet-stream")
        self.assertEqual(status, 201)
        sha = r["asset"]["sha256"]
        self.assertEqual(self.request("GET", "/api/assets/" + sha)[0], 401)
        self.assertEqual(self.request("GET", "/api/assets/" + sha, token=bob)[0], 404)
        self.assertEqual(self.request("GET", "/api/assets/" + sha, token=alice)[0], 200)
        self.request("POST", "/api/messages", {"schema": PROTOCOL, "text": "hello", "sha256": sha, "alt": "hello"}, alice)
        self.assertEqual(self.request("GET", "/api/assets/" + sha, token=bob)[0], 200)

    def test_history_gap_returns_cursor_and_recovers(self):
        # Emulate history retention with a bounded deque of three entries.
        from collections import deque
        state = DemoState(messages=deque(maxlen=3))
        new_server = create_server(0, state)
        thread = threading.Thread(target=new_server.serve_forever, daemon=True)
        thread.start()
        try:
            old_port = self.port
            self.port = new_server.server_port
            token = self.join("Reconnector")
            for n in range(4):
                status, _ = self.request("POST", "/api/messages", {"schema": PROTOCOL, "text": f"m{n}"}, token)
                self.assertEqual(status, 201)
            status, gap = self.request("GET", "/api/messages?since=0", token=token)
            self.assertEqual(status, 409)
            self.assertEqual(gap["earliest"], 2)
            status, body = self.request("GET", "/api/messages?since=1", token=token)
            self.assertEqual(status, 200)
            self.assertEqual([m["seq"] for m in body["messages"]], [2, 3, 4])
        finally:
            self.port = old_port
            new_server.shutdown()
            new_server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()

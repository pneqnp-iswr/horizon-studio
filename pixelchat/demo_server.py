"""Loopback-only PixelChat two-browser demo. NOT a Minecraft server plugin."""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
from threading import Lock
import time
from urllib.parse import parse_qs, urlsplit

from .media import Media, MediaError, inspect_media, MAX_BYTES
from .protocol import Message, ProtocolError, PROTOCOL, validate_message

HTML = Path(__file__).with_name("demo.html")
MAX_JSON_BYTES = 3_000
MAX_ASSETS = 16
MAX_SESSIONS = 32
MAX_MESSAGES = 200


@dataclass
class DemoState:
    """Transient demo state; an actual game must bind identity to game sessions."""
    lock: Lock = field(default_factory=Lock)
    sessions: dict[str, str] = field(default_factory=dict)
    assets: dict[str, tuple[Media, bytes]] = field(default_factory=dict)
    messages: deque[Message] = field(default_factory=lambda: deque(maxlen=MAX_MESSAGES))
    recent: dict[str, deque[float]] = field(default_factory=dict)
    seq: int = 0
    owners: dict[str, set[str]] = field(default_factory=dict)

    def join(self, name: str) -> str:
        if not isinstance(name, str) or not (1 <= len(name.strip()) <= 24):
            raise ProtocolError("Name must be 1–24 characters")
        if any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise ProtocolError("Invalid name")
        with self.lock:
            if len(self.sessions) >= MAX_SESSIONS:
                raise ProtocolError("Demo session limit reached")
            token = secrets.token_urlsafe(32)
            self.sessions[token] = name.strip()
            return token

    def name_for(self, token: str) -> str:
        with self.lock:
            name = self.sessions.get(token)
        if name is None:
            raise PermissionError("Join PixelChat before posting")
        return name

    def upload(self, token: str, data: bytes) -> Media:
        self.name_for(token)
        media = inspect_media(data)
        with self.lock:
            if media.digest not in self.assets:
                if len(self.assets) >= MAX_ASSETS or sum(m.size for m, _ in self.assets.values()) + media.size > 8 * 1024 * 1024:
                    raise MediaError("Demo asset quota exceeded")
                self.assets[media.digest] = media, data
            self.owners.setdefault(media.digest, set()).add(token)
        return media

    def send(self, token: str, payload: object) -> Message:
        self.name_for(token)
        with self.lock:
            text, sha, alt = validate_message(payload, set(self.assets))
            now = time.monotonic()
            recent = self.recent.setdefault(token, deque())
            while recent and now - recent[0] >= 10:
                recent.popleft()
            if len(recent) >= 8:
                raise ProtocolError("Rate limit: 8 messages per 10 seconds")
            recent.append(now)
            self.seq += 1
            msg = Message(self.seq, self.sessions[token], text, sha, alt)
            self.messages.append(msg)
            return msg

    def after(self, seq: int) -> list[dict]:
        with self.lock:
            earliest = self.messages[0].seq if self.messages else self.seq + 1
            if seq < earliest - 1 or seq > self.seq:
                raise ProtocolError(f"Cursor expired; retained messages start at {earliest}")
            return [m.public() for m in self.messages if m.seq > seq]

    def can_read_asset(self, token: str, sha: str) -> bool:
        self.name_for(token)
        with self.lock:
            return sha in self.assets and (
                token in self.owners.get(sha, ())
                or any(m.sha256 == sha for m in self.messages)
            )


def make_handler(state: DemoState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PixelChatDemo/1"

        def log_message(self, _format, *_args):
            pass  # Avoid logging session tokens or chat contents

        def respond(self, status: int, payload: dict):
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def valid_request(self) -> bool:
            host = self.headers.get("Host", "")
            # This demo intentionally never listens on a public interface.
            if host not in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}:
                self.respond(403, {"error": "Invalid local Host"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}:
                self.respond(403, {"error": "Cross-origin requests forbidden"})
                return False
            return True

        def token(self) -> str:
            return self.headers.get("X-PixelChat-Session", "")

        def do_GET(self):
            if not self.valid_request():
                return
            parsed = urlsplit(self.path)
            if parsed.path in ("/", "/demo.html"):
                data = HTML.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self'; object-src 'none'; base-uri 'none'")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if parsed.path == "/api/messages":
                try:
                    state.name_for(self.token())
                    value = parse_qs(parsed.query).get("since", ["0"])[0]
                    since = int(value)
                    if since < 0:
                        raise ValueError
                except (ValueError, PermissionError):
                    self.respond(400, {"error": "Invalid session or cursor"})
                    return
                try:
                    messages = state.after(since)
                except ProtocolError:
                    with state.lock:
                        earliest = state.messages[0].seq if state.messages else state.seq + 1
                    self.respond(409, {"error": "history_gap", "earliest": earliest})
                    return
                self.respond(200, {"schema": PROTOCOL, "messages": messages})
                return
            prefix = "/api/assets/"
            if parsed.path.startswith(prefix) and parsed.query == "":
                sha = parsed.path[len(prefix):]
                try:
                    allowed = state.can_read_asset(self.token(), sha)
                except PermissionError:
                    self.respond(401, {"error": "Join to load attachments"})
                    return
                if not allowed:
                    self.respond(404, {"error": "Attachment not found or not shared"})
                    return
                with state.lock:
                    stored = state.assets.get(sha)
                if stored is None:
                    self.respond(404, {"error": "Asset not found"})
                    return
                media, data = stored
                self.send_response(200)
                self.send_header("Content-Type", media.mime)
                self.send_header("Cache-Control", "private, no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.respond(404, {"error": "Unknown route"})

        def do_POST(self):
            if not self.valid_request():
                return
            path = urlsplit(self.path)
            if path.query or path.path not in ("/api/join", "/api/assets", "/api/messages"):
                self.respond(404, {"error": "Unknown route"})
                return
            raw_len = self.headers.get("Content-Length", "")
            try:
                length = int(raw_len)
            except ValueError:
                length = -1
            bound = MAX_BYTES if path.path == "/api/assets" else MAX_JSON_BYTES
            if length < 1 or length > bound or self.headers.get("Transfer-Encoding"):
                self.respond(413, {"error": "Invalid or oversized body"})
                self.close_connection = True
                return
            try:
                content_type = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if (path.path == "/api/assets" and content_type != "application/octet-stream") or (path.path != "/api/assets" and content_type != "application/json"):
                    self.respond(415, {"error": "Unsupported content type"})
                    return
                data = self.rfile.read(length)
                if path.path == "/api/assets":
                    media = state.upload(self.token(), data)
                    self.respond(201, {"asset": media.public()})
                    return
                payload = json.loads(data.decode("utf-8"))
                if path.path == "/api/join":
                    if not isinstance(payload, dict) or set(payload) != {"name"}:
                        raise ProtocolError("Join requires exactly name")
                    token = state.join(payload["name"])
                    self.respond(201, {"schema": PROTOCOL, "token": token,
                                       "capabilities": ["gif", "png", "pixel-emoji", "history-gap"],
                                       "limits": {"max_bytes": MAX_BYTES, "max_messages": MAX_MESSAGES}})
                else:
                    message = state.send(self.token(), payload)
                    self.respond(201, {"message": message.public()})
            except (MediaError, ProtocolError, ValueError, UnicodeError) as exc:
                self.respond(400, {"error": str(exc)})
            except PermissionError as exc:
                self.respond(401, {"error": str(exc)})

    return Handler


def create_server(port: int = 0, state: DemoState | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(state or DemoState()))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Local two-client GIF/pixel emoji prototype (not a Minecraft mod)")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    server = create_server(args.port)
    print(f"PixelChat local demo: http://127.0.0.1:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

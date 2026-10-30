"""Server-authoritative, strictly versioned PixelChat v1 message metadata."""
from __future__ import annotations

import re
from dataclasses import dataclass

PROTOCOL = "pixelchat/1"
MAX_TEXT = 512
MAX_ALT = 100
SHA256 = re.compile(r"^[a-f0-9]{64}$")


class ProtocolError(ValueError):
    pass


@dataclass
class Message:
    seq: int
    sender: str  # assigned by server authentication, never client payload
    text: str
    sha256: str | None = None
    alt: str = ""

    def public(self) -> dict:
        return {"schema": PROTOCOL, "seq": self.seq, "sender": self.sender,
                "text": self.text, "sha256": self.sha256, "alt": self.alt,
                "fallback": self.fallback()}

    def fallback(self) -> str:
        media_text = f"[GIF/image: {self.alt or 'attachment'}]" if self.sha256 else ""
        return (self.text + " " + media_text).strip() or "[empty message]"


def validate_message(payload: object, known_assets: set[str]) -> tuple[str, str | None, str]:
    if not isinstance(payload, dict) or set(payload) - {"schema", "text", "sha256", "alt"}:
        raise ProtocolError("Invalid message fields")
    if payload.get("schema") != PROTOCOL:
        raise ProtocolError("Unsupported PixelChat schema")
    text = payload.get("text", "")
    sha = payload.get("sha256")
    alt = payload.get("alt", "")
    if not isinstance(text, str) or len(text) > MAX_TEXT or any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise ProtocolError("Invalid message text")
    if not isinstance(alt, str) or len(alt) > MAX_ALT or any(ord(c) < 32 for c in alt):
        raise ProtocolError("Invalid alt text")
    if sha is not None and (not isinstance(sha, str) or not SHA256.fullmatch(sha) or sha not in known_assets):
        raise ProtocolError("Unknown or invalid media digest")
    if not text.strip() and sha is None:
        raise ProtocolError("Message must contain text or media")
    if sha is None and alt:
        raise ProtocolError("Alt text without media")
    return text, sha, alt

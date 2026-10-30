"""Security boundary for Horizon Studio's loopback-only HTTP API.

The token is a per-server CSRF/capability secret. It is not a remote
authentication system, and the server must remain bound to loopback.
"""
from __future__ import annotations

import hmac
import secrets
import threading

_token_init_lock = threading.Lock()
_LOCAL_NAMES = ("127.0.0.1", "localhost")


def session_token(server) -> str:
    """Create a cryptographically random token once per server instance."""
    with _token_init_lock:
        if not hasattr(server, "_studio_session_token"):
            server._studio_session_token = secrets.token_urlsafe(32)
        return server._studio_session_token


def trusted_request(headers, port: int) -> bool:
    """Reject DNS rebinding hosts and cross-origin browser requests.

    Only literal loopback Host headers for this bound port are valid.
    Origin may be absent for local non-browser clients with the token.
    """
    authority = headers.get("Host", "")
    allowed = {f"{name}:{port}" for name in _LOCAL_NAMES}
    if authority not in allowed:
        return False
    origin = headers.get("Origin")
    if origin is not None and origin != f"http://{authority}":
        return False
    fetch_site = headers.get("Sec-Fetch-Site")
    if fetch_site is not None and fetch_site not in ("same-origin", "none"):
        return False
    return True


def authorized_post(headers, server) -> bool:
    provided = headers.get("X-Studio-Token", "")
    return (isinstance(provided, str) and 1 <= len(provided) <= 128
            and hmac.compare_digest(provided, session_token(server)))


def content_type_allowed(headers, path: str) -> bool:
    content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    expected = "application/octet-stream" if path == "/api/resourcepack" else "application/json"
    return content_type == expected

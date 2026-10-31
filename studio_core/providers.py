"""HS-021: AI providers behind one interface, with consent, offline mode and minimal context.

A provider turns a request into typed operations (``studio_core.ai_tools`` contract). It never
edits a project: the core plans and validates its operations, and a person approves them
(``studio_core.transactions``). Rules every provider follows:

* **Offline mode** turns off every provider that would send data off the machine; Studio stays fully
  usable with the local fixture.
* **Consent.** Nothing is sent to a remote provider until the person has allowed that provider. The
  editor shows the exact payload first (``payload``), and the consent is stored with what it covers.
* **Minimal context.** A remote model receives:
  - the project's id, name and version, and the engine target;
  - the counts, and a list of blocks, items, recipes, structures and effects (kind, id, name and a
    few scalar properties).

  It never receives textures, source overrides, extensions, provenance, plugin objects, effect
  curves, file paths, or anything from outside the project.
* **No new powers.** The model is offered exactly the edit operations of the tool contract. It gets
  no shell, no file system, no network, no export and no build, and it can never approve native
  code. Its operations are untrusted input: the executor validates every one.
* **Credentials** come from the operating system's store (``studio_core.credentials``) and are only
  ever placed in the outgoing request.

Providers in this build:
* ``fixture``: deterministic, offline, labelled as simulated.
* ``claude``: Anthropic's Messages API through the official ``anthropic`` SDK. It is optional: if the
  package is not installed, the provider says so. **It has not been exercised against the live API
  in this repository's tests**, which use a stand-in client. Model, effort, timeout and retries are
  configurable; the request is streamed (cancellable between events); usage and an estimated cost
  are reported. It enables the API's server-side refusal fallback.
"""
from __future__ import annotations

import copy
import json
import threading
import time

from studio_core.ai_tools import EDITS, FixtureProvider, ToolError, VFX_FIELDS, VFX_PRESETS

CLAUDE_MODELS = {  # list prices in USD per million tokens (input, output), as published 2026-10-06
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-1": (10.0, 50.0),
}
DEFAULT_MODEL = "claude-opus-5-5"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
MAX_CONTEXT_ASSETS = 200
MAX_REQUEST_TEXT = 2000
MIN_INTERVAL = 2.0  # seconds between two requests to one remote provider
SCALAR_PROPS = ("name", "template", "rarity", "hardness", "light", "type", "count", "kind", "theme", "size")

SYSTEM_PROMPT = (
    "You edit one Horizon Studio mod project (Minecraft-style content for the Horizon engine) by calling the "
    "provided tools. Each tool call is one operation; together they form a proposal that a person reviews before "
    "anything changes. Use only the tools. Refer to existing assets by \"kind:id\" (for example \"item:ruby\"). "
    "In props, a reference to another asset is written {\"asset\": \"kind:id\"}. Ids use lowercase letters, digits "
    "and underscores and start with a letter. Effects are Studio-only previews and are never exported to the game. "
    "If the request cannot be expressed with these tools, call no tool and say why in one sentence."
)


class ProviderError(ToolError):
    """A refused or failed provider call (``code`` is stable)."""


def _object(properties: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": properties, "required": required}


TOOL_SCHEMAS = [
    {"name": "create_asset", "description": "Create a block, item, recipe or structure.",
     "input_schema": _object({"kind": {"type": "string", "enum": ["block", "item", "recipe", "structure"]},
                              "id": {"type": "string"}, "props": {"type": "object"}}, ["kind", "id", "props"])},
    {"name": "update_asset", "description": "Change properties of an existing asset, named \"kind:id\".",
     "input_schema": _object({"asset": {"type": "string"}, "set": {"type": "object"},
                              "unset": {"type": "array", "items": {"type": "string"}}}, ["asset"])},
    {"name": "delete_asset", "description": "Delete an asset nothing else uses, named \"kind:id\".",
     "input_schema": _object({"asset": {"type": "string"}}, ["asset"])},
    {"name": "create_vfx_asset", "description": "Create a Studio-only particle effect from a preset.",
     "input_schema": _object({"id": {"type": "string"}, "preset": {"type": "string", "enum": list(VFX_PRESETS)},
                              "set": {"type": "object", "properties": {k: {} for k in VFX_FIELDS}}}, ["id"])},
]
assert [t["name"] for t in TOOL_SCHEMAS] == list(EDITS)


def minimal_context(doc: dict) -> dict:
    """What a remote provider may see of a project (see the module docstring)."""
    counts: dict[str, int] = {}
    assets = []
    for obj in doc["objects"]:
        kind = obj["kind"] if obj["kind"] in ("block", "item", "recipe", "structure", "vfx") else "other"
        counts[kind] = counts.get(kind, 0) + 1  # plugin kinds are not named
        if obj["kind"] not in ("block", "item", "recipe", "structure", "vfx") or len(assets) >= MAX_CONTEXT_ASSETS:
            continue
        props = {k: v for k, v in obj["props"].items()
                 if k in SCALAR_PROPS and isinstance(v, (str, int, float, bool)) and not (isinstance(v, str) and len(v) > 120)}
        assets.append({"asset": f"{obj['kind']}:{obj['id']}", **props})
    project = {k: doc["project"].get(k) for k in ("id", "name", "version") if isinstance(doc["project"].get(k), str)}
    return {"project": project, "target": (doc.get("target") or {}).get("revision"), "counts": counts, "assets": assets}


def request_text(request: dict) -> str:
    text = request.get("text") if isinstance(request, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise ProviderError("BAD_REQUEST", "Describe the change in a sentence or two")
    if len(text) > MAX_REQUEST_TEXT:
        raise ProviderError("BAD_REQUEST", f"Keep the request under {MAX_REQUEST_TEXT} characters")
    return text.strip()


def payload(request: dict, context: dict, model: str) -> dict:
    """The exact message a remote provider would receive (shown to the person before consent)."""
    return {"model": model, "system": SYSTEM_PROMPT, "tools": [t["name"] for t in TOOL_SCHEMAS],
            "messages": [{"role": "user", "content": "Project:\n" + json.dumps(context, ensure_ascii=False, indent=1)
                          + "\n\nRequest: " + request_text(request)}]}


def operations_from(content) -> list[dict]:
    """Tool calls in a Messages API response, as executor operations (untrusted: validated later)."""
    operations = []
    for block in content:
        if getattr(block, "type", None) != "tool_use":
            continue
        if block.name not in EDITS or not isinstance(block.input, dict):
            raise ProviderError("BAD_TOOL_CALL", f"The model called an unknown tool {block.name!r}")
        operations.append({"tool": block.name, **copy.deepcopy(block.input)})
    return operations


class ClaudeProvider:
    """Anthropic Messages API with tool use, streamed. ``client`` is injectable (tests)."""

    name = "claude"
    remote = True

    def __init__(self, api_key: str, *, model: str = DEFAULT_MODEL, effort: str = "medium", timeout: float = 120.0,
                 max_retries: int = 2, client=None, cancel: threading.Event | None = None):
        if model not in CLAUDE_MODELS:
            raise ProviderError("BAD_MODEL", f"Unknown model {model!r}")
        if effort not in EFFORTS:
            raise ProviderError("BAD_REQUEST", f"Unknown effort {effort!r}")
        self.model, self.effort, self.cancel = model, effort, cancel or threading.Event()
        if client is None:
            try:
                import anthropic  # noqa: PLC0415 - optional dependency
            except ImportError:
                raise ProviderError("PROVIDER_UNAVAILABLE", "The Claude provider needs the 'anthropic' package "
                                                            "(pip install anthropic)") from None
            client = anthropic.Anthropic(api_key=api_key)
        self.client = client.with_options(timeout=timeout, max_retries=max_retries)
        self.usage: dict | None = None
        self.note: str | None = None

    def context(self, session) -> dict:
        return minimal_context(session.doc)

    def propose(self, request: dict, context: dict) -> list[dict]:
        sent = payload(request, context, self.model)
        tools = [{**t, "eager_input_streaming": True} for t in TOOL_SCHEMAS]
        try:
            with self.client.beta.messages.stream(
                model=self.model, max_tokens=16000, system=sent["system"], messages=sent["messages"], tools=tools,
                output_config={"effort": self.effort},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            ) as stream:
                for _event in stream:
                    if self.cancel.is_set():
                        raise ProviderError("CANCELLED", "Cancelled; nothing was proposed")
                response = stream.get_final_message()
        except ProviderError:
            raise
        except ValueError as exc:  # tool input JSON the SDK could not parse at all
            raise ProviderError("BAD_TOOL_CALL", f"The model's tool call could not be read: {exc}") from None
        except Exception as exc:  # noqa: BLE001 - SDK errors are reported, never crash the core
            raise ProviderError("PROVIDER_ERROR", f"{type(exc).__name__}: {str(exc)[:300]}") from None
        usage = getattr(response, "usage", None)
        tokens_in, tokens_out = getattr(usage, "input_tokens", 0) or 0, getattr(usage, "output_tokens", 0) or 0
        served = getattr(response, "model", None) or self.model  # a refusal fallback may have answered
        price_in, price_out = CLAUDE_MODELS.get(served, CLAUDE_MODELS[self.model])
        self.usage = {"model": served, "input_tokens": tokens_in,
                      "output_tokens": tokens_out,
                      "estimated_cost_usd": round(tokens_in / 1e6 * price_in + tokens_out / 1e6 * price_out, 6)}
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            raise ProviderError("REFUSED", f"The model declined ({getattr(details, 'category', None) or 'no category'})")
        if response.stop_reason == "max_tokens":
            raise ProviderError("TRUNCATED", "The answer was cut off; nothing was proposed")
        operations = operations_from(response.content)
        if not operations:
            text = " ".join(getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text")
            raise ProviderError("NO_OPERATIONS", text.strip()[:300] or "The model proposed no change")
        return operations


class Providers:
    """Which providers exist, whether each may be used now, and the person's settings."""

    def __init__(self, settings, credentials, *, clock=time.monotonic, claude_client=None):
        self.settings, self.credentials, self.clock = settings, credentials, clock
        self.claude_client = claude_client  # tests inject a stand-in for the SDK client
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def status(self) -> dict:
        current = self.settings.load()
        claude = current["providers"].get("claude", {})
        stored = bool(self.credentials and self.credentials.get("anthropic"))
        try:
            import anthropic  # noqa: F401, PLC0415
            sdk = True
        except ImportError:
            sdk = self.claude_client is not None
        return {"offline": current["offline"], "store": getattr(self.credentials, "kind", None), "providers": [
            {"id": "fixture", "remote": False, "simulated": True, "ready": True},
            {"id": "claude", "remote": True, "simulated": False, "sdk": sdk, "key_stored": stored,
             "consent": claude.get("consent"), "model": claude.get("model", DEFAULT_MODEL),
             "effort": claude.get("effort", "medium"), "models": list(CLAUDE_MODELS),
             "ready": sdk and stored and bool(claude.get("consent")) and not current["offline"],
             "exercised_live": False}]}

    def create(self, name: str, cancel: threading.Event | None = None):
        if name == "fixture":
            return FixtureProvider()
        if name != "claude":
            raise ProviderError("UNKNOWN_PROVIDER", f"No provider {name!r} is configured")
        current = self.settings.load()
        if current["offline"]:
            raise ProviderError("OFFLINE", "Offline mode is on: no data leaves this computer")
        claude = current["providers"].get("claude", {})
        if not claude.get("consent"):
            raise ProviderError("CONSENT_REQUIRED", "Allow Claude to receive this project's summary first")
        key = self.credentials.get("anthropic") if self.credentials else None
        if not key:
            raise ProviderError("CREDENTIAL_MISSING", "No Anthropic API key is stored in this computer's credential store")
        with self._lock:
            now = self.clock()
            if now - self._last.get(name, -MIN_INTERVAL) < MIN_INTERVAL:
                raise ProviderError("RATE_LIMITED", "One request at a time; try again in a moment")
            self._last[name] = now
        return ClaudeProvider(key, model=claude.get("model", DEFAULT_MODEL), effort=claude.get("effort", "medium"),
                              client=self.claude_client, cancel=cancel)


class Settings:
    """The person's AI settings (no secrets): offline mode and, per provider, consent and model."""

    def __init__(self, path):
        from pathlib import Path
        self.path = Path(path)

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        providers = data.get("providers") if isinstance(data.get("providers"), dict) else {}
        return {"offline": data.get("offline") is True, "providers": providers}

    def save(self, data: dict) -> None:
        from studio_core.storage import atomic_write_bytes
        atomic_write_bytes(self.path, (json.dumps(data, indent=1) + "\n").encode("utf-8"))

    def update(self, *, offline=None, provider=None, consent=None, model=None, effort=None, clock=time.time) -> dict:
        data = self.load()
        if offline is not None:
            data["offline"] = bool(offline)
        if provider is not None:
            if provider != "claude":
                raise ProviderError("UNKNOWN_PROVIDER", f"No provider {provider!r} is configured")
            entry = dict(data["providers"].get(provider, {}))
            if consent is True:
                entry["consent"] = {"granted_at": clock(), "covers": "project id, name, version, engine target, counts "
                                    "and a list of assets with names and a few scalar properties; the request text"}
            elif consent is False:
                entry.pop("consent", None)
            if model is not None:
                if model not in CLAUDE_MODELS:
                    raise ProviderError("BAD_MODEL", f"Unknown model {model!r}")
                entry["model"] = model
            if effort is not None:
                if effort not in EFFORTS:
                    raise ProviderError("BAD_REQUEST", f"Unknown effort {effort!r}")
                entry["effort"] = effort
            data["providers"][provider] = entry
        self.save(data)
        return data

"""HS-021: providers, consent, offline mode, minimal context and credentials.

The Claude provider is exercised against a stand-in for the official SDK client that records what it
is asked and answers like the Messages API (tool_use blocks, usage, stop reasons). **No live API
call is made here**, so nothing in these tests shows that Claude itself works with Studio."""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio_core.credentials import CredentialError, MemoryStore, SecretToolStore, default_store
from studio_core.migrate import from_editor_state, to_editor_state, upgrade
from studio_core.providers import (CLAUDE_MODELS, SYSTEM_PROMPT, ClaudeProvider, ProviderError, Providers, Settings,
                                   minimal_context, payload)
from studio_core.transactions import ProjectService, TransactionError
from studio_core.workspace import WorkspaceStore

KEY = "sk-ant-test-0123456789abcdefSECRET"
PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAGUlEQVR4nGP4z8DwnxLMMGrAqAGjBgwXAwAwxP4QHCfkAAAAAABJRU5ErkJggg=="  # a real 16x16 texture


def project():
    state = to_editor_state(upgrade(json.loads((ROOT / "examples" / "ruby_demo.hstudio.json").read_text(encoding="utf-8"))))
    state["items"][0]["texture"] = PNG
    state["source_overrides"] = {"assets/ruby_demo/models/item/ruby.json": '{"secret": "override"}'}
    state["carry"]["extensions"] = {"acme.plugin": {"token": "plugin-private"}}
    state["carry"]["preserved_objects"] = [{"uid": "33333333-3333-4333-8333-333333333333", "kind": "acme.widget",
                                            "id": "w1", "props": {"private": "plugin-data"}}]
    return from_editor_state(state)


def tool_use(name, data):
    return NS(type="tool_use", id="toolu_1", name=name, input=data)


class FakeStream:
    def __init__(self, owner, message, events, fail):
        self.owner, self.message, self.events, self.fail = owner, message, events, fail

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.owner.closed += 1
        return False

    def __iter__(self):
        for event in range(self.events):
            self.owner.yielded += 1
            if self.owner.on_event:
                self.owner.on_event(event)
            yield NS(type="text", text="…")
        if self.fail:
            raise self.fail

    def get_final_message(self):
        return self.message


class FakeClient:
    """Stands in for anthropic.Anthropic(): with_options(...).beta.messages.stream(**kwargs)."""

    def __init__(self, message=None, *, events=3, fail=None, on_event=None):
        self.message = message or NS(content=[tool_use("update_asset", {"asset": "item:ruby", "set": {"rarity": "epic"}})],
                                     stop_reason="tool_use", stop_details=None, model="claude-opus-5-5",
                                     usage=NS(input_tokens=1200, output_tokens=300))
        self.events, self.fail, self.on_event = events, fail, on_event
        self.calls, self.options, self.closed, self.yielded = [], [], 0, 0
        self.beta = NS(messages=NS(stream=self._stream))

    def with_options(self, **options):
        self.options.append(options)
        return self

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self, self.message, self.events, self.fail)


class ContextAndPayloadTests(unittest.TestCase):
    def test_a_remote_model_sees_only_a_minimal_summary(self):
        context = minimal_context(project())
        text = json.dumps(context)
        self.assertEqual(context["project"]["id"], "ruby_demo")
        self.assertIn({"asset": "item:ruby", "name": "Ruby", "template": "minecraft:diamond", "rarity": "rare"},
                      context["assets"])
        for private in ("data:image/png", "override", "plugin-private", "plugin-data", "acme", "uid", "provenance"):
            self.assertNotIn(private, text, private)

    def test_the_payload_is_exactly_what_would_be_sent(self):
        sent = payload({"text": "Add a sapphire set"}, minimal_context(project()), "claude-opus-5-5")
        self.assertEqual(sent["system"], SYSTEM_PROMPT)
        self.assertEqual(sent["tools"], ["create_asset", "update_asset", "delete_asset", "create_vfx_asset"])
        self.assertTrue(sent["messages"][0]["content"].endswith("Request: Add a sapphire set"))
        for bad in ({}, {"text": "   "}, {"text": "x" * 3000}):
            with self.subTest(bad=bad), self.assertRaises(ProviderError):
                payload(bad, {}, "claude-opus-5-5")


class ClaudeProviderTests(unittest.TestCase):
    def propose(self, client, **kwargs):
        provider = ClaudeProvider(KEY, client=client, **kwargs)
        return provider, provider.propose({"text": "Make the ruby epic"}, minimal_context(project()))

    def test_tool_calls_become_operations_and_the_request_is_well_formed(self):
        client = FakeClient()
        provider, operations = self.propose(client, model="claude-sonnet-5-5", effort="low")
        self.assertEqual(operations, [{"tool": "update_asset", "asset": "item:ruby", "set": {"rarity": "epic"}}])
        [call] = client.calls
        self.assertEqual(call["model"], "claude-sonnet-5-5")
        self.assertEqual(call["output_config"], {"effort": "low"})
        self.assertEqual([t["name"] for t in call["tools"]], ["create_asset", "update_asset", "delete_asset", "create_vfx_asset"])
        self.assertTrue(all(t["eager_input_streaming"] for t in call["tools"]))
        self.assertNotIn("tool_choice", call, "forced tool use is refused by current models")
        self.assertEqual((call["fallbacks"], call["betas"]), ("default", ["server-side-fallback-2026-07-01"]))
        self.assertNotIn(KEY, json.dumps(call, default=str), "the key is a client credential, never message content")
        self.assertEqual(client.options, [{"timeout": 120.0, "max_retries": 2}])
        self.assertEqual(provider.usage, {"model": "claude-opus-5-5", "input_tokens": 1200, "output_tokens": 300,
                                          "estimated_cost_usd": round(1200 / 1e6 * 4 + 300 / 1e6 * 20, 6)})

    def test_refusals_truncation_empty_answers_and_unknown_tools_are_reported(self):
        cases = {
            "REFUSED": NS(content=[], stop_reason="refusal", stop_details=NS(category="cyber"), model="m",
                          usage=NS(input_tokens=1, output_tokens=1)),
            "TRUNCATED": NS(content=[tool_use("create_asset", {"kind": "item"})], stop_reason="max_tokens",
                            stop_details=None, model="m", usage=NS(input_tokens=1, output_tokens=1)),
            "NO_OPERATIONS": NS(content=[NS(type="text", text="I cannot do that with these tools.")],
                                stop_reason="end_turn", stop_details=None, model="m", usage=NS(input_tokens=1, output_tokens=1)),
            "BAD_TOOL_CALL": NS(content=[tool_use("run_shell", {"cmd": "rm -rf /"})], stop_reason="tool_use",
                                stop_details=None, model="m", usage=NS(input_tokens=1, output_tokens=1)),
        }
        for code, message in cases.items():
            with self.subTest(code), self.assertRaises(ProviderError) as refused:
                self.propose(FakeClient(message))
            self.assertEqual(refused.exception.code, code)

    def test_sdk_errors_unparseable_tool_json_and_cancellation_end_cleanly(self):
        for fail, code in ((RuntimeError("529 overloaded"), "PROVIDER_ERROR"), (ValueError("bad json"), "BAD_TOOL_CALL")):
            with self.subTest(code), self.assertRaises(ProviderError) as failed:
                self.propose(FakeClient(fail=fail))
            self.assertEqual(failed.exception.code, code)
        cancel = threading.Event()
        client = FakeClient(events=50, on_event=lambda n: n == 2 and cancel.set())
        with self.assertRaises(ProviderError) as stopped:
            self.propose(client, cancel=cancel)
        self.assertEqual(stopped.exception.code, "CANCELLED")
        self.assertLess(client.yielded, 50, "the stream stopped at the next event")
        self.assertEqual(client.closed, 1, "and the connection was closed")

    def test_unknown_models_and_a_missing_sdk_are_refused(self):
        with self.assertRaises(ProviderError):
            ClaudeProvider(KEY, model="gpt-4", client=FakeClient())
        with mock.patch.dict(sys.modules, {"anthropic": None}), self.assertRaises(ProviderError) as missing:
            ClaudeProvider(KEY)
        self.assertEqual(missing.exception.code, "PROVIDER_UNAVAILABLE")
        self.assertIn("claude-opus-5-5", CLAUDE_MODELS)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = [100.0]
        self.client = FakeClient()
        self.providers = Providers(Settings(self.root / "ai.json"), MemoryStore(), clock=lambda: self.now[0],
                                   claude_client=self.client)
        self.service = ProjectService(WorkspaceStore(self.root / "ws"), registry=self.providers)
        self.r0 = self.service.commit(project(), base_revision=None)["revision"]

    def tearDown(self):
        self.tmp.cleanup()

    def ask(self):
        return self.service.propose("ruby_demo", {"text": "Make the ruby epic"}, provider="claude", base_revision=self.r0)

    def test_nothing_is_sent_offline_without_consent_or_without_a_key(self):
        settings = self.providers.settings
        for step, code in ((lambda: None, "CONSENT_REQUIRED"),
                           (lambda: settings.update(provider="claude", consent=True), "CREDENTIAL_MISSING"),
                           (lambda: self.providers.credentials.set("anthropic", KEY), None)):
            step()
            if code:
                with self.subTest(code), self.assertRaises(TransactionError) as refused:
                    self.ask()
                self.assertEqual(refused.exception.code, code)
        self.assertEqual(self.client.calls, [], "no request left the computer before all three")
        settings.update(offline=True)
        with self.assertRaises(TransactionError) as offline:
            self.ask()
        self.assertEqual(offline.exception.code, "OFFLINE")
        self.assertFalse(self.providers.status()["providers"][1]["ready"])
        settings.update(offline=False)
        proposal = self.ask()
        self.assertEqual((proposal["provider"], proposal["remote"], proposal["simulated"]), ("claude", True, False))
        self.assertEqual(proposal["usage"]["input_tokens"], 1200)
        self.assertEqual(proposal["diff"]["assets"][0]["fields"], [{"path": "rarity", "before": "rare", "after": "epic"}])
        with self.assertRaises(TransactionError) as busy:  # one request at a time per remote provider
            self.ask()
        self.assertEqual(busy.exception.code, "RATE_LIMITED")
        settings.update(provider="claude", consent=False)
        self.now[0] += 10
        with self.assertRaises(TransactionError):
            self.ask()

    def test_model_output_is_untrusted_and_goes_through_the_same_strict_executor(self):
        self.providers.settings.update(provider="claude", consent=True)
        self.providers.credentials.set("anthropic", KEY)
        self.client.message = NS(content=[tool_use("delete_asset", {"asset": "item:ruby"})], stop_reason="tool_use",
                                 stop_details=None, model="claude-opus-5-5", usage=NS(input_tokens=1, output_tokens=1))
        with self.assertRaises(TransactionError) as in_use:
            self.ask()
        self.assertEqual(in_use.exception.code, "IN_USE", "recipes still use the ruby")
        self.assertIn("proposal_refused", [a["action"] for a in self.service.audit("ruby_demo")])

    def test_the_key_is_never_written_anywhere_studio_writes(self):
        self.providers.settings.update(provider="claude", consent=True, model="claude-haiku-5-5")
        self.providers.credentials.set("anthropic", KEY)
        proposal = self.ask()
        self.service.commit_proposal("ruby_demo", proposal["id"], expected_revision=self.r0)
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(KEY.encode(), path.read_bytes(), path)
        self.assertNotIn(KEY, json.dumps(self.providers.status()))
        self.assertEqual(self.client.calls[0]["model"], "claude-haiku-5-5")


class CredentialStoreTests(unittest.TestCase):
    def test_the_memory_store_and_its_limits(self):
        store = MemoryStore()
        store.set("anthropic", f"  {KEY}  ")
        self.assertEqual(store.get("anthropic"), KEY)
        for bad in ("", "two\nlines", "x" * 600):
            with self.subTest(bad=bad[:10]), self.assertRaises(CredentialError):
                store.set("anthropic", bad)
        with self.assertRaises(CredentialError):
            store.set("github", KEY)
        store.delete("anthropic")
        self.assertIsNone(store.get("anthropic"))
        self.assertEqual(default_store({"HORIZON_STUDIO_CREDENTIALS": "memory"}).kind, "memory")

    @unittest.skipIf(sys.platform == "win32", "a POSIX shell script stands in for secret-tool")
    def test_secret_tool_gets_the_key_on_stdin_never_on_a_command_line(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            log, vault = folder / "argv.log", folder / "vault"
            tool = folder / "secret-tool"
            tool.write_text(f"#!/bin/sh\necho \"$@\" >> {log}\ncase \"$1\" in\n  store) cat > {vault};;\n"
                            f"  lookup) [ -f {vault} ] && cat {vault} || exit 1;;\n  clear) rm -f {vault};;\nesac\n")
            tool.chmod(0o755)
            store = SecretToolStore(str(tool))
            self.assertIsNone(store.get("anthropic"))
            store.set("anthropic", KEY)
            self.assertEqual(store.get("anthropic"), KEY)
            self.assertNotIn(KEY, log.read_text(), "the key never appears in a process's arguments")
            store.delete("anthropic")
            self.assertIsNone(store.get("anthropic"))

    @unittest.skipUnless(sys.platform == "win32", "Windows Credential Manager")
    def test_windows_credential_manager_round_trip(self):
        from studio_core.credentials import WindowsStore
        store = WindowsStore()
        try:
            store.set("anthropic", KEY)
            self.assertEqual(store.get("anthropic"), KEY)
        finally:
            store.delete("anthropic")
        self.assertIsNone(store.get("anthropic"))


class HttpTests(unittest.TestCase):
    def test_keys_go_in_and_never_come_out(self):
        import http.client
        from security.request_policy import session_token
        from studio import Handler, ThreadingHTTPServer
        with tempfile.TemporaryDirectory() as folder:
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            server.studio_workspaces = WorkspaceStore(Path(folder) / "ws")
            server.studio_providers = Providers(Settings(Path(folder) / "ai.json"), MemoryStore())
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                def post(path, body):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
                    connection.request("POST", path, json.dumps(body), {"Content-Type": "application/json",
                                                                         "X-Studio-Token": session_token(server)})
                    response = connection.getresponse()
                    raw = response.read()
                    connection.close()
                    return response.status, raw
                status, raw = post("/api/ai/credentials", {"name": "anthropic", "key": KEY})
                self.assertEqual((status, json.loads(raw)), (200, {"name": "anthropic", "key_stored": True}))
                for path, body in (("/api/ai/providers", {}), ("/api/ai/settings", {"provider": "claude", "consent": True})):
                    status, raw = post(path, body)
                    self.assertEqual(status, 200)
                    self.assertNotIn(KEY.encode(), raw)
                self.assertTrue(json.loads(raw)["providers"][1]["key_stored"])
                self.assertFalse(json.loads(raw)["providers"][1]["exercised_live"])
                status, raw = post("/api/ai/credentials", {"name": "anthropic", "key": None})
                self.assertEqual(json.loads(raw)["key_stored"], False)
                self.assertNotIn(KEY.encode(), (Path(folder) / "ai.json").read_bytes())
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()

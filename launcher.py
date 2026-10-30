"""Desktop entry point for the bundled Windows Horizon Studio executable.

The UI is served exclusively on loopback. The small native window controls the
lifetime of the local server, so the frozen app does not need a console window.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from studio import HOST, PORT, Handler


def app_version() -> str:
    try:
        return (Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "development"


def start_server(*, smoke_test: bool = False) -> ThreadingHTTPServer:
    """Prefer a stable origin for browser localStorage across regular launches."""
    port = 0 if smoke_test else PORT
    try:
        server = ThreadingHTTPServer((HOST, port), Handler)
    except OSError as exc:
        raise RuntimeError(
            f"Unable to start Horizon Studio on http://{HOST}:{PORT}. "
            "Close the process using this port, then launch the app again."
        ) from exc
    server.daemon_threads = True
    return server


# The ruby demo request; the official cargo-horizon-mod accepted exactly these package bytes
# (docs/COMPATIBILITY_EVIDENCE.md), so a frozen build must reproduce them.
SMOKE_PACKAGE = {
    "id": "ruby_demo", "name": "Ruby Demo", "version": "0.1.0", "author": "Creator",
    "description": "Example with two recipes, a block and a gem",
    "blocks": [{"id": "ruby_block", "name": "Block of Ruby", "template": "minecraft:iron_block", "hardness": 4, "light": 3}],
    "items": [{"id": "ruby", "name": "Ruby", "template": "minecraft:diamond", "rarity": "rare", "max_stack_size": 64}],
    "recipes": [
        {"id": "ruby_block", "type": "shaped", "result": "ruby_demo:ruby_block", "count": 1, "grid": ["ruby_demo:ruby"] * 9},
        {"id": "ruby_from_block", "type": "shapeless", "result": "ruby_demo:ruby", "count": 9,
         "grid": ["ruby_demo:ruby_block"] + [""] * 8},
    ],
    "structures": [],
}
SMOKE_PACKAGE_SHA256 = "ee3e1c878ea41fbf710f749896bfdb92b23b18e21e67b016b57b95b96a8797e2"
SMOKE_LEGACY_PROJECT = {
    "format": "horizon-studio", "schema": 2,
    "metadata": {"id": "smoke_project", "name": "Smoke", "version": "0.1.0", "author": "Horizon Studio"},
    "blocks": [], "items": [{"id": "probe", "name": "Probe", "template": "minecraft:diamond"}],
    "recipes": [{"id": "probe_recipe", "type": "shapeless", "result": "@probe", "count": 1,
                 "grid": ["minecraft:diamond"] + [""] * 8}],
}


def smoke_test(report_path: Path | None = None, workspace_dir: Path | None = None) -> int:
    """Self-test of the bundled application without a GUI.

    Checks every bundled script and asset, both languages, the session API, project
    open/save, disk workspaces (also across a server restart and, with a persistent
    ``workspace_dir``, across process launches), the exported package bytes and shutdown.
    """
    import hashlib
    import tempfile
    from studio import WEB_SCRIPTS
    from studio_core.workspace import WorkspaceStore

    checks: dict[str, object] = {}
    error = None
    temporary = None
    if workspace_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="horizon-studio-smoke-")
        workspace_dir = Path(temporary.name)
    servers = []

    def launch():
        server = start_server(smoke_test=True)
        server.studio_workspaces = WorkspaceStore(Path(workspace_dir))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        servers.append((server, worker))
        return f"http://{HOST}:{server.server_port}"

    def get(base, path):
        with urllib.request.urlopen(base + path, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError(f"GET {path} returned {response.status}")
            return response.read()

    def post(base, token, path, payload):
        request = urllib.request.Request(base + path, json.dumps(payload).encode("utf-8"), method="POST",
                                         headers={"Content-Type": "application/json", "X-Studio-Token": token})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def stop(server, worker):
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        return not worker.is_alive()

    try:
        base = launch()
        html = get(base, "/")
        missing = [name for name in WEB_SCRIPTS if f'src="/{name}"'.encode() not in html]
        if b"Horizon Studio" not in html or missing:
            raise RuntimeError(f"index.html does not load {missing}")
        for name, marker in WEB_SCRIPTS.items():
            if marker not in get(base, "/" + name):
                raise RuntimeError(f"Bundled script {name} is wrong or missing")
        checks["scripts"] = sorted(WEB_SCRIPTS)
        if not get(base, "/assets/branding/horizon-studio-mark.png").startswith(b"\x89PNG"):
            raise RuntimeError("Bundled favicon is missing")
        i18n = get(base, "/i18n.js")
        if b'"en": {' not in i18n or b'"ru": {' not in i18n:
            raise RuntimeError("Both EN and RU catalogs must be bundled")
        checks["i18n"] = ["en", "ru"]
        token = json.loads(get(base, "/api/session"))["token"]

        status, raw = post(base, token, "/api/project/open", SMOKE_LEGACY_PROJECT)
        opened = json.loads(raw)
        if status != 200 or opened.get("migrated_from") != 2:
            raise RuntimeError(f"Project open failed: {status} {raw[:200]!r}")
        status, raw = post(base, token, "/api/project/save", opened["state"])
        if status != 200 or json.loads(raw).get("schema") != "studio.project/1":
            raise RuntimeError(f"Project save failed: {status}")
        checks["project_open_save"] = "schema 2 -> studio.project/1"

        state = opened["state"]
        status, raw = post(base, token, "/api/workspace/recover", {"project_id": "smoke_project"})
        previous = json.loads(raw).get("revision") if status == 200 else None
        if status not in (200, 404):
            raise RuntimeError(f"Workspace recover failed: {status}")
        checks["workspace_before_launch"] = "recovered" if previous else "empty"
        status, raw = post(base, token, "/api/workspace/write", {"state": state, "expected_revision": previous})
        if status != 200:
            raise RuntimeError(f"Workspace write failed: {status} {raw[:200]!r}")
        revision = json.loads(raw)["revision"]

        status, raw = post(base, token, "/api/hmod", SMOKE_PACKAGE)
        digest = hashlib.sha256(raw).hexdigest()
        if status != 200 or digest != SMOKE_PACKAGE_SHA256:
            raise RuntimeError(f"Exported package {digest} differs from the officially checked bytes")
        checks["hmod_sha256"] = digest

        if not stop(*servers[0]):
            raise RuntimeError("Server thread did not stop")
        base = launch()  # a fresh server must see the saved workspace
        token = json.loads(get(base, "/api/session"))["token"]
        status, raw = post(base, token, "/api/workspace/recover", {"project_id": "smoke_project"})
        if status != 200 or json.loads(raw)["revision"] != revision:
            raise RuntimeError("Workspace did not survive a server restart")
        checks["workspace_after_restart"] = revision
        if not stop(*servers[1]):
            raise RuntimeError("Server thread did not stop")
        checks["shutdown"] = "clean"
    except Exception as exc:  # reported, never hidden
        error = f"{type(exc).__name__}: {exc}"
    finally:
        for server, worker in servers:
            if worker.is_alive():
                stop(server, worker)
        if temporary is not None:
            temporary.cleanup()
    report = {"schema": "horizon-studio.smoke/1", "version": app_version(), "ok": error is None,
              "checks": checks, "error": error}
    if report_path is not None:
        Path(report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if sys.stdout is not None and error is None:
        print("Horizon Studio standalone smoke test passed", flush=True)
    if sys.stderr is not None and error is not None:
        print(f"Horizon Studio smoke test FAILED: {error}", file=sys.stderr, flush=True)
    return 0 if error is None else 1


CORE_PROTOCOL = "horizon-studio.core/1"


def serve_core(stdin=None, stdout=None) -> int:
    """Headless core for the desktop shell (``--serve``).

    Binds an ephemeral loopback port, announces itself with one JSON line on stdout and
    runs until stdin reaches end-of-file or receives ``shutdown``. The shell owns the
    other end of that pipe, so the core also stops when the shell exits or crashes.
    """
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    if stdin is None or stdout is None:
        return 2  # a windowed build has no pipes to talk to the shell
    server = start_server(smoke_test=True)
    server.studio_log = sys.stderr
    server.studio_desktop = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def announce(event: str, **fields) -> None:
        stdout.write(json.dumps({"protocol": CORE_PROTOCOL, "event": event, **fields}) + "\n")
        stdout.flush()

    announce("ready", url=f"http://{HOST}:{server.server_port}/", version=app_version(), pid=os.getpid())
    try:
        for line in stdin:
            if line.strip() == "shutdown":
                break
    except (OSError, ValueError):
        pass  # a broken pipe means the shell is gone
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    try:
        announce("stopped")
    except (OSError, ValueError):
        pass
    return 0


def launch_gui() -> None:
    import tkinter as tk
    from tkinter import messagebox

    try:
        server = start_server()
    except RuntimeError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Horizon Studio", str(exc))
        root.destroy()
        raise SystemExit(1) from exc

    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f"http://{HOST}:{server.server_port}/"

    root = tk.Tk()
    root.title(f"Horizon Studio {app_version()}")
    root.geometry("430x290")
    root.minsize(400, 260)
    root.configure(bg="#0b111a")
    root.resizable(True, False)
    try:
        icon = Path(__file__).resolve().parent / "assets" / "horizon-studio.ico"
        if icon.is_file():
            root.iconbitmap(str(icon))
    except tk.TclError:
        pass
    root._language = "en"
    heading = tk.Label(root, text="Horizon Studio", font=("Segoe UI", 23, "bold"),
                       fg="#edf5ff", bg="#0b111a")
    heading.pack(pady=(23, 7))
    sub = tk.Label(root, font=("Segoe UI", 10), fg="#a9c4d9", bg="#0b111a")
    sub.pack()
    url_label = tk.Label(root, text=url, font=("Consolas", 10), fg="#68d5ff", bg="#0b111a")
    url_label.pack(pady=(8, 12))
    actions = tk.Frame(root, bg="#0b111a")
    actions.pack()
    language_bar = tk.Frame(root, bg="#0b111a")
    language_bar.pack(pady=(14, 5))

    def shutdown() -> None:
        root.withdraw()
        server.shutdown()
        server.server_close()
        root.destroy()

    def open_browser() -> None:
        webbrowser.open(url, new=2)

    open_button = tk.Button(actions, command=open_browser, bg="#68d5ff", fg="#08111b",
                            relief="flat", font=("Segoe UI", 10, "bold"), padx=16, pady=9)
    open_button.pack(side="left", padx=6)
    exit_button = tk.Button(actions, command=shutdown, bg="#1c2a3a", fg="#eaf4ff",
                            relief="flat", font=("Segoe UI", 10, "bold"), padx=16, pady=9)
    exit_button.pack(side="left", padx=6)

    def set_language(language: str) -> None:
        root._language = language
        if language == "ru":
            sub.config(text="Локальный редактор модов · Сервер запущен")
            open_button.config(text="Открыть редактор")
            exit_button.config(text="Закрыть")
        else:
            sub.config(text="Offline mod editor · Local server running")
            open_button.config(text="Open Studio")
            exit_button.config(text="Stop & Exit")
        for code, button in language_buttons.items():
            button.config(bg="#68d5ff" if code == language else "#192434",
                          fg="#051521" if code == language else "#d2e5f6")

    language_buttons = {}
    for code, label in (("en", "🇬🇧 EN"), ("ru", "🇷🇺 RU")):
        button = tk.Button(language_bar, text=label, command=lambda c=code: set_language(c),
                           font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=5)
        button.pack(side="left", padx=4)
        language_buttons[code] = button
    set_language("en")
    root.protocol("WM_DELETE_WINDOW", shutdown)
    root.after(400, open_browser)
    try:
        root.mainloop()
    finally:
        if worker.is_alive():
            server.shutdown()
            server.server_close()


def main() -> int:
    if "--smoke-test" in sys.argv:
        def option(flag):
            return Path(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv[:-1] else None
        return smoke_test(option("--smoke-report"), option("--smoke-workspace"))
    if "--serve" in sys.argv:
        return serve_core()
    launch_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

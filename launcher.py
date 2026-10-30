"""Desktop entry point for the bundled Windows Horizon Studio executable.

The UI is served exclusively on loopback. The small native window controls the
lifetime of the local server, so the frozen app does not need a console window.
"""
from __future__ import annotations

import json
import sys
import threading
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


def smoke_test() -> int:
    """Exercise bundled web assets and a generated mod without displaying a GUI."""
    server = start_server(smoke_test=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://{HOST}:{server.server_port}"
    try:
        for path, expected in (("/", b"Horizon Studio"), ("/i18n.js", b"HorizonI18n"), ("/model_viewer.js", b"HorizonModelViewer"), ("/source_workbench_ui.js", b"source_overrides"), ("/editor_history.js", b"HorizonStudioHistory"), ("/editor_api.js", b"HorizonStudioApi"), ("/editor_workspace.js", b"createWorkspaceSync")):
            with urllib.request.urlopen(base + path, timeout=10) as response:
                data = response.read()
                if response.status != 200 or expected not in data:
                    raise RuntimeError(f"Unexpected response from {path}")
        sample = {
            "id": "smoke", "name": "Smoke Test", "version": "0.1.0",
            "author": "Horizon Studio", "description": "Bundled application smoke check",
            "blocks": [], "items": [{"id": "probe", "name": "Probe", "template": "minecraft:diamond"}], "recipes": [], "structures": []
        }
        with urllib.request.urlopen(base + "/api/session", timeout=10) as response:
            token = json.loads(response.read())["token"]
        body = json.dumps(sample).encode("utf-8")
        request = urllib.request.Request(
            base + "/api/preview", body,
            headers={"Content-Type": "application/json", "X-Studio-Token": token}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read())
            if response.status != 200 or "manifest" not in result:
                raise RuntimeError("Packager API verification failed")
        if sys.stdout is not None:
            print("Horizon Studio standalone smoke test passed", flush=True)
        return 0
    except Exception as exc:
        if sys.stderr is not None:
            print(f"Horizon Studio smoke test FAILED: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


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
        return smoke_test()
    launch_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

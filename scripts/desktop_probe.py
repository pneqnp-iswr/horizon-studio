"""Launch the desktop shell the way a user does and record evidence about that run.

The shell is started with ``--smoke-report``; once it writes ``<report>.ready`` (the editor
booted) the probe captures a real screenshot of the window and the memory of the whole
process tree (shell, project core and web view processes), then waits for the shell to
exit on its own. Output, per ``--label``: ``<label>.smoke.json`` (the shell's report),
``<label>.png`` and ``<label>.metrics.json``.

Requires psutil; screenshots use Pillow's ImageGrab on Windows and ImageMagick ``import``
on X11. Exit status is non-zero unless the shell reported ``ok`` and exited with 0.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def window_rect(title: str):
    """Screen rectangle of the shell window on Windows, or None."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return None
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def screen_size():
    if sys.platform == "win32":
        import ctypes
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    return None


def screenshot(path: Path, title: str) -> dict:
    if sys.platform == "win32":
        from PIL import ImageGrab
        image = ImageGrab.grab(all_screens=True)
        rect = window_rect(title)
        if rect:
            image = image.crop(rect)
        image.save(path)
        return {"path": path.name, "size": list(image.size), "cropped_to_window": bool(rect)}
    if shutil.which("import") and os.environ.get("DISPLAY"):
        subprocess.run(["import", "-window", "root", str(path)], check=True, timeout=30)
        return {"path": path.name, "cropped_to_window": False}
    return {"path": None, "reason": "no screenshot tool for this platform"}


def tree_memory(pid: int) -> dict:
    import psutil
    try:
        root = psutil.Process(pid)
        processes = [root, *root.children(recursive=True)]
    except psutil.Error as error:
        return {"error": str(error)}
    by_name: dict[str, dict] = {}
    total = 0
    for process in processes:
        try:
            rss = process.memory_info().rss
            name = process.name()
        except psutil.Error:
            continue
        total += rss
        entry = by_name.setdefault(name, {"processes": 0, "rss_mb": 0.0})
        entry["processes"] += 1
        entry["rss_mb"] = round(entry["rss_mb"] + rss / 2**20, 1)
    return {"total_rss_mb": round(total / 2**20, 1), "processes": len(processes), "by_name": by_name}


def probe(exe: Path, out: Path, label: str, window: str, hold: int, timeout: int, settle: float,
          allow_test_build: bool = False) -> int:
    out.mkdir(parents=True, exist_ok=True)
    report = out / f"{label}.smoke.json"
    ready = Path(str(report) + ".ready")
    for stale in (report, ready):
        stale.unlink(missing_ok=True)
    started = time.monotonic()
    shell = subprocess.Popen([str(exe), "--smoke-report", str(report), "--smoke-hold", str(hold),
                              "--window-size", window])
    metrics: dict = {"label": label, "executable": exe.name, "window": window, "screen": screen_size()}
    while not ready.exists() and shell.poll() is None and time.monotonic() - started < timeout:
        time.sleep(0.05)
    if ready.exists():
        metrics["ready_seen_after_ms"] = round((time.monotonic() - started) * 1000)
        time.sleep(settle)  # let the first frame settle before the screenshot
        metrics["memory"] = tree_memory(shell.pid)
        try:
            metrics["screenshot"] = screenshot(out / f"{label}.png", "Horizon Studio")
        except Exception as error:  # evidence is best effort; the smoke verdict is not
            metrics["screenshot"] = {"path": None, "error": str(error)}
    try:
        code = shell.wait(timeout=max(5, timeout - (time.monotonic() - started)) + hold + 15)
    except subprocess.TimeoutExpired:
        shell.kill()
        code = shell.wait()
    metrics["wall_ms"] = round((time.monotonic() - started) * 1000)
    metrics["exit_code"] = code
    metrics["report"] = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else None
    ok = code == 0 and bool(metrics["report"] and metrics["report"].get("ok"))
    if ok and (metrics["report"].get("shell") or {}).get("test_build") and not allow_test_build:
        # The cargo feature `e2e` answers the Save dialog from the environment: never ship it.
        metrics["error"] = "this is a test build (cargo feature e2e); packaged builds must not enable it"
        print(metrics["error"], file=sys.stderr)
        ok = False
    metrics["ok"] = ok
    (out / f"{label}.metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: metrics.get(k) for k in ("label", "ok", "exit_code", "wall_ms", "ready_seen_after_ms")}))
    if metrics["report"]:
        print(" timings_ms:", json.dumps(metrics["report"].get("timings_ms")))
    if "memory" in metrics:
        print(" memory:", json.dumps(metrics["memory"]))
    return 0 if ok else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--window-size", default="1280x800")
    parser.add_argument("--hold", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--settle", type=float, default=1.5)
    parser.add_argument("--allow-test-build", action="store_true", help="accept a build with the cargo feature e2e")
    args = parser.parse_args(argv)
    return probe(args.exe.resolve(), args.out, args.label, args.window_size, args.hold, args.timeout, args.settle,
                 args.allow_test_build)


if __name__ == "__main__":
    raise SystemExit(main())

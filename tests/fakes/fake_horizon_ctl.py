"""A stand-in for upstream's horizon-ctl (agent control) for Preview Bridge tests.

Speaks the same command line and JSON replies as horizon-ctl at Horizon 3c1d4b39 for the commands
Studio uses; keeps its "game" in a JSON file beside the socket. FAKE_CTL_MODE simulates failures.
"""
import json
import os
import sys
import zipfile
from pathlib import Path

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def reply(value, code=0):
    print(json.dumps(value))
    sys.exit(code)


def main(argv):
    socket = os.environ.get("HORIZON_CONTROL", "control.sock")
    if argv[:1] == ["--socket"]:
        socket, argv = argv[1], argv[2:]
    mode = os.environ.get("FAKE_CTL_MODE", "")
    state_file = Path(socket + ".state")
    command, args = argv[0], argv[1:]
    if command == "launch":
        if mode == "unreachable":
            reply({"error": "the game exited (exit status: 1) before opening the control socket", "kind": "launch"}, 3)
        if "--game-dir" not in args or "--home" not in args:
            reply({"error": "Studio must isolate the game folder"}, 2)
        game_dir = Path(args[args.index("--game-dir") + 1])
        world = args[args.index("--world") + 1]
        (game_dir / "saves" / world).mkdir(parents=True, exist_ok=True)
        (game_dir / "saves" / world / "level.dat").write_bytes(b"fake")
        mods = [args[i + 1] for i, a in enumerate(args) if a == "--dev-mod"]
        state_file.write_text(json.dumps({"running": True, "mods": mods, "inventory": [], "args": args}))
        reply({"pid": 999999, "socket": socket, "version": "v2026.10.31", "game": "horizon-client", "source": "beside"})
    if not state_file.is_file():
        reply({"error": f"no game is listening on {socket}", "kind": "connect"}, 3)
    state = json.loads(state_file.read_text())
    if command == "wait-for":
        reply({"loaded": True, "world": "StudioPreview"})
    if command == "state":
        reply({"screen": None, "dimension": "minecraft:overworld", "game_mode": "survival", "position": [0.5, 64, 0.5],
               "health": 20})
    if command == "screenshot":
        Path(args[0]).write_bytes(b"not a png" if mode == "no-png" else PNG)
        reply({"path": args[0]})
    if command == "give":
        item = args[0]
        namespace, _, name = item.partition(":")
        known = False
        for mod in state["mods"]:
            with zipfile.ZipFile(mod) as archive:
                known |= f"assets/{namespace}/models/item/{name}.json" in archive.namelist()
        if not known and namespace != "minecraft":
            reply({"error": f"unknown item {item}"}, 1)
        state["inventory"].append({"item": item, "count": int(args[1]) if len(args) > 1 else 1})
        state_file.write_text(json.dumps(state))
        reply({"given": item})
    if command == "inventory":
        reply({"hotbar": state["inventory"]})
    if command == "quit":
        if mode == "quit-hangs":
            reply({"error": "timed out waiting for the game", "kind": "timeout"}, 1)
        state_file.unlink()
        reply({"quit": True})
    reply({"error": f"unknown command {command}", "kind": "usage"}, 2)


if __name__ == "__main__":
    main(sys.argv[1:])

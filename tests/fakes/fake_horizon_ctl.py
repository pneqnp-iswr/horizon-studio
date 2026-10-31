"""A stand-in for upstream's horizon-ctl (agent control) for Preview Bridge tests.

Speaks the same command line and JSON replies as horizon-ctl at Horizon 3c1d4b39 for the commands
Studio uses (give: control.rs; inventory: agent.rs inventory_value, with hotbar 0-8, main 9-35,
armor 500-503, offhand 504, carried and counts); keeps its "game" in a JSON file beside the socket.

FAKE_CTL_MODE (comma-separated) simulates failures and lying or ambiguous games:
  unreachable, no-png, quit-hangs      the session's failure paths
  give-lies        give answers {"ok": true} and adds nothing
  accept-anything  give accepts ids no package defines
  substring        give adds a vanilla stack whose components mention the id
  prefix           give adds a different item whose id starts with the requested one
  two              give adds two
  late             the stack shows up only on the third inventory read after a give
  malformed        the hotbar has 8 slots
  duplicate-slot   two hotbar entries claim slot 0
  counts-mismatch  counts disagree with the slots
  list-reply       inventory answers a JSON list
"""
import json
import os
import struct
import sys
import zipfile
import zlib
from pathlib import Path

def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


# A real 1x1 PNG, like the frame the game would present.
PNG = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
       + _chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + _chunk(b"IEND", b""))


def reply(value, code=0):
    print(json.dumps(value))
    sys.exit(code)


def main(argv):
    socket = os.environ.get("HORIZON_CONTROL", "control.sock")
    if argv[:1] == ["--socket"]:
        socket, argv = argv[1], argv[2:]
    mode = set(filter(None, os.environ.get("FAKE_CTL_MODE", "").split(",")))
    state_file = Path(socket + ".state")
    command, args = argv[0], argv[1:]
    if command == "launch":
        if "unreachable" in mode:
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
        Path(args[0]).write_bytes(b"not a png" if "no-png" in mode else PNG)
        reply({"path": args[0]})
    if command == "give":
        item = args[0] if ":" in args[0] else "minecraft:" + args[0]
        count = int(args[1]) if len(args) > 1 else 1
        namespace, _, name = item.partition(":")
        known = namespace == "minecraft"
        for mod in state["mods"]:
            with zipfile.ZipFile(mod) as archive:
                known |= f"assets/{namespace}/items/{name}.json" in archive.namelist()
        if not known and "accept-anything" not in mode:
            reply({"error": f"unknown item {item}"}, 1)
        stack = {"item": item, "count": count}
        if "substring" in mode:
            stack = {"item": "minecraft:paper", "count": 1, "components": "{custom_name:'" + item + "'}"}
        elif "prefix" in mode:
            stack = {"item": item + "_block", "count": count}
        elif "two" in mode:
            stack["count"] = count + 1
        if "give-lies" not in mode:
            state["inventory"].append(stack)
            state["hidden_reads"] = 2 if "late" in mode else 0
        state_file.write_text(json.dumps(state))
        reply({"ok": True, "given": count})
    if command == "inventory":
        if "list-reply" in mode:
            reply([{"item": s["item"]} for s in state["inventory"]])
        stacks = state["inventory"]
        if state.get("hidden_reads"):
            state["hidden_reads"] -= 1
            state_file.write_text(json.dumps(state))
            stacks = stacks[:-1]
        slots = [None] * 36
        for index, stack in enumerate(stacks[:36]):
            slots[index] = stack
        entry = lambda n, s: {"slot": n, "item": None} if s is None else {**s, "slot": n}
        hotbar = [entry(n, slots[n]) for n in range(9)]
        if "malformed" in mode:
            hotbar = hotbar[:8]
        if "duplicate-slot" in mode:
            hotbar[1]["slot"] = 0
        counts = {}
        for stack in stacks[:36]:
            counts[stack["item"]] = counts.get(stack["item"], 0) + stack["count"]
        if "counts-mismatch" in mode and stacks:
            counts[stacks[-1]["item"]] += 1
        reply({"selected": 1, "held": slots[0], "hotbar": hotbar, "main": [entry(n, slots[n]) for n in range(9, 36)],
               "armor": [{**entry(500 + i, None), "part": part} for i, part in enumerate(["head", "chest", "legs", "feet"])],
               "offhand": entry(504, None), "carried": None, "counts": counts})
    if command == "quit":
        if "quit-hangs" in mode:
            reply({"error": "timed out waiting for the game", "kind": "timeout"}, 1)
        state_file.unlink()
        reply({"quit": True})
    reply({"error": f"unknown command {command}", "kind": "usage"}, 2)


if __name__ == "__main__":
    main(sys.argv[1:])

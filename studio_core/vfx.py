"""HS-025: the ``studio.vfx/1`` effect model, validation and seeded simulation (core side).

Mirrors ``vfx_engine.js`` (the editor preview): the same PRNG, draw order and closed-form motion,
so the core and the editor agree on every particle (``tests/test_vfx.py`` checks both against
one fixture). Effects are canonical project objects of kind ``vfx``. They are Studio authoring
data: the ``.hmod`` generator leaves them out, because no audited Horizon revision has a contract
for custom particles (``render.custom_particles``). Nothing here claims in-game rendering.
"""
from __future__ import annotations

import copy
import math
import re

SCHEMA = "studio.vfx/1"
LIMITS = {"emitters": 8, "bursts": 16, "count": 512, "particles": 2048, "keys": 16, "duration": (0.05, 10),
          "speed": (0, 60), "lifetime": (0.01, 10), "gravity": (-50, 50), "drag": (0, 20), "spread": (0, 180),
          "radius": (0, 10), "stretch": (0, 0.5), "size": (0, 8)}
ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
HEX_RE = re.compile(r"^#[0-9a-f]{6}$")
GOLDEN = 0x9E3779B9
MASK = 0xFFFFFFFF


def impact_spark() -> dict:
    """The Impact Spark preset (identical to ``HorizonVfx.impactSpark()``)."""
    return {"schema": SCHEMA, "name": "Impact Spark", "duration": 0.8, "loop": False, "seed": 1337, "emitters": [
        {"id": "sparks", "bursts": [{"time": 0, "count": 28}], "shape": {"type": "sphere", "radius": 0.12},
         "direction": {"axis": [0, 1, 0], "spread": 70}, "speed": [3.5, 7], "lifetime": [0.25, 0.6],
         "gravity": 9.8, "drag": 2.5, "stretch": 0.035, "blend": "additive",
         "size": [[0, 0.1], [0.7, 0.06], [1, 0]], "color": [[0, "#fff6c8"], [0.35, "#ffbe3d"], [1, "#b8320f"]],
         "alpha": [[0, 1], [0.8, 0.9], [1, 0]]},
        {"id": "flash", "bursts": [{"time": 0, "count": 1}], "shape": {"type": "point", "radius": 0},
         "direction": {"axis": [0, 1, 0], "spread": 0}, "speed": [0, 0], "lifetime": [0.09, 0.09],
         "gravity": 0, "drag": 0, "stretch": 0, "blend": "additive",
         "size": [[0, 0.45], [1, 0.8]], "color": [[0, "#ffffff"], [1, "#ffd36b"]], "alpha": [[0, 0.95], [1, 0]]},
    ]}


def mulberry32(seed: int):
    state = seed & MASK

    def random() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & MASK
        t = ((state ^ (state >> 15)) * (state | 1)) & MASK
        t = ((t + (((t ^ (t >> 7)) * (t | 61)) & MASK)) & MASK) ^ t
        return ((t ^ (t >> 14)) & MASK) / 4294967296

    return random


def _num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate(effect) -> list[dict]:
    """Problems as ``[{path, code, message}]``; the same checks as ``HorizonVfx.validate``."""
    out: list[dict] = []

    def bad(path, code, message):
        out.append({"path": path, "code": code, "message": message})

    def in_range(path, value, limits):
        lo, hi = limits
        if not _num(value) or value < lo or value > hi:
            bad(path, "RANGE", f"{path} must be a number from {lo} to {hi}")

    def pair(path, value, limits):
        if not isinstance(value, list) or len(value) != 2:
            bad(path, "PAIR", f"{path} must be [min, max]")
            return
        in_range(f"{path}[0]", value[0], limits)
        in_range(f"{path}[1]", value[1], limits)
        if _num(value[0]) and _num(value[1]) and value[0] > value[1]:
            bad(path, "ORDER", f"{path}: min must not exceed max")

    def curve(path, keys, check):
        if not isinstance(keys, list) or not 2 <= len(keys) <= LIMITS["keys"]:
            bad(path, "CURVE", f"{path} needs 2 to {LIMITS['keys']} keys")
            return
        for i, key in enumerate(keys):
            if not isinstance(key, list) or len(key) != 2 or not _num(key[0]):
                bad(f"{path}[{i}]", "KEY", f"{path}[{i}] must be [time, value]")
                continue
            previous = keys[i - 1] if i else None
            if previous and isinstance(previous, list) and previous and _num(previous[0]) and key[0] < previous[0]:
                bad(f"{path}[{i}]", "KEY_ORDER", f"{path}: key times must not decrease")
            check(f"{path}[{i}]", key[1])
        if isinstance(keys[0], list) and keys[0] and keys[0][0] != 0:
            bad(path, "KEY_START", f"{path} must start at time 0")
        if isinstance(keys[-1], list) and keys[-1] and keys[-1][0] != 1:
            bad(path, "KEY_END", f"{path} must end at time 1")

    if not isinstance(effect, dict):
        bad("", "TYPE", "An effect must be an object")
        return out
    if effect.get("schema") != SCHEMA:
        bad("schema", "SCHEMA", f"schema must be {SCHEMA}")
    name = effect.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        bad("name", "NAME", "name must be 1-80 characters")
    in_range("duration", effect.get("duration"), LIMITS["duration"])
    if not isinstance(effect.get("loop"), bool):
        bad("loop", "TYPE", "loop must be true or false")
    seed = effect.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= MASK:
        bad("seed", "SEED", "seed must be an integer from 0 to 4294967295")
    emitters = effect.get("emitters")
    if not isinstance(emitters, list) or not 1 <= len(emitters) <= LIMITS["emitters"]:
        bad("emitters", "EMITTERS", f"An effect needs 1 to {LIMITS['emitters']} emitters")
        return out
    total, ids = 0, set()
    for i, e in enumerate(emitters):
        p = f"emitters[{i}]"
        if not isinstance(e, dict):
            bad(p, "TYPE", f"{p} must be an object")
            continue
        if not isinstance(e.get("id"), str) or not ID_RE.fullmatch(e["id"]):
            bad(f"{p}.id", "ID", f"{p}.id: use lowercase letters, numbers and underscores")
        elif e["id"] in ids:
            bad(f"{p}.id", "DUPLICATE", f"Duplicate emitter id {e['id']}")
        ids.add(e.get("id"))
        bursts = e.get("bursts")
        if not isinstance(bursts, list) or not 1 <= len(bursts) <= LIMITS["bursts"]:
            bad(f"{p}.bursts", "BURSTS", f"{p} needs 1 to {LIMITS['bursts']} bursts")
        else:
            for j, burst in enumerate(bursts):
                burst = burst if isinstance(burst, dict) else {}
                in_range(f"{p}.bursts[{j}].time", burst.get("time"), (0, LIMITS["duration"][1]))
                count = burst.get("count")
                if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= LIMITS["count"]:
                    bad(f"{p}.bursts[{j}].count", "COUNT", f"count must be 1 to {LIMITS['count']}")
                else:
                    total += count
        shape = e.get("shape")
        if not isinstance(shape, dict) or shape.get("type") not in ("point", "sphere"):
            bad(f"{p}.shape", "SHAPE", "shape must be a point or a sphere")
        else:
            in_range(f"{p}.shape.radius", shape.get("radius"), LIMITS["radius"])
        direction = e.get("direction") if isinstance(e.get("direction"), dict) else {}
        axis = direction.get("axis")
        if (not isinstance(axis, list) or len(axis) != 3 or not all(_num(v) for v in axis)
                or math.hypot(*axis) < 1e-6):
            bad(f"{p}.direction.axis", "AXIS", "axis must be a non-zero [x, y, z]")
        in_range(f"{p}.direction.spread", direction.get("spread"), LIMITS["spread"])
        pair(f"{p}.speed", e.get("speed"), LIMITS["speed"])
        pair(f"{p}.lifetime", e.get("lifetime"), LIMITS["lifetime"])
        for field in ("gravity", "drag", "stretch"):
            in_range(f"{p}.{field}", e.get(field), LIMITS[field])
        if e.get("blend") not in ("additive", "alpha"):
            bad(f"{p}.blend", "BLEND", "blend must be additive or alpha")
        curve(f"{p}.size", e.get("size"), lambda path, v: in_range(path, v, LIMITS["size"]))
        curve(f"{p}.alpha", e.get("alpha"), lambda path, v: in_range(path, v, (0, 1)))

        def color(path, v):
            if not isinstance(v, str) or not HEX_RE.fullmatch(v):
                bad(path, "COLOR", f"{path} must be a colour like #ffbe3d")
        curve(f"{p}.color", e.get("color"), color)
    if total > LIMITS["particles"]:
        bad("emitters", "BUDGET", f"At most {LIMITS['particles']} particles per effect ({total} requested)")
    return out


def sample(keys, t):
    if t <= keys[0][0]:
        return keys[0][1]
    for i in range(1, len(keys)):
        t1, v1 = keys[i]
        if t <= t1:
            t0, v0 = keys[i - 1]
            f = (t - t0) / (t1 - t0) if t1 > t0 else 1
            return v0 + (v1 - v0) * f
    return keys[-1][1]


def gradient(keys, t) -> list[int]:
    def channel(c):
        return sample([[k, int(v[1 + 2 * c:3 + 2 * c], 16)] for k, v in keys], t)
    return [math.floor(channel(c) + 0.5) for c in range(3)]  # JavaScript's Math.round


def _norm(v):
    length = math.hypot(*v)
    return [x / length for x in v]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def spawn(effect: dict) -> list[dict]:
    particles = []
    for index, e in enumerate(effect["emitters"]):
        random = mulberry32((effect["seed"] + index * GOLDEN) % 4294967296)
        axis = _norm(e["direction"]["axis"])
        helper = [0, 1, 0] if abs(axis[1]) < 0.99 else [1, 0, 0]
        b1 = _norm(_cross(axis, helper))
        b2 = _cross(b1, axis)
        cos_max = math.cos(e["direction"]["spread"] * math.pi / 180)
        for burst in e["bursts"]:
            for _ in range(burst["count"]):
                u = [random() for _ in range(7)]
                r = e["shape"]["radius"] * math.cbrt(u[0]) if e["shape"]["type"] == "sphere" else 0
                cz = 2 * u[1] - 1
                sz = math.sqrt(max(0, 1 - cz * cz))
                phi = 2 * math.pi * u[2]
                position = [r * sz * math.cos(phi), r * cz, r * sz * math.sin(phi)]
                cos_t = 1 - u[3] * (1 - cos_max)
                sin_t = math.sqrt(max(0, 1 - cos_t * cos_t))
                psi = 2 * math.pi * u[4]
                local = [sin_t * math.cos(psi), cos_t, sin_t * math.sin(psi)]
                direction = [b1[c] * local[0] + axis[c] * local[1] + b2[c] * local[2] for c in range(3)]
                speed = e["speed"][0] + (e["speed"][1] - e["speed"][0]) * u[5]
                life = e["lifetime"][0] + (e["lifetime"][1] - e["lifetime"][0]) * u[6]
                particles.append({"emitter": index, "born": burst["time"], "life": life, "position": position,
                                  "velocity": [d * speed for d in direction]})
    return particles


def _position_at(p, e, age):
    g, k = [0, -e["gravity"], 0], e["drag"]
    if k > 1e-9:
        return [p["position"][c] + g[c] / k * age + (p["velocity"][c] - g[c] / k) * (1 - math.exp(-k * age)) / k
                for c in range(3)]
    return [p["position"][c] + p["velocity"][c] * age + 0.5 * g[c] * age * age for c in range(3)]


def simulate(effect: dict, time: float, spawned: list[dict] | None = None) -> list[dict]:
    """Particles alive at ``time``: position, trail end, size, colour, opacity."""
    spawned = spawn(effect) if spawned is None else spawned
    t = (time % effect["duration"]) if effect["loop"] else time
    alive = []
    for p in spawned:
        e = effect["emitters"][p["emitter"]]
        age = t - p["born"]
        if age < 0 or age >= p["life"]:
            continue
        a = age / p["life"]
        alive.append({"emitter": p["emitter"], "age": age, "position": _position_at(p, e, age),
                      "trail": _position_at(p, e, max(0, age - e["stretch"])), "size": sample(e["size"], a),
                      "alpha": sample(e["alpha"], a), "color": gradient(e["color"], a), "blend": e["blend"]})
    return alive


def diagnostics(obj: dict, label: str) -> list[dict]:
    """Graph diagnostics for one ``vfx`` project object."""
    props = copy.deepcopy(obj.get("props") or {})
    found = [{"level": "error", "code": "VFX_" + problem["code"], "uid": obj["uid"],
              "message": f"{label}: {problem['message']}"} for problem in validate(props)]
    found.append({"level": "warning", "code": "VFX_STUDIO_ONLY", "uid": obj["uid"],
                  "message": f"{label} is a Studio preview and is not exported: no audited Horizon revision has a "
                             "contract for custom particles (render.custom_particles)"})
    return found

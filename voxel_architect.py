"""Deterministic geometry -> Java Edition 26.3 compressed NBT structure templates.

Offline, no dependencies and no bundled Mojang assets. Horizon content-mod support
for namespace structures is experimental; validate in the running game.
"""
from __future__ import annotations

import gzip
import io
import math
import random
import re
import struct

IDENT = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
BLOCK = re.compile(r'^minecraft:[a-z0-9_./-]+$')
PALETTES = {
    'stone': ('minecraft:stone_bricks', 'minecraft:polished_andesite', 'minecraft:sea_lantern'),
    'prismarine': ('minecraft:prismarine_bricks', 'minecraft:dark_prismarine', 'minecraft:sea_lantern'),
    'copper': ('minecraft:cut_copper', 'minecraft:oxidized_cut_copper', 'minecraft:glowstone'),
    'nether': ('minecraft:polished_blackstone_bricks', 'minecraft:nether_bricks', 'minecraft:shroomlight'),
    'end': ('minecraft:end_stone_bricks', 'minecraft:purpur_block', 'minecraft:end_rod'),
    'quartz': ('minecraft:quartz_bricks', 'minecraft:quartz_pillar', 'minecraft:sea_lantern'),
}
MODES = ('spiral_tower', 'sky_dome', 'labyrinth', 'floating_island', 'crystal_grove', 'battle_arena')
MAX_STRUCTURES = 8
MAX_BLOCKS = 12000
DATA_VERSION = 5023  # Minecraft Java Edition 26.3


def _tag(kind: int, name: str, payload: bytes) -> bytes:
    raw = name.encode('utf-8')
    return struct.pack('>BH', kind, len(raw)) + raw + payload


def _string(value: str) -> bytes:
    raw = value.encode('utf-8')
    return struct.pack('>H', len(raw)) + raw


def _compound(*members: bytes) -> bytes:
    return b''.join(members) + b'\0'


def _int_list(values) -> bytes:
    return struct.pack('>BI', 3, len(values)) + b''.join(struct.pack('>i', v) for v in values)


def _compound_list(values: list[bytes]) -> bytes:
    return struct.pack('>BI', 10, len(values)) + b''.join(values)


def serialize_structure(cells: dict[tuple[int, int, int], str]) -> bytes:
    """Gzip-compressed NBT with Java structure's size/palette/blocks/entities."""
    if not cells or len(cells) > MAX_BLOCKS:
        raise ValueError(f'Structure requires 1..{MAX_BLOCKS} blocks')
    for (x, y, z), block in cells.items():
        if not all(isinstance(v, int) and 0 <= v < 32 for v in (x, y, z)):
            raise ValueError('Structure coordinates must be in 0..31')
        if not isinstance(block, str) or not BLOCK.fullmatch(block):
            raise ValueError('Invalid vanilla block name')
    sx = max(k[0] for k in cells) + 1
    sy = max(k[1] for k in cells) + 1
    sz = max(k[2] for k in cells) + 1
    palette = sorted(set(cells.values()))
    lookup = {name: index for index, name in enumerate(palette)}
    block_entries = []
    for (x, y, z), name in sorted(cells.items(), key=lambda pair: (pair[0][1], pair[0][2], pair[0][0])):
        block_entries.append(_compound(
            _tag(3, 'state', struct.pack('>i', lookup[name])),
            _tag(9, 'pos', _int_list((x, y, z))),
        ))
    root = _compound(
        _tag(3, 'DataVersion', struct.pack('>i', DATA_VERSION)),
        _tag(9, 'size', _int_list((sx, sy, sz))),
        _tag(9, 'palette', _compound_list([_compound(_tag(8, 'Name', _string(name))) for name in palette])),
        _tag(9, 'blocks', _compound_list(block_entries)),
        _tag(9, 'entities', _compound_list([])),
    )
    nbt = _tag(10, '', root)
    out = io.BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=out, compresslevel=9, mtime=0) as writer:
        writer.write(nbt)
    return out.getvalue()


def generate_structure(spec: dict) -> dict[tuple[int, int, int], str]:
    if not isinstance(spec, dict):
        raise ValueError('Structure must be an object')
    label = spec.get('id')
    if not isinstance(label, str) or not IDENT.fullmatch(label):
        raise ValueError('Structure ID: use lowercase letters, digits and underscores')
    kind = spec.get('kind')
    if kind not in MODES:
        raise ValueError('Unknown structure generator')
    theme = spec.get('theme', 'stone')
    if theme not in PALETTES:
        raise ValueError('Unknown structure palette')
    raw_size = spec.get('size', 19)
    if isinstance(raw_size, bool) or not isinstance(raw_size, int) or raw_size < 7 or raw_size > 29 or raw_size % 2 == 0:
        raise ValueError('Structure size must be an odd integer between 7 and 29')
    seed = spec.get('seed', 0)
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**31 - 1:
        raise ValueError('Structure seed must be a non-negative 32-bit integer')
    a, b, glow = PALETTES[theme]
    vox: dict[tuple[int, int, int], str] = {}
    s = raw_size
    c = s // 2
    def put(x, y, z, block):
        if 0 <= x < s and 0 <= y < 32 and 0 <= z < s:
            vox[(x, y, z)] = block
    if kind == 'sky_dome':
        # A walkable basin with concentric arches and four luminous entrances.
        radius = c - 1
        for x in range(s):
            for z in range(s):
                dist = math.hypot(x - c, z - c)
                if dist <= radius and dist >= radius - 2:
                    put(x, 0, z, b)
                elif dist < radius - 2:
                    put(x, 0, z, a)
                for y in range(1, radius + 2):
                    delta = math.sqrt(dist * dist + (y - 1) * (y - 1))
                    if radius - .65 <= delta <= radius + .45 and y >= 2:
                        if (abs(x-c) <= 1 or abs(z-c) <= 1) and y < 4:
                            continue
                        put(x, y, z, glow if y % 5 == 0 else b)
        for x,z in ((c,c),(c-3,c),(c+3,c),(c,c-3),(c,c+3)):
            put(x, 1, z, glow)
    elif kind == 'spiral_tower':
        height = min(30, s + 7)
        radius = max(2, c-2)
        # Central support, radial two-thread stairs, guard rails and a top observation deck.
        for y in range(height):
            put(c, y, c, b)
            angle = y * .63
            for offset in (0, math.pi):
                x = round(c + radius * math.cos(angle+offset))
                z = round(c + radius * math.sin(angle+offset))
                put(x,y,z,a)
                # stairs are platforms, not real stair block states
                if y % 4 == 0:
                    put(x,y+1,z,glow)
        for x in range(c-radius-1,c+radius+2):
            for z in range(c-radius-1,c+radius+2):
                r=math.hypot(x-c,z-c)
                if r<=radius+1:
                    put(x,0,z,b)
                    put(x,height-1,z,b if r>radius-1 else a)
        for x,z in ((c-radius,c),(c+radius,c),(c,c-radius),(c,c+radius)):
            put(x,height,z,glow)
    elif kind == 'floating_island':
        rng = random.Random(seed)
        radius = c - 2
        # Floating ellipsoid tapering into a pointed underside. A walkable top
        # and four deterministic terraces create a useful modular prefab.
        ground = min(21, c + 4)
        for x in range(s):
            for z in range(s):
                d = math.hypot(x-c, z-c)
                if d > radius: continue
                lower = max(1, int((radius - d) * 1.2))
                for y in range(ground-lower, ground+1):
                    put(x, y, z, a if y == ground else b)
                if d < radius-2 and rng.randrange(26) == 0:
                    put(x, ground+1, z, glow)
        for dx, dz in ((-1,0),(1,0),(0,-1),(0,1)):
            for n in range(1, radius):
                x,z=c+dx*n,c+dz*n
                put(x, ground+1, z, b)
        for y in range(ground+1, min(31, ground+6)):
            put(c,y,c,glow if y%2 else b)
    elif kind == 'crystal_grove':
        rng = random.Random(seed)
        radius = c - 1
        for x in range(s):
            for z in range(s):
                if math.hypot(x-c,z-c) <= radius:
                    put(x,0,z,b if (x+z)%5==0 else a)
        # Seed controls placement, height and branch direction.
        points=[(c,c,min(25,s+1))]
        for _ in range(max(6,s//2)):
            x,z=rng.randrange(2,s-2),rng.randrange(2,s-2)
            if math.hypot(x-c,z-c)<radius-1:
                points.append((x,z,rng.randrange(3,min(16,s))))
        for x,z,height in points:
            dx,dz=rng.choice(((1,0),(-1,0),(0,1),(0,-1)))
            for y in range(1,height+1):
                offset = (y//5 if (x,z)!=(c,c) else y//7)
                bx,bz=x+dx*offset,z+dz*offset
                put(bx,y,bz,glow if y%3==0 else b)
                if y%4==0:
                    for ax,az in ((-1,0),(1,0),(0,-1),(0,1)):
                        put(bx+ax,y,bz+az,a)
            put(x+dx*(height//5),min(31,height+1),z+dz*(height//5),glow)
    elif kind == 'battle_arena':
        radius=c-1
        # A fighting floor, ringed seating and cardinal gates.
        for x in range(s):
            for z in range(s):
                d=math.hypot(x-c,z-c)
                if d<=radius:
                    put(x,0,z,a if d<radius-3 else b)
                if radius-3<=d<=radius and not ((abs(x-c)<=1 or abs(z-c)<=1) and d>radius-2):
                    height=max(1, int(radius-d)+1)
                    for y in range(1,height+2):
                        put(x,y,z,glow if y==height+1 and (x+z)%5==0 else b)
        for x,z in ((1,1),(s-2,1),(1,s-2),(s-2,s-2)):
            if math.hypot(x-c,z-c)<=radius+1:
                for y in range(1,min(12,s//2+1)):
                    put(x,y,z,b)
                put(x,min(12,s//2+1),z,glow)
    else:
        # Seeded depth-first perfect maze; two-block cells, connected corridors.
        rng = random.Random(seed)
        nc = (s-1)//2
        open_cells={(1,1)}
        stack=[(0,0)]
        visited={(0,0)}
        while stack:
            x,z=stack[-1]
            options=[(x+dx,z+dz) for dx,dz in ((1,0),(-1,0),(0,1),(0,-1))
                     if 0<=x+dx<nc and 0<=z+dz<nc and (x+dx,z+dz) not in visited]
            if not options:
                stack.pop();continue
            nx,nz=rng.choice(options)
            visited.add((nx,nz))
            open_cells.add((2*nx+1,2*nz+1))
            open_cells.add((x+nx+1,z+nz+1))
            stack.append((nx,nz))
        open_cells.update(((1,0),(s-2,s-1)))
        for x in range(s):
            for z in range(s):
                put(x,0,z,a)
                if (x,z) not in open_cells:
                    for y in range(1,5):
                        put(x,y,z, glow if y==4 and (x+z)%7==0 else b)
    rotation=spec.get('rotation', 0)
    mirror=spec.get('mirror', 'none')
    if isinstance(rotation,bool) or type(rotation) is not int or rotation not in (0,90,180,270):
        raise ValueError('Rotation must be 0, 90, 180 or 270 degrees')
    if mirror not in ('none','x','z'):
        raise ValueError('Mirror must be none, x or z')
    if rotation or mirror!='none':
        rotated={}
        for (x,y,z),block in vox.items():
            if mirror=='x': x=s-1-x
            if mirror=='z': z=s-1-z
            if rotation==90: x,z=z,s-1-x
            elif rotation==180: x,z=s-1-x,s-1-z
            elif rotation==270: x,z=s-1-z,x
            rotated[(x,y,z)]=block
        vox=rotated
    if not vox or len(vox) > MAX_BLOCKS:
        raise ValueError(f'Structure would exceed the {MAX_BLOCKS}-block limit')
    return vox


def preview_structure(spec: dict, layer: int=0) -> dict:
    cells = generate_structure(spec)
    if isinstance(layer, bool) or not isinstance(layer, int) or not 0<=layer<32:
        raise ValueError('Layer must be within 0..31')
    s=spec.get('size',19)
    lines=[]
    palette=sorted(set(cells.values()))
    indices={name:i for i,name in enumerate(palette)}
    for z in range(s):
        lines.append(''.join('█' if (x,layer,z) in cells else '·' for x in range(s)))
    return {'id': spec['id'], 'kind':spec['kind'], 'theme':spec.get('theme','stone'),
            'size':[max(x for x,_,_ in cells)+1, max(y for _,y,_ in cells)+1, max(z for _,_,z in cells)+1],
            'blocks':len(cells), 'palette':palette,
            'layer':layer, 'top_down':'\n'.join(lines),
            'voxels':[[x,y,z,indices[b]] for (x,y,z),b in sorted(cells.items())]}

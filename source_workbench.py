"""Safe, deterministic source overlays and user-supplied resource-pack indexing.

Never executes uploaded Rust/JSON or distributes user game resources.
"""
from __future__ import annotations

import base64
import io
import json
import re
import zipfile
from pathlib import PurePosixPath

MAX_SOURCE_FILES = 64
MAX_SOURCE_BYTES = 128 * 1024
MAX_SOURCE_TOTAL = 512 * 1024
MAX_PACK_BYTES = 64 * 1024 * 1024
MAX_TEX_BYTES = 512 * 1024
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def safe_overrides(overrides, mod_id: str, generated: dict[str, bytes]) -> dict[str, bytes]:
    """Allow JSON-only overlays of generated content. No arbitrary paths or code execution."""
    if overrides in (None, {}):
        return {}
    if not isinstance(overrides, dict) or len(overrides) > MAX_SOURCE_FILES:
        raise ValueError('source_overrides: expected at most 64 files')
    result = {}
    aggregate = 0
    for path, text in overrides.items():
        if not isinstance(path, str) or path not in generated or not path.endswith('.json'):
            raise ValueError(f'Cannot override ungenerated JSON path: {str(path)[:120]}')
        if not (path.startswith(f'assets/{mod_id}/') or path.startswith(f'data/{mod_id}/')):
            raise ValueError('Only this mod namespace can be overridden')
        if not isinstance(text, str):
            raise ValueError(f'{path}: source must be UTF-8 text')
        raw = text.encode('utf-8')
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError(f'{path}: JSON must be <= 128 KiB')
        aggregate += len(raw)
        if aggregate > MAX_SOURCE_TOTAL:
            raise ValueError('Source overlays exceed 512 KiB')
        try:
            parsed = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f'{path}: invalid JSON: {exc}') from exc
        if not isinstance(parsed, dict):
            raise ValueError(f'{path}: expected a JSON object')
        if '/models/' in path:
            validate_model(parsed)
        result[path] = (json.dumps(parsed, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    return result


def validate_model(model: dict):
    """Inspect editor-supported cuboids, reject malformed or oversized geometry."""
    elements = model.get('elements', [])
    if not isinstance(elements, list) or len(elements) > 128:
        raise ValueError('Model must have at most 128 elements')
    for element in elements:
        if not isinstance(element, dict):
            raise ValueError('Model element must be an object')
        for name in ('from', 'to'):
            coords = element.get(name)
            if not isinstance(coords, list) or len(coords) != 3 or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not -16 <= v <= 32
                for v in coords
            ):
                raise ValueError(f'Model {name} requires 3 finite coordinates in [-16,32]')
        if any(a >= b for a, b in zip(element['from'], element['to'])):
            raise ValueError('Model element to must be greater than from')
        if 'faces' in element and not isinstance(element['faces'], dict):
            raise ValueError('Model faces must be an object')


# Only extract a small known subset; never copy user pack assets into a release.
PACK_TEXTURES = {
    'minecraft:diamond': 'item/diamond.png',
    'minecraft:emerald': 'item/emerald.png',
    'minecraft:iron_ingot': 'item/iron_ingot.png',
    'minecraft:gold_ingot': 'item/gold_ingot.png',
    'minecraft:amethyst_shard': 'item/amethyst_shard.png',
    'minecraft:stick': 'item/stick.png',
    'minecraft:stone': 'block/stone.png',
    'minecraft:iron_block': 'block/iron_block.png',
    'minecraft:amethyst_block': 'block/amethyst_block.png',
    'minecraft:oak_planks': 'block/oak_planks.png',
    'minecraft:glass': 'block/glass.png',
    'minecraft:gold_block': 'block/gold_block.png',
    'minecraft:diamond_block': 'block/diamond_block.png',
    'minecraft:emerald_block': 'block/emerald_block.png',
    'minecraft:crafting_table': 'block/crafting_table_top.png',
    'minecraft:furnace': 'block/furnace_front.png',
    'minecraft:coal': 'item/coal.png',
    'minecraft:redstone': 'item/redstone.png',
}


def import_resource_pack(data: bytes) -> dict:
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_PACK_BYTES:
        raise ValueError('Resource pack must be a ZIP/JAR up to 64 MiB')
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError('Not a valid resource-pack ZIP/JAR') from exc
    result = {}
    with archive:
        for key, subpath in PACK_TEXTURES.items():
            name = f'assets/minecraft/textures/{subpath}'
            try:
                item = archive.getinfo(name)
            except KeyError:
                continue
            if item.file_size > MAX_TEX_BYTES or item.compress_size == 0:
                continue
            with archive.open(item) as file:
                raw = file.read(MAX_TEX_BYTES + 1)
            if len(raw) <= MAX_TEX_BYTES and raw.startswith(PNG_SIGNATURE):
                result[key] = 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii')
    return {'textures': result, 'count': len(result), 'local_only': True}

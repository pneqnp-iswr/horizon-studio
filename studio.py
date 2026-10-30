#!/usr/bin/env python3
"""Horizon Studio: offline content-mod editor, project & experimental .hmod packager.

Generates Horizon API 0.2 content-only mods, based on the official specification:
https://playhorizon.dev/docs/content-mods
Does not claim to implement the official cargo-horizon-mod validator.
"""
from __future__ import annotations

import base64
import binascii
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
from pathlib import Path
import re
import struct
import sys
import zlib
import zipfile
from source_workbench import safe_overrides, import_resource_pack, MAX_PACK_BYTES
from voxel_architect import generate_structure, serialize_structure, preview_structure, MAX_STRUCTURES
from security.request_policy import session_token, trusted_request, authorized_post, content_type_allowed
from studio_core.graph import AssetGraph
from studio_core.migrate import from_editor_state, source_schema, to_editor_state, upgrade
from studio_core.project_schema import SCHEMA, dumps
from studio_core.workspace import WorkspaceStore, WorkspaceNotFound, WorkspaceConflict, WorkspaceCorrupt
import threading

HOST = '127.0.0.1'
PORT = 8787
# Editor scripts served at /<name> and bundled into the Windows executable, each with a marker
# the frozen smoke test looks for. index.html, the build and the smoke test all use this list.
WEB_SCRIPTS = {
    'i18n.js': b'HorizonI18n',
    'model_viewer.js': b'HorizonModelViewer',
    'editor_history.js': b'HorizonStudioHistory',
    'editor_model.js': b'HorizonStudioModel',
    'editor_render.js': b'HorizonStudioRender',
    'editor_api.js': b'HorizonStudioApi',
    'editor_workspace.js': b'createWorkspaceSync',
    'source_workbench_ui.js': b'source_overrides',
}
# Every file the packaged application needs at runtime, relative to the repository root.
BUNDLED_FILES = ('index.html', 'VERSION', *WEB_SCRIPTS, 'assets/branding/horizon-studio-mark.png')
MAX_REQUEST_BYTES = 6 * 1024 * 1024
ID_RE = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
VERSION_RE = re.compile(r'^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')
MC_RESOURCE_RE = re.compile(r'^minecraft:[a-z0-9_./-]+$')
VANILLA_BLOCKS = {
    'minecraft:iron_block': 'minecraft:block/iron_block',
    'minecraft:amethyst_block': 'minecraft:block/amethyst_block',
    'minecraft:glass': 'minecraft:block/glass',
    'minecraft:stone': 'minecraft:block/stone',
    'minecraft:oak_planks': 'minecraft:block/oak_planks',
}
VANILLA_ITEMS = {
    'minecraft:diamond': 'minecraft:item/diamond',
    'minecraft:emerald': 'minecraft:item/emerald',
    'minecraft:stick': 'minecraft:item/stick',
    'minecraft:amethyst_shard': 'minecraft:item/amethyst_shard',
    'minecraft:iron_ingot': 'minecraft:item/iron_ingot',
}
RARITIES = {'common', 'uncommon', 'rare', 'epic'}
TOOLS = {'none', 'pickaxe', 'axe', 'shovel', 'hoe'}
TOOL_TIERS = {'none', 'stone', 'iron', 'diamond'}


def fail(message: str):
    raise ValueError(message)


def require_text(value, field, maximum=100):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        fail(f'{field}: required text, maximum {maximum} characters')
    return value.strip()


def ident(value, field):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        fail(f'{field}: use 1-64 lowercase letters, numbers, underscores; start with a letter')
    return value


def toml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def finite_number(value, field, minimum, maximum):
    if isinstance(value, bool):
        fail(f'{field}: expected a number')
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        fail(f'{field}: expected a number')
    if not math.isfinite(result) or not minimum <= result <= maximum:
        fail(f'{field}: must be within {minimum}..{maximum}')
    return result


def integer(value, field, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not re.fullmatch(r'-?\d+', str(value)):
        fail(f'{field}: expected an integer')
    number = int(value)
    if not minimum <= number <= maximum:
        fail(f'{field}: must be within {minimum}..{maximum}')
    return number


def validated_png(data_url):
    if not data_url:
        return None
    if not isinstance(data_url, str) or not data_url.startswith('data:image/png;base64,'):
        fail('Custom texture must be a PNG file')
    try:
        data = base64.b64decode(data_url.split(',', 1)[1], validate=True)
    except (ValueError, binascii.Error):
        fail('Corrupted PNG base64')
    if len(data) > 1024 * 1024 or len(data) < 45 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        fail('PNG must be valid and under 1 MiB')
    # Scan PNG chunk structure (including CRC), not only its magic bytes.
    offset = 8
    seen_ihdr = seen_iend = seen_idat = False
    while offset < len(data):
        if offset + 12 > len(data):
            fail('PNG: truncated chunk')
        length = struct.unpack_from('>I', data, offset)[0]
        tag = data[offset + 4: offset + 8]
        end = offset + 12 + length
        if length > len(data) or end > len(data):
            fail('PNG: truncated data')
        if (zlib.crc32(data[offset + 4:offset + 8 + length]) & 0xffffffff) != struct.unpack_from('>I', data, offset + 8 + length)[0]:
            fail('PNG: CRC checksum mismatch')
        if offset == 8:
            if tag != b'IHDR' or length != 13:
                fail('PNG: missing IHDR')
            width, height = struct.unpack_from('>II', data, offset + 8)
            if not 1 <= width <= 1024 or not 1 <= height <= 1024:
                fail('PNG: dimensions must be 1-1024 pixels')
            seen_ihdr = True
        if tag == b'IDAT':
            seen_idat = True
        if tag == b'IEND':
            if length != 0 or end != len(data):
                fail('PNG: invalid IEND')
            seen_iend = True
            break
        offset = end
    if not seen_ihdr or not seen_iend or not seen_idat:
        fail('PNG: missing required chunks')
    return data


def _recipe(ident_name, item, mod_id, known_ids):
    recipe_id = ident(ident_name, 'Recipe ID')
    if not isinstance(item, dict):
        fail(f'Recipe {recipe_id}: expected an object')
    kind = item.get('type', 'shaped')
    if kind not in ('shaped', 'shapeless'):
        fail(f'Recipe {recipe_id}: type must be shaped or shapeless')
    grid = item.get('grid')
    if not isinstance(grid, list) or len(grid) != 9:
        fail(f'Recipe {recipe_id}: grid must contain exactly nine slots')
    cells = []
    for raw in grid:
        if raw in ('', None):
            cells.append('')
        elif isinstance(raw, str) and (raw in known_ids or MC_RESOURCE_RE.fullmatch(raw)):
            cells.append(raw)
        else:
            fail(f'Recipe {recipe_id}: invalid or unknown ingredient {raw!r}')
    result = item.get('result')
    if not isinstance(result, str) or result not in known_ids:
        fail(f'Recipe {recipe_id}: result must be a block or item from this project')
    count = integer(item.get('count', 1), f'Recipe {recipe_id} result count', 1, 64)
    if not any(cells):
        fail(f'Recipe {recipe_id}: add at least one ingredient')
    data = {'type': 'minecraft:crafting_' + kind}
    if kind == 'shapeless':
        data['ingredients'] = [cell for cell in cells if cell]
    else:
        # Trim unused edges to allow ordinary crafting grids of any size.
        occupied = [(i // 3, i % 3) for i, c in enumerate(cells) if c]
        rows = [r for r, _ in occupied]
        cols = [c for _, c in occupied]
        first_r, last_r, first_c, last_c = min(rows), max(rows), min(cols), max(cols)
        letters = {}
        lines = []
        for row in range(first_r, last_r + 1):
            line = ''
            for col in range(first_c, last_c + 1):
                cell = cells[3 * row + col]
                if not cell:
                    line += ' '
                else:
                    if cell not in letters:
                        letters[cell] = chr(65 + len(letters))
                    line += letters[cell]
            lines.append(line)
        data['key'] = {symbol: ingredient for ingredient, symbol in letters.items()}
        data['pattern'] = lines
    data['result'] = {'id': result, 'count': count}
    return data


def create_project_files(request: dict) -> tuple[str, dict[str, bytes]]:
    if not isinstance(request, dict):
        fail('Expected an object')
    mod_id = ident(request.get('id'), 'Mod ID')
    name = require_text(request.get('name'), 'Mod name', 100)
    author = require_text(request.get('author', 'Creator'), 'Author', 100)
    description = request.get('description', '')
    if not isinstance(description, str) or len(description) > 300:
        fail('Description must be at most 300 characters')
    version = request.get('version', '0.1.0')
    if not isinstance(version, str) or len(version) > 40 or not VERSION_RE.fullmatch(version):
        fail('Version: use e.g. 0.2.0 or 1.0.0')
    blocks, items, recipes, structures = (request.get(category, []) for category in ('blocks', 'items', 'recipes', 'structures'))
    if any(not isinstance(x, list) for x in (blocks, items, recipes, structures)):
        fail('Blocks, items and recipes must be arrays')
    if not blocks and not items and not structures:
        fail('Add at least one block, item or structure')
    if len(blocks) > 32 or len(items) > 32 or len(recipes) > 64 or len(structures) > MAX_STRUCTURES:
        fail('Maximum 32 blocks, 32 items, 64 recipes and 8 structures per project')
    manifest = '\n'.join([
        f'id = {toml_quote(mod_id)}',
        f'name = {toml_quote(name)}',
        f'version = {toml_quote(version)}',
        f'description = {toml_quote(description)}',
        f'authors = [{toml_quote(author)}]',
        'api = "0.2"',
        'side = "both"',
        'capabilities = ["registries"]',
        '',
    ])
    out = {'horizon-mod.toml': manifest.encode('utf-8')}
    names = {}
    names_ru = {}
    mining_tags = {}
    used_ids = set()
    known_ids = set()

    def assign_id(obj, category):
        if not isinstance(obj, dict):
            fail(f'{category}: each entry must be an object')
        item_id = ident(obj.get('id'), f'{category} ID')
        if item_id in used_ids:
            fail(f'Duplicate block/item ID: {item_id}')
        used_ids.add(item_id)
        label = require_text(obj.get('name'), f'{category} name', 100)
        known_ids.add(f'{mod_id}:{item_id}')
        local_name = obj.get('name_ru', '')
        if local_name not in ('', None):
            local_name = require_text(local_name, f'{category} Russian name', 100)
        else:
            local_name = label
        return item_id, label, local_name

    for obj in blocks:
        bid, label, label_ru = assign_id(obj, 'Block')
        template = obj.get('template', 'minecraft:iron_block')
        if template not in VANILLA_BLOCKS:
            fail(f'Block {bid}: unsupported template')
        hardness = finite_number(obj.get('hardness', 5), f'Block {bid} hardness', -1, 50)
        light = integer(obj.get('light', 0), f'Block {bid} light', 0, 15)
        props = {'hardness': hardness, 'light': light}
        optional = {
            'explosion_resistance': (0, 3600000),
            'friction': (0, 1),
        }
        for key, (lo, hi) in optional.items():
            if key in obj and obj[key] not in (None, ''):
                props[key] = finite_number(obj[key], f'Block {bid} {key}', lo, hi)
        if 'requires_tool' in obj:
            if not isinstance(obj['requires_tool'], bool):
                fail(f'Block {bid}: requires_tool must be a boolean')
            props['requires_tool'] = obj['requires_tool']
        if 'map_color' in obj and obj['map_color'] not in (None, ''):
            props['map_color'] = integer(obj['map_color'], f'Block {bid} map_color', 0, 61)
        if 'sounds' in obj and obj['sounds'] not in (None, ''):
            if obj['sounds'] not in VANILLA_BLOCKS:
                fail(f'Block {bid}: unsupported sound template')
            props['sounds'] = obj['sounds']
        texture = validated_png(obj.get('texture'))
        texture_ref = f'{mod_id}:block/{bid}' if texture else VANILLA_BLOCKS[template]
        if texture:
            out[f'assets/{mod_id}/textures/block/{bid}.png'] = texture
        out[f'data/{mod_id}/horizon/block/{bid}.json'] = json_bytes({'template': template, 'properties': props})
        out[f'assets/{mod_id}/blockstates/{bid}.json'] = json_bytes({
            'variants': {'': {'model': f'{mod_id}:block/{bid}'}}
        })
        out[f'assets/{mod_id}/models/block/{bid}.json'] = json_bytes({
            'parent': 'minecraft:block/cube_all', 'textures': {'all': texture_ref}
        })
        out[f'assets/{mod_id}/items/{bid}.json'] = json_bytes({
            'model': {'type': 'minecraft:model', 'model': f'{mod_id}:block/{bid}'}
        })
        out[f'data/{mod_id}/loot_table/blocks/{bid}.json'] = json_bytes({
            'type': 'minecraft:block', 'pools': [{
                'rolls': 1, 'entries': [{'type': 'minecraft:item', 'name': f'{mod_id}:{bid}'}],
                'conditions': [{'condition': 'minecraft:survives_explosion'}]
            }]
        })
        names[f'block.{mod_id}.{bid}'] = label
        names_ru[f'block.{mod_id}.{bid}'] = label_ru
        tool = obj.get('mining_tool', 'pickaxe' if obj.get('requires_tool') else 'none')
        tier = obj.get('tool_tier', 'none')
        if tool not in TOOLS or tier not in TOOL_TIERS:
            fail(f'Block {bid}: unsupported mining tool or tier')
        if tier != 'none' and tool == 'none':
            fail(f'Block {bid}: a mining tier requires a mining tool')
        if tool != 'none':
            mining_tags.setdefault(f'mineable/{tool}', []).append(f'{mod_id}:{bid}')
        if tier != 'none':
            mining_tags.setdefault(f'needs_{tier}_tool', []).append(f'{mod_id}:{bid}')

    for tag, values in sorted(mining_tags.items()):
        out[f'data/minecraft/tags/block/{tag}.json'] = json_bytes({'replace': False, 'values': values})

    for obj in items:
        iid, label, label_ru = assign_id(obj, 'Item')
        template = obj.get('template', 'minecraft:diamond')
        rarity = obj.get('rarity', 'common')
        if template not in VANILLA_ITEMS or rarity not in RARITIES:
            fail(f'Item {iid}: unsupported template/rarity')
        texture = validated_png(obj.get('texture'))
        texture_ref = f'{mod_id}:item/{iid}' if texture else VANILLA_ITEMS[template]
        if texture:
            out[f'assets/{mod_id}/textures/item/{iid}.png'] = texture
        data = {'template': template, 'rarity': rarity}
        if 'max_stack_size' in obj:
            data['max_stack_size'] = integer(obj['max_stack_size'], f'Item {iid} max_stack_size', 1, 99)
        out[f'data/{mod_id}/horizon/item/{iid}.json'] = json_bytes(data)
        out[f'assets/{mod_id}/models/item/{iid}.json'] = json_bytes({
            'parent': 'minecraft:item/generated', 'textures': {'layer0': texture_ref}
        })
        out[f'assets/{mod_id}/items/{iid}.json'] = json_bytes({
            'model': {'type': 'minecraft:model', 'model': f'{mod_id}:item/{iid}'}
        })
        names[f'item.{mod_id}.{iid}'] = label
        names_ru[f'item.{mod_id}.{iid}'] = label_ru

    recipe_ids = set()
    for obj in recipes:
        if not isinstance(obj, dict):
            fail('Recipe: expected an object')
        rid = ident(obj.get('id'), 'Recipe ID')
        if rid in recipe_ids:
            fail(f'Duplicate recipe ID: {rid}')
        recipe_ids.add(rid)
        out[f'data/{mod_id}/recipe/{rid}.json'] = json_bytes(_recipe(rid, obj, mod_id, known_ids))

    structure_ids = set()
    for spec in structures:
        cells = generate_structure(spec)
        sid = spec['id']
        if sid in structure_ids:
            fail(f'Duplicate structure ID: {sid}')
        structure_ids.add(sid)
        out[f'data/{mod_id}/structure/{sid}.nbt'] = serialize_structure(cells)

    out[f'assets/{mod_id}/lang/en_us.json'] = json_bytes(names)
    out[f'assets/{mod_id}/lang/ru_ru.json'] = json_bytes(names_ru)
    out.update(safe_overrides(request.get('source_overrides'), mod_id, out))
    return mod_id, out


def _archive(files):
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, content in sorted(files.items()):
            # Stable timestamps for reproducible output (1980 is ZIP's earliest date).
            info = zipfile.ZipInfo(path, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            # ZipInfo defaults create_system to 0 on Windows and 3 elsewhere; pin it so
            # every OS writes the same bytes (and the Unix mode below means what it says).
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return result.getvalue()


def project_zip(request: dict) -> bytes:
    mod_id, files = create_project_files(request)
    return _archive({f'{mod_id}/{path}': data for path, data in files.items()})


def hmod_zip(request: dict) -> bytes:
    # Format matches the documented content-only .hmod: manifest, data/, assets/ at root.
    # Always verify with `cargo horizon-mod check ...` before distributing.
    _, files = create_project_files(request)
    return _archive(files)


def inspect_project(request: dict):
    _, files = create_project_files(request)
    return {'files': sorted(files), 'file_count': len(files),
            'bytes_raw': sum(len(value) for value in files.values()),
            'manifest': files['horizon-mod.toml'].decode('utf-8'),
            'recipes': len(request.get('recipes', [])), 'structures': len(request.get('structures', [])), 'ok': True}


_workspace_lock = threading.Lock()


def workspace_for(server):
    with _workspace_lock:
        if not hasattr(server, 'studio_workspaces'):
            server.studio_workspaces = WorkspaceStore(Path.home() / '.horizon-studio' / 'workspaces')
        return server.studio_workspaces


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if sys.stdout is not None:
            print('[studio]', fmt % args)

    def response(self, code, mime, content: bytes, filename=None):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if not trusted_request(self.headers, self.server.server_address[1]):
            return self.response(403, 'application/json; charset=utf-8', b'{"error":"Untrusted request origin or host"}')
        if self.path == '/api/session':
            return self.response(200, 'application/json; charset=utf-8', json_bytes({'token': session_token(self.server)}))
        root = Path(__file__).parent
        if self.path in ('/', '/index.html'):
            self.response(200, 'text/html; charset=utf-8', (root / 'index.html').read_bytes())
        elif self.path.lstrip('/') in WEB_SCRIPTS:
            self.response(200, 'text/javascript; charset=utf-8', (root / self.path.lstrip('/')).read_bytes())
        elif self.path.startswith('/assets/'):
            target = (root / self.path.lstrip('/')).resolve()
            try:
                target.relative_to(root.resolve())
            except Exception:
                return self.response(403, 'text/plain; charset=utf-8', b'Forbidden')
            if target.is_file():
                ctype = 'application/octet-stream'
                if target.suffix == '.png': ctype = 'image/png'
                elif target.suffix == '.svg': ctype = 'image/svg+xml; charset=utf-8'
                elif target.suffix in {'.jpg', '.jpeg'}: ctype = 'image/jpeg'
                elif target.suffix == '.webp': ctype = 'image/webp'
                elif target.suffix == '.css': ctype = 'text/css; charset=utf-8'
                return self.response(200, ctype, target.read_bytes())
            return self.response(404, 'text/plain; charset=utf-8', b'Not found')
        else:
            self.response(404, 'text/plain; charset=utf-8', b'Not found')

    def do_POST(self):
        if self.path not in ('/api/export', '/api/hmod', '/api/preview', '/api/source', '/api/structure-preview', '/api/doctor', '/api/resourcepack',
                             '/api/project/open', '/api/project/save', '/api/workspace/write', '/api/workspace/recover'):
            return self.response(404, 'application/json', b'{"error":"Not found"}')
        if not trusted_request(self.headers, self.server.server_address[1]):
            return self.response(403, 'application/json; charset=utf-8', b'{"error":"Untrusted request origin or host"}')
        if not authorized_post(self.headers, self.server):
            return self.response(403, 'application/json; charset=utf-8', b'{"error":"Missing or invalid Studio session token"}')
        if not content_type_allowed(self.headers, self.path):
            return self.response(415, 'application/json; charset=utf-8', b'{"error":"Unsupported content type"}')
        try:
            raw_len = self.headers.get('Content-Length', '0')
            length = int(raw_len)
            max_size = MAX_PACK_BYTES if self.path == '/api/resourcepack' else MAX_REQUEST_BYTES
            if not 0 < length <= max_size:
                return self.response(413, 'application/json', b'{"error":"Payload too large or empty"}')
            if self.path == '/api/resourcepack':
                return self.response(200, 'application/json; charset=utf-8', json_bytes(import_resource_pack(self.rfile.read(length))))
            payload = json.loads(self.rfile.read(length), parse_constant=lambda x: fail(f'Invalid JSON number: {x}'))
            if self.path == '/api/structure-preview':
                if not isinstance(payload, dict) or 'structure' not in payload:
                    fail('Missing structure specification')
                return self.response(200, 'application/json; charset=utf-8', json_bytes(preview_structure(payload['structure'], payload.get('layer', 0))))
            if self.path == '/api/doctor':
                from mod_doctor import audit_project
                return self.response(200, 'application/json; charset=utf-8', json_bytes(audit_project(payload)))
            if self.path == '/api/workspace/recover':
                if not isinstance(payload, dict) or not isinstance(payload.get('project_id'), str):
                    fail('Expected project_id')
                result = workspace_for(self.server).recover(payload['project_id'])
                return self.response(200, 'application/json; charset=utf-8', json_bytes({
                    'state': to_editor_state(result['document']),
                    'revision': result['revision'],
                    'recovered_from_backup': result['recovered_from_backup']}))
            if self.path == '/api/workspace/write':
                if not isinstance(payload, dict) or not isinstance(payload.get('state'), dict):
                    fail('Expected project state')
                document = from_editor_state(payload['state'])
                outcome = workspace_for(self.server).save(
                    document, expected_revision=payload.get('expected_revision'))
                return self.response(200, 'application/json; charset=utf-8', json_bytes(outcome))
            if self.path == '/api/project/open':
                # Any supported project file -> editor state; older schemas are migrated in memory only.
                document = upgrade(payload)
                schema = source_schema(payload)
                return self.response(200, 'application/json; charset=utf-8', json_bytes({
                    'state': to_editor_state(document),
                    'migrated_from': None if schema == SCHEMA else schema,
                    'diagnostics': AssetGraph(document).diagnostics()}))
            if self.path == '/api/project/save':
                return self.response(200, 'application/json; charset=utf-8',
                                     dumps(from_editor_state(payload)).encode('utf-8'))
            mod_id, _ = create_project_files(payload)
            if self.path == '/api/source':
                _, files = create_project_files(payload)
                source = {path: raw.decode('utf-8') for path, raw in files.items() if path.endswith(('.json', '.toml')) and len(raw) <= 131072}
                return self.response(200, 'application/json; charset=utf-8', json_bytes({'files': source, 'count': len(source)}))
            if self.path == '/api/preview':
                return self.response(200, 'application/json; charset=utf-8', json_bytes(inspect_project(payload)))
            if self.path == '/api/hmod':
                return self.response(200, 'application/octet-stream', hmod_zip(payload), f'{mod_id}.hmod')
            return self.response(200, 'application/zip', project_zip(payload), f'{mod_id}-source.zip')
        except WorkspaceNotFound as exc:
            return self.response(404, 'application/json; charset=utf-8', json_bytes({'error': str(exc)}))
        except WorkspaceConflict as exc:
            return self.response(409, 'application/json; charset=utf-8', json_bytes({'error': str(exc)}))
        except WorkspaceCorrupt as exc:
            return self.response(422, 'application/json; charset=utf-8', json_bytes({'error': str(exc)}))
        except OSError:
            return self.response(500, 'application/json; charset=utf-8', json_bytes({'error': 'Workspace filesystem operation failed'}))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self.response(400, 'application/json; charset=utf-8', json_bytes({'error': str(exc)}))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    with ThreadingHTTPServer((HOST, port), Handler) as server:
        print(f'Horizon Studio running locally at http://{HOST}:{server.server_address[1]}')
        print('Ctrl+C to stop. All assets stay on this computer.')
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()

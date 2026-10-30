"""Non-authoritative, deterministic static diagnostics for Horizon Studio projects.

Not a replacement for cargo horizon-mod check or an in-game test. Never executes
mod code or reads arbitrary local paths.
"""
from __future__ import annotations


def audit_project(request: dict) -> dict:
    # Late import avoids a cycle; validation uses exactly the same output path
    # as the artifact generator, rather than a second independent schema.
    from studio import create_project_files
    issues = []

    def add(level, code, message, subject='project'):
        issues.append({'level': level, 'code': code, 'message': message, 'subject': subject})

    try:
        mod_id, files = create_project_files(request)
    except (ValueError, TypeError, KeyError) as exc:
        add('error', 'EXPORT_VALIDATION_FAILED', str(exc))
        return {'ok': False, 'issues': issues, 'stats': {'files': 0, 'bytes': 0}}

    recipes = request.get('recipes', [])
    known_local = {f'{mod_id}:{e["id"]}' for group in ('items', 'blocks') for e in request.get(group, [])}
    crafted = set()
    for recipe in recipes:
        crafted.add(recipe['result'])

    available = set()
    changed = True
    while changed:
        changed = False
        for recipe in recipes:
            ingredients = [x for x in recipe['grid'] if x]
            if all(x not in known_local or x in available for x in ingredients):
                if recipe['result'] not in available:
                    available.add(recipe['result'])
                    changed = True
    for result in sorted(crafted - available):
        add('warning', 'CRAFT_BOOTSTRAP',
            f'{result} has no crafting path from vanilla ingredients alone; it may still be obtainable through mining, loot or commands.', result)

    shapes = {}
    for recipe in recipes:
        slots = recipe['grid']
        if recipe.get('type', 'shaped') == 'shapeless':
            signature = ('shapeless', tuple(sorted(x for x in slots if x)))
        else:
            used = [(i//3,i%3) for i,v in enumerate(slots) if v]
            if not used: continue
            ys = [y for y,_ in used]
            xs = [x for _,x in used]
            signature = ('shaped', tuple(tuple(slots[y*3+x] for x in range(min(xs),max(xs)+1))
                                         for y in range(min(ys),max(ys)+1)))
        if signature in shapes:
            add('warning', 'RECIPE_CONFLICT',
                f'Recipes {shapes[signature]} and {recipe["id"]} have the same ingredients/layout; one may shadow the other.', recipe['id'])
        else:
            shapes[signature] = recipe['id']

    missing_ru = [f'{group[:-1]}:{obj["id"]}' for group in ('blocks','items')
                  for obj in request.get(group, []) if not obj.get('name_ru')]
    if missing_ru:
        add('info', 'RU_FALLBACK',
            f'{len(missing_ru)} entry name(s) use English as their Russian fallback.', 'translations')

    if request.get('structures'):
        add('info', 'STRUCTURE_PLACEMENT',
            'NBT templates are packaged, but automatic world placement requires separate compatible structure-set/pool configuration or commands.', 'structures')
    add('info', 'GAME_CHECK_REQUIRED',
        'Static checks passed. Official cargo horizon-mod check and a test in the running game are still required.', 'package')
    return {'ok': True, 'issues': issues,
            'stats': {'files': len(files), 'bytes': sum(map(len,files.values())),
                      'blocks': len(request.get('blocks', [])), 'items': len(request.get('items', [])),
                      'recipes': len(recipes), 'structures': len(request.get('structures', [])),
                      'craftable_from_vanilla': len(available)}}

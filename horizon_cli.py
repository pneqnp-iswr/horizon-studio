#!/usr/bin/env python3
"""Horizon Studio offline CLI for mod creators and CI workflows.

Uses exactly the same generator/validator as the visual editor. This is NOT the
official Horizon validator, nor does it launch the game.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from mod_doctor import audit_project
from studio import hmod_zip, project_zip, inspect_project

MAX_PROJECT_BYTES = 6 * 1024 * 1024


def load_project(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > MAX_PROJECT_BYTES:
        raise ValueError('Project file missing or larger than 6 MiB')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('format') != 'horizon-studio':
        raise ValueError('Expected a Horizon Studio .hstudio.json project')
    if data.get('schema') not in (2, 3, 4):
        raise ValueError('Unsupported Horizon Studio project schema')
    if not isinstance(data.get('metadata'), dict):
        raise ValueError('Missing project metadata')
    mod_id = data['metadata'].get('id')
    if not isinstance(mod_id, str):
        raise ValueError('Missing mod ID')
    result = {**data['metadata']}
    for group in ('blocks', 'items', 'recipes', 'structures'):
        entries = data.get(group, [])
        if not isinstance(entries, list):
            raise ValueError(f'{group} must be a list')
        result[group] = entries
    converted = []
    for recipe in result['recipes']:
        if not isinstance(recipe, dict) or not isinstance(recipe.get('grid'), list):
            raise ValueError('Invalid recipe')
        def convert(ref):
            return f'{mod_id}:{ref[1:]}' if isinstance(ref, str) and ref.startswith('@') else ref
        converted.append({**recipe, 'result': convert(recipe.get('result')),
                          'grid': [convert(cell) for cell in recipe['grid']]})
    result['recipes'] = converted
    return result


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='Horizon Studio offline builder and diagnostics (not official Horizon validation)')
    parser.add_argument('command', choices=('doctor','inspect','build','source'))
    parser.add_argument('project', type=Path, help='Project .hstudio.json file')
    parser.add_argument('-o','--output',type=Path,help='Destination for build/source')
    parser.add_argument('--json',action='store_true',help='Machine-readable diagnostics with doctor/inspect')
    args=parser.parse_args(argv)
    try:
        project=load_project(args.project)
        if args.command=='doctor':
            report=audit_project(project)
            if args.json: print(json.dumps(report,ensure_ascii=False,indent=2))
            else:
                for issue in report['issues']:
                    print(f"{issue['level'].upper():7s} {issue['code']}: {issue['message']}")
                print(f"Local validation: {'PASS' if report['ok'] else 'FAIL'}")
            return 0 if report['ok'] else 1
        if args.command=='inspect':
            report=inspect_project(project)
            if args.json: print(json.dumps(report,ensure_ascii=False,indent=2))
            else:
                print(report['manifest'])
                print('\n'.join(report['files']))
            return 0
        artifact = hmod_zip(project) if args.command=='build' else project_zip(project)
        filename = f"{project['id']}.hmod" if args.command=='build' else f"{project['id']}-source.zip"
        output=args.output or (Path('dist')/filename)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_bytes(artifact)
        print(f'Created {output} ({len(artifact)} bytes); run cargo horizon-mod check for official verification')
        return 0
    except (OSError,UnicodeError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main())

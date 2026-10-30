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
from horizon_compat.official_validator import check_hmod
from studio_core.graph import AssetGraph
from studio_core.migrate import source_schema, to_generator_request, upgrade
from studio_core.project_schema import SCHEMA, dumps
from studio_core.storage import atomic_write_bytes

MAX_PROJECT_BYTES = 6 * 1024 * 1024


def _read_json(path: Path):
    if not path.is_file() or path.stat().st_size > MAX_PROJECT_BYTES:
        raise ValueError('Project file missing or larger than 6 MiB')
    return json.loads(path.read_text(encoding='utf-8'))


def read_document(path: Path) -> dict:
    """Read any supported project file as a ``studio.project/1`` document."""
    return upgrade(_read_json(path))


def load_project(path: Path) -> dict:
    """The generator request for a project file (legacy schemas 2-4 or studio.project/1)."""
    return to_generator_request(read_document(path))


def write_migrated(source: Path, output: Path, force: bool) -> str:
    """Write ``source`` as studio.project/1; a backup is kept when migrating in place."""
    data = _read_json(source)
    original = source_schema(data)
    document = dumps(upgrade(data))
    if output.exists() and output.resolve() == source.resolve():
        if original == SCHEMA:
            return f'{source} is already {SCHEMA}; nothing to do'
        backup = source.with_name(f'{source.name}.schema{original}.bak')
        if backup.exists():
            raise ValueError(f'Backup {backup} already exists; move it away first')
        atomic_write_bytes(backup, source.read_bytes())
        atomic_write_bytes(output, document.encode('utf-8'))
        return f'Migrated {source} from schema {original} to {SCHEMA} (backup: {backup})'
    if output.exists() and not force:
        raise ValueError(f'{output} exists; pass --force to replace it')
    atomic_write_bytes(output, document.encode('utf-8'))
    return f'Wrote {output} ({SCHEMA}, from schema {original})'


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description='Horizon Studio offline builder and diagnostics (official checking is opt-in)')
    parser.add_argument('command', choices=('doctor','inspect','build','source','verify','migrate','graph','capabilities'))
    parser.add_argument('project', type=Path, help='Project .hstudio.json file (schema 2-4 or studio.project/1)')
    parser.add_argument('-o','--output',type=Path,help='Destination for build/source/migrate (migrate prints to stdout without it)')
    parser.add_argument('--force',action='store_true',help='migrate: replace an existing output file')
    parser.add_argument('--json',action='store_true',help='Machine-readable diagnostics with doctor/inspect/verify/graph')
    parser.add_argument('--validator-bin',default='cargo',help='Trusted cargo or cargo-horizon-mod executable path for verify')
    parser.add_argument('--direct-validator',action='store_true',help='Invoke cargo-horizon-mod directly, without cargo prefix')
    parser.add_argument('--validator-revision',help='Declared pinned validator source revision (40-digit SHA; not independently authenticated)')
    parser.add_argument('--timeout',type=float,default=120,help='Official checker timeout in seconds (verify only)')
    parser.add_argument('--evidence',type=Path,help='Write JSON official-check evidence for verify')
    args=parser.parse_args(argv)
    try:
        if args.command=='migrate':
            if args.output is None:
                sys.stdout.write(dumps(read_document(args.project)))
            else:
                print(write_migrated(args.project,args.output,args.force))
            return 0
        if args.command=='capabilities':
            from studio_core.capabilities import check
            report=check(read_document(args.project))
            if args.json: print(json.dumps(report,ensure_ascii=False,indent=2))
            else:
                profile=report['profile']
                print(f"Engine profile: {profile['label'] if profile else 'unknown'}")
                for capability,users in sorted(report['requirements'].items()):
                    print(f"  needs {capability:24s} {len(users)} object(s)")
                for issue in report['diagnostics']:
                    print(f"{issue['level'].upper():7s} {issue['code']}: {issue['message']}")
            return 1 if report['diagnostics'] else 0
        if args.command=='graph':
            graph=AssetGraph(read_document(args.project))
            report=graph.to_json()
            if args.json: print(json.dumps(report,ensure_ascii=False,indent=2))
            else:
                for edge in report['edges']:
                    print(f"{graph.label(edge['from'])} -> {graph.label(edge['to'])} ({edge['role']})")
                for issue in report['diagnostics']:
                    print(f"{issue['level'].upper():7s} {issue['code']}: {issue['message']}")
            return 1 if any(issue['level']=='error' for issue in report['diagnostics']) else 0
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
        if args.command=='verify':
            result=check_hmod(hmod_zip(project),cargo_binary=args.validator_bin,direct_binary=args.direct_validator,
                              timeout=args.timeout,declared_validator_revision=args.validator_revision)
            if args.evidence:
                args.evidence.parent.mkdir(parents=True,exist_ok=True)
                args.evidence.write_text(json.dumps(result.to_json(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            if args.json: print(json.dumps(result.to_json(),ensure_ascii=False,indent=2))
            else: print(f"Official .hmod check: {'PASS' if result.ok else 'FAIL'} (sha256 {result.sha256})"+
                        (f" — {result.error}" if result.error else ''))
            return 0 if result.ok else 1
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

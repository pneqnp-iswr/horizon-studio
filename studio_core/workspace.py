"""On-disk Studio workspace snapshots: optimistic revisions and crash recovery.

A project has one primary and one previous-known-good snapshot. No client
supplied filesystem paths are ever evaluated. A revision identifies serialized
canonical bytes, not a timestamp or last-writer-wins state.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import threading

from studio_core.migrate import upgrade
from studio_core.project_schema import dumps
from studio_core.storage import atomic_write_bytes

MAX_DOCUMENT_BYTES = 6 * 1024 * 1024
PROJECT_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
REVISION = re.compile(r"^[a-f0-9]{64}$")


class WorkspaceNotFound(ValueError):
    pass


class WorkspaceConflict(ValueError):
    pass


class WorkspaceCorrupt(ValueError):
    pass


class WorkspaceStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = threading.RLock()

    @staticmethod
    def _id(project_id: str) -> str:
        if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
            raise ValueError("Invalid workspace project ID")
        return project_id

    def paths(self, project_id: str) -> tuple[Path, Path]:
        project_id = self._id(project_id)
        # Fixed hash names prevent traversal and expose no raw project names.
        filename = hashlib.sha256(project_id.encode("utf-8")).hexdigest() + ".hstudio.json"
        primary = self.root / filename
        return primary, self.root / (filename + ".previous")

    @staticmethod
    def _digest(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()

    def _valid(self, path: Path, project_id: str):
        if not path.is_file():
            return None
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            return None
        try:
            raw = path.read_bytes()
            doc = upgrade(json.loads(raw.decode("utf-8")))
        except (OSError, UnicodeError, ValueError, TypeError):
            return None
        if doc["project"]["id"] != project_id:
            return None
        if dumps(doc).encode("utf-8") != raw:
            # Only canonical snapshots written by this store are accepted.
            return None
        return doc, raw

    def _read(self, project_id: str):
        primary, backup = self.paths(project_id)
        current = self._valid(primary, project_id)
        if current:
            return current, False
        previous = self._valid(backup, project_id)
        if previous:
            return previous, True
        if primary.exists() or backup.exists():
            raise WorkspaceCorrupt("No valid workspace snapshot or recovery copy")
        raise WorkspaceNotFound("No saved workspace exists for this project")

    def recover(self, project_id: str) -> dict:
        with self._lock:
            (doc, raw), used_backup = self._read(project_id)
            return {"document": doc, "revision": self._digest(raw),
                    "recovered_from_backup": used_backup}

    def save(self, document: dict, *, expected_revision: str | None) -> dict:
        doc = upgrade(document)
        project_id = self._id(doc["project"]["id"])
        if expected_revision is not None and (
            not isinstance(expected_revision, str) or not REVISION.fullmatch(expected_revision)
        ):
            raise ValueError("expected_revision must be a SHA-256 hex string or null")
        raw = dumps(doc).encode("utf-8")
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise ValueError("Workspace exceeds 6 MiB")
        primary, backup = self.paths(project_id)
        with self._lock:
            try:
                (old_doc, old_raw), used_backup = self._read(project_id)
                actual = self._digest(old_raw)
            except WorkspaceNotFound:
                old_raw = None
                actual = None
            # If the caller did not recover a pre-existing workspace,
            # its snapshot cannot silently overwrite someone's work.
            if actual != expected_revision:
                raise WorkspaceConflict("Workspace changed on disk; recover it before saving")
            # Every write keeps the last good document as a fallback; if the
            # primary was damaged, use the valid recovered fallback.
            if old_raw is not None and old_raw != raw:
                atomic_write_bytes(backup, old_raw)
            if old_raw != raw or used_backup:
                atomic_write_bytes(primary, raw)
            return {"project_id": project_id, "revision": self._digest(raw),
                    "recovered_from_backup": bool(old_raw is not None and used_backup)}

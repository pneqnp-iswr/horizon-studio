"""Run the official Horizon content-mod checker and verify its report.

This deliberately does NOT replace real-game testing or prove which
Git revision a locally installed executable was built from.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


@dataclass(frozen=True)
class OfficialCheckResult:
    stage: str
    ok: bool
    sha256: str
    size: int
    command: list[str]
    exit_code: int | None
    report: dict | None
    error: str | None
    declared_validator_revision: str | None = None

    def to_json(self) -> dict:
        return asdict(self)


def check_hmod(
    package: bytes, *, cargo_binary: str = "cargo",
    direct_binary: bool = False, timeout: float = 120,
    declared_validator_revision: str | None = None,
) -> OfficialCheckResult:
    """Run a trusted locally installed checker on a fresh temporary .hmod.

    `cargo_binary` is an explicit executable path (not a shell command).
    Set `direct_binary=True` for the `cargo-horizon-mod` executable.
    The declared revision is descriptive provenance, NOT a verified binary SHA.
    """
    if not isinstance(package, bytes) or not package:
        raise ValueError("A non-empty .hmod byte archive is required")
    if not isinstance(cargo_binary, str) or not cargo_binary.strip():
        raise ValueError("Validator executable path is required")
    if not 1 <= timeout <= 900:
        raise ValueError("Validator timeout must be 1..900 seconds")
    if declared_validator_revision is not None and not re.fullmatch(r"[0-9a-f]{40}", declared_validator_revision):
        raise ValueError("Declared validator revision must be a full 40-digit lowercase Git SHA")
    digest = hashlib.sha256(package).hexdigest()
    size = len(package)
    prefix = [cargo_binary] if direct_binary else [cargo_binary, "horizon-mod"]
    with tempfile.TemporaryDirectory(prefix="horizon-studio-official-") as folder:
        archive = Path(folder) / "studio-export.hmod"
        archive.write_bytes(package)
        command = prefix + ["check", str(archive), "--json"]
        try:
            completed = subprocess.run(
                command, check=False, text=True, capture_output=True,
                timeout=timeout, stdin=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return OfficialCheckResult("official", False, digest, size, command, None, None,
                                       "Official validator not installed or executable not found", declared_validator_revision)
        except subprocess.TimeoutExpired:
            return OfficialCheckResult("official", False, digest, size, command, None, None,
                                       "Official validator timed out", declared_validator_revision)
        except OSError as exc:
            return OfficialCheckResult("official", False, digest, size, command, None, None,
                                       f"Official validator could not start: {exc}", declared_validator_revision)
        try:
            output = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError, ValueError):
            return OfficialCheckResult("official", False, digest, size, command, completed.returncode, None,
                                       "Validator did not emit the expected JSON document", declared_validator_revision)
        if not isinstance(output, dict) or output.get("ok") is not True or completed.returncode != 0:
            error = output.get("error") if isinstance(output, dict) else None
            detail = str(error or completed.stderr.strip() or "Official validator rejected the mod")[:2000]
            return OfficialCheckResult("official", False, digest, size, command, completed.returncode,
                                       output if isinstance(output, dict) else None, detail, declared_validator_revision)
        report = output.get("report")
        if not isinstance(report, dict):
            return OfficialCheckResult("official", False, digest, size, command, completed.returncode, output,
                                       "Official success response has no report object", declared_validator_revision)
        if (report.get("sha256") != digest or report.get("size") != size
                or report.get("kind") != "mod" or report.get("api") != "0.2"):
            return OfficialCheckResult("official", False, digest, size, command, completed.returncode, output,
                                       "Validator report is inconsistent with generated .hmod bytes/API", declared_validator_revision)
        return OfficialCheckResult("official", True, digest, size, command, completed.returncode, output,
                                   None, declared_validator_revision)

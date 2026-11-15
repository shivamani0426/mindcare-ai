"""Safety checks for administrator-only backup utilities.

No live database connection, patient data, keys, or encrypted archives used.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKUP = ROOT / "scripts" / "backup_postgres.sh"
VERIFY = ROOT / "scripts" / "verify_postgres_backup.sh"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")
def test_private_backup_scripts_parse():
    for path in (BACKUP, VERIFY):
        result = subprocess.run(["bash", "-n", str(path)],
                                capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")
def test_backup_refuses_to_run_without_admin_connection(tmp_path):
    env = os.environ.copy()
    for key in ("PGHOST", "PGDATABASE", "PGUSER", "AGE_RECIPIENT", "PGPASSWORD"):
        env.pop(key, None)
    env["HOME"] = str(tmp_path)
    result = subprocess.run(["bash", str(BACKUP)], env=env,
                            capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "Set PGHOST" in result.stderr
    assert not list(tmp_path.glob("**/*.age"))


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")
def test_verifier_refuses_missing_archive_and_identity(tmp_path):
    result = subprocess.run([
        "bash", str(VERIFY), str(tmp_path / "missing.dump.age"),
        str(tmp_path / "missing.agekey"),
    ], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "missing" in result.stderr.lower()


def test_private_export_requirements_are_present():
    backup = BACKUP.read_text(encoding="utf-8")
    verifier = VERIFY.read_text(encoding="utf-8")
    assert "umask 077" in backup and "umask 077" in verifier
    assert "PGSSLMODE=require" in backup
    assert "pg_dump --format=custom" in backup
    assert "age --recipient" in backup
    assert "sha256sum --check" in backup
    assert "sha256sum --check" in verifier
    assert "pg_restore --list" in verifier
    assert "pg_restore --dbname" not in verifier

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.lab


def _restic(repo, *args):
    return subprocess.run(
        ["restic", "-r", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "RESTIC_PASSWORD": "lab-password",
            "RESTIC_FROM_PASSWORD": "lab-password",
        },
    )


def test_restic_backup_copy_and_check(tmp_path):
    if os.environ.get("HOMELAB_LAB") != "1":
        pytest.skip("defina HOMELAB_LAB=1")
    if not shutil.which("restic"):
        pytest.skip("restic ausente")

    source = tmp_path / "source"
    source.mkdir()
    (source / "documento.txt").write_text("conteudo")
    primary = tmp_path / "primary"
    cold = tmp_path / "cold"

    _restic(primary, "init")
    _restic(cold, "init")
    _restic(primary, "backup", str(source))
    snapshots = _restic(primary, "snapshots", "--json")
    assert "documento.txt" not in snapshots.stdout
    _restic(cold, "copy", "--from-repo", str(primary))
    _restic(cold, "check")
    restored = tmp_path / "restored"
    restored.mkdir()
    _restic(cold, "restore", "latest", "--target", str(restored))
    matches = list(restored.rglob("documento.txt"))
    assert matches
    assert matches[0].read_text() == "conteudo"

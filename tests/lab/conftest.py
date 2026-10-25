from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def _run(*args, check=True):
    return subprocess.run(
        list(args),
        check=check,
        capture_output=True,
        text=True,
    )


def lab_enabled() -> bool:
    return os.environ.get("HOMELAB_LAB") == "1" and os.geteuid() == 0


pytestmark = pytest.mark.lab


@pytest.fixture
def loop_factory(tmp_path):
    if not lab_enabled():
        pytest.skip("HOMELAB_LAB=1 e root sao necessarios")
    if not shutil.which("losetup"):
        pytest.skip("losetup ausente")
    created: list[str] = []

    def make(size_mb: int = 96) -> str:
        image = tmp_path / f"disk-{len(created)}.img"
        with image.open("wb") as handle:
            handle.truncate(size_mb * 1024 * 1024)
        result = _run("losetup", "--find", "--show", str(image))
        device = result.stdout.strip()
        created.append(device)
        return device

    yield make
    for device in reversed(created):
        _run("losetup", "-d", device, check=False)


@pytest.fixture
def mountpoint(tmp_path):
    path = tmp_path / "mnt"
    path.mkdir()
    return path


@pytest.fixture
def mounted():
    mounted: list[Path] = []

    def do(device: str, target: Path, fstype: str = "") -> Path:
        target.mkdir(parents=True, exist_ok=True)
        args = ["mount"]
        if fstype:
            args += ["-t", fstype]
        args += [device, str(target)]
        _run(*args)
        mounted.append(target)
        return target

    yield do
    for target in reversed(mounted):
        _run("umount", "-R", str(target), check=False)

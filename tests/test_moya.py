from __future__ import annotations

from .conftest import ROOT, parse_env_file


def test_moya_example_profile():
    values = parse_env_file(ROOT / "host.env.moya.example")
    assert values["BIND_ADDR"] == "127.0.0.1"
    assert values["ALLOWED_PATH_PREFIXES"] == "/mnt/data/"
    assert values["SNAPSHOT_DENYLIST"] == "Veronte_Images"
    assert values["SNAPSHOT_BACKEND"] == "rsync"
    assert values["DATA_DIR"] == "/mnt/data/apps/storage/data"
    assert values["DOWNLOAD_DIR"] == "/mnt/data/apps/storage/data/downloads"
    assert values["COMPOSE_OVERLAY"] == "docker-compose.moya.yml"
    assert values["SYSTEM_MANAGE"] == "1"
    assert values["TERMINAL_ENABLE"] == "1"


def test_moya_overlay_does_not_use_pi_paths_or_ip():
    text = (ROOT / "docker-compose.moya.yml").read_text(encoding="utf-8")
    assert "192.168.0.150" not in text
    assert "/srv/samba:/srv/samba:ro" not in text
    assert "/mnt/data:/mnt/data:ro" in text
    assert "/mnt/nas:/mnt/nas:ro" not in text


def test_homelab_overlay_still_reproduces_pi_paths():
    text = (ROOT / "docker-compose.homelab.yml").read_text(encoding="utf-8")
    assert "/mnt/nas:/mnt/nas:ro" in text
    assert "/run/homelab-storage-admin:/run/homelab-storage-admin:ro" in text


def test_readme_documents_profiles_and_neighbors():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    # O README aponta o TOML e o PRESETS; os overlays ficam no doc da area.
    assert "host.toml" in text
    assert "PRESETS.md" in text
    assert "Jellyfin" in text
    assert "Pi-hole" in text
    presets = (ROOT / "docs" / "PRESETS.md").read_text(encoding="utf-8")
    assert "docker-compose.homelab.yml" in presets
    assert "docker-compose.moya.yml" in presets

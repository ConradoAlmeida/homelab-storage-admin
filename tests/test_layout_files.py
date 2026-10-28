from __future__ import annotations

from pathlib import Path

from .conftest import ROOT, parse_env_file


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_generic_compose_has_no_pi_ip():
    text = read("docker-compose.yml")
    assert "192.168.0.150" not in text
    assert "BIND_ADDR" in text
    assert "AGENT_SOCKET" in text


def test_homelab_overlay_keeps_current_paths():
    text = read("docker-compose.homelab.yml")
    assert "/mnt/nas/apps/homelab-storage-admin/data:/app/data" in text
    assert "/mnt/nas:/mnt/nas:ro" in text
    assert "${JELLYFIN_ROOT:-/mnt/jellyfin}:${JELLYFIN_ROOT:-/mnt/jellyfin}:ro" in text
    assert "/run/homelab-storage-admin:/run/homelab-storage-admin:ro" in text


def test_host_env_example_is_pi_profile():
    values = parse_env_file(ROOT / "host.env.example")
    assert values["STORAGE_ROOT"] == "/mnt/nas"
    assert values["ALLOWED_PATH_PREFIXES"] == "/mnt/nas/"
    assert values["BIND_ADDR"] == "192.168.0.150"
    assert values["SNAPSHOT_BACKEND"] == "auto"
    assert values["COMPOSE_OVERLAY"] == "docker-compose.homelab.yml"


def test_metrics_timer_is_installed_and_daily():
    timer = read("agent/homelab-storage-metrics.timer")
    service = read("agent/homelab-storage-metrics.service")
    install = read("install-agent.sh")
    assert "OnCalendar=*-*-* 06:00:00" in timer
    assert "--collect" in service
    assert "homelab-storage-metrics.timer" in install


def test_install_agent_makes_btrfs_and_restic_optional():
    text = read("install-agent.sh")
    required_block = text.split("Checando dependencias obrigatorias", 1)[1].split(
        "Dependencias opcionais", 1
    )[0]
    assert "btrfs" not in required_block
    assert "restic" not in required_block
    optional_block = text.split("Dependencias opcionais", 1)[1]
    assert "btrfs" in optional_block
    assert "restic" in optional_block
    assert "host.env" in text
    assert "! -f \"$HOST_ENV\"" in text


def test_unit_uses_host_env_and_preserves_socket_name():
    text = read("agent/homelab-storage-agent.service")
    assert "EnvironmentFile=-/etc/homelab-storage-admin/host.env" in text
    assert "RuntimeDirectory=homelab-storage-admin" in text
    assert "Environment=STORAGE_ROOT" not in text


def test_pi_boot_unit_uses_host_env_and_overlay():
    text = read("deploy/pi/homelab-compose.service")
    assert "/etc/homelab-storage-admin/host.env" in text
    assert "COMPOSE_OVERLAY" in text
    assert "homelab-storage-admin" in text
    assert "ip -4 addr show | grep" in text
    assert "show dev wlan0" not in text


def test_pi_motd_points_to_storage_admin():
    text = read("deploy/pi/motd")
    assert "Storage admin:" in text
    assert "http://homelab.lan:8060/" in text


def test_deploy_loads_host_env_and_selected_overlay():
    text = read("deploy.sh")
    assert "/etc/homelab-storage-admin/host.env" in text
    assert "COMPOSE_OVERLAY" in text
    assert "docker-compose.homelab.yml" not in text
    assert 'docker compose "${COMPOSE_FILES[@]}" up -d --build' in text


def test_install_agent_selects_profile():
    text = read("install-agent.sh")
    assert "HOST_ENV_PROFILE" in text
    assert "host.env.moya.example" in text
    assert "host.env.example" in text


def test_templates_have_no_inline_css_or_js():
    for path in (ROOT / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert "<style" not in text, path
        assert "<script>" not in text, path
        assert 'style="' not in text, path
        assert "onclick=" not in text, path
        assert "onsubmit=" not in text, path


def test_static_assets_exist():
    assert (ROOT / "static" / "css" / "app.css").is_file()
    for name in (
        "confirm-actions.js",
        "copy-secret.js",
        "auto-refresh.js",
        "disk-wizard.js",
        "job-form.js",
        "live-metrics.js",
        "network-metrics.js",
        "share-sizes.js",
    ):
        assert (ROOT / "static" / "js" / name).is_file(), name

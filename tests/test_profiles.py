from __future__ import annotations

import importlib.util
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from core.forms import ShareCreateForm
from core.hostinfo import disk_role, disks_for_path, rotulo_discos, volume_for

from .conftest import ROOT, load_agent, set_env

SETTINGS_PATH = ROOT / "config" / "settings.py"


def load_settings(monkeypatch, values):
    set_env(monkeypatch, values)
    spec = importlib.util.spec_from_file_location("test_config_settings", SETTINGS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_defaults_are_the_pi_layout(monkeypatch):
    agent = load_agent(monkeypatch, {})
    assert agent.STORAGE_ROOT == "/mnt/nas"
    assert agent.SNAPSHOT_ROOT == "/mnt/nas/.snapshots"
    assert agent.ALLOWED_PATH_PREFIXES == ("/mnt/nas/",)
    assert agent.DF_MOUNTS == ("/", "/mnt/nas")
    assert agent.BACKUP_ROOT == "/mnt/backup"
    assert agent.SHARE_OWNER == "conrado"
    assert agent.SNAPSHOT_BACKEND == "auto"
    assert agent.DENY_SNAPSHOT == set()


def test_pi_profile_fixture_matches_defaults(profile_env):
    pi = profile_env["pi"]
    assert pi["STORAGE_ROOT"] == "/mnt/nas"
    assert pi["SNAPSHOT_ROOT"] == "/mnt/nas/.snapshots"
    assert pi["ALLOWED_PATH_PREFIXES"] == "/mnt/nas/"
    assert pi["BIND_ADDR"] == "192.168.0.150"
    assert pi["BIND_PORT"] == "8060"
    assert pi["COMPOSE_OVERLAY"] == "docker-compose.homelab.yml"


def test_moya_profile(profile_env):
    moya = profile_env["moya"]
    assert moya["ALLOWED_PATH_PREFIXES"].split(",") == ["/srv/samba/", "/mnt/data/"]
    assert moya["BIND_ADDR"] == "127.0.0.1"
    assert moya["SNAPSHOT_DENYLIST"] == "Veronte_Images"
    assert moya["SNAPSHOT_BACKEND"] == "rsync"
    assert moya["COMPOSE_OVERLAY"] == "docker-compose.moya.yml"


def test_minimal_profile_has_no_optional_backend(profile_env):
    minimal = profile_env["minimal"]
    assert minimal["SNAPSHOT_BACKEND"] == "none"
    assert minimal["ALLOWED_PATH_PREFIXES"] == "/srv/samba/"


def test_django_settings_read_environment(monkeypatch, profile_env):
    settings_module = load_settings(monkeypatch, profile_env["moya"])
    assert settings_module.SITE_NAME == "Moya Storage"
    assert settings_module.STORAGE_ROOT == "/srv/samba"
    assert settings_module.BACKUP_ROOT == "/mnt/data/backups"
    assert settings_module.ALLOWED_PATH_PREFIXES == ("/srv/samba/", "/mnt/data/")
    assert settings_module.BIND_ADDR == "127.0.0.1"
    assert settings_module.SNAPSHOT_DENYLIST == ("Veronte_Images",)


def test_share_form_help_uses_first_allowed_prefix():
    with override_settings(ALLOWED_PATH_PREFIXES=("/srv/samba/", "/mnt/data/")):
        form = ShareCreateForm()
    assert "/srv/samba/pasta" in form.fields["path"].help_text


def test_share_form_aceita_pasta_no_disco_jellyfin_montado(monkeypatch):
    monkeypatch.setattr("core.paths.os.path.ismount", lambda path: path == "/mnt/jellyfin")
    with override_settings(
        ALLOWED_PATH_PREFIXES=("/mnt/nas/",),
        JELLYFIN_ROOT="/mnt/jellyfin",
    ):
        form = ShareCreateForm(
            {"name": "fotos", "path": "/mnt/jellyfin/fotos", "snapshot_keep": "7"}
        )
        assert form.is_valid(), form.errors
        assert "/mnt/jellyfin/pasta" in form.fields["path"].help_text


def test_share_form_recusa_jellyfin_sem_mount(monkeypatch):
    monkeypatch.setattr("core.paths.os.path.ismount", lambda path: False)
    with override_settings(
        ALLOWED_PATH_PREFIXES=("/mnt/nas/",),
        JELLYFIN_ROOT="/mnt/jellyfin",
    ):
        form = ShareCreateForm(
            {"name": "fotos", "path": "/mnt/jellyfin/fotos", "snapshot_keep": "7"}
        )
        assert not form.is_valid()
        assert "permitido" in str(form.errors)


class DiskRoleTests(SimpleTestCase):
    def test_system_disk_by_mount_not_by_name(self):
        assert disk_role({"name": "mmcblk0", "mounts": ["/"]}, "/mnt/nas", "/mnt/backup") == "sistema"
        assert disk_role({"name": "sda", "mounts": ["/", "/boot"]}, "/mnt/nas", "/mnt/backup") == "sistema"

    def test_data_and_backup_roles(self):
        assert disk_role({"mounts": ["/mnt/nas"]}, "/mnt/nas", "/mnt/backup") == "dados/RAID"
        assert disk_role({"mounts": ["/mnt/backup/hdd700"]}, "/mnt/nas", "/mnt/backup") == "backup"
        assert disk_role({"mounts": ["/mnt/other"]}, "/mnt/nas", "/mnt/backup") == "—"

    def test_disco_do_share_prefere_o_mount_mais_especifico(self):
        sistema = {"name": "sda", "model": "ST2000NM012B-2TD", "mounts": ["/", "/mnt/backup"]}
        espelho_a = {"name": "sdb", "model": "WDC WD40EFZZ-68C", "mounts": ["/mnt/data"]}
        espelho_b = {"name": "sdc", "model": "WDC WD40EFZZ-68C", "mounts": ["/mnt/data"]}
        discos = [espelho_b, sistema, espelho_a]
        assert disks_for_path("/srv/samba/print_files", discos) == [sistema]
        assert disks_for_path("/mnt/data/Veronte_Images", discos) == [espelho_a, espelho_b]
        assert rotulo_discos([sistema]) == "Disco sda · ST2000NM012B-2TD"
        assert (
            rotulo_discos([espelho_a, espelho_b])
            == "Discos sdb + sdc · WDC WD40EFZZ-68C"
        )

    def test_volume_for_prefers_most_specific_mount(self):
        volumes = [
            {"mount": "/", "total": 100},
            {"mount": "/mnt/nas", "total": 200},
        ]
        assert volume_for("/mnt/nas/docs", volumes)["mount"] == "/mnt/nas"
        assert volume_for("/etc", volumes)["mount"] == "/"

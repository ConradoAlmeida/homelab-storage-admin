from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

import backups.views as backup_views
import core.context_processors as context_processors
import core.views as core_views
import storage.views as storage_views
from core.services import DEFAULT_COLOR, load_services

from .conftest import ROOT
from .test_views import fake_agent


def write_ini(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "services.ini"
    path.write_text(text)
    return path


def test_loads_and_sorts_services(tmp_path):
    path = write_ini(
        tmp_path,
        "[zeta]\n"
        "name = Zeta\n"
        "url = https://zeta.example/\n"
        "order = 20\n"
        "\n"
        "[alfa]\n"
        "name = Alfa\n"
        "description = Primeiro\n"
        "url = http://alfa.example/\n"
        "icon = pihole\n"
        "color = #123abc\n"
        "order = 10\n",
    )
    services = load_services(path)
    assert [service.key for service in services] == ["alfa", "zeta"]
    assert services[0].description == "Primeiro"
    assert services[0].color == "#123abc"
    assert services[0].icon == "pihole"


def test_invalid_url_is_skipped_and_invalid_color_falls_back(tmp_path):
    path = write_ini(
        tmp_path,
        "[inseguro]\n"
        "url = javascript:alert(1)\n"
        "\n"
        "[sem-host]\n"
        "url = http:///sem-host\n"
        "\n"
        "[valido]\n"
        "url = https://ok.example/\n"
        "color = vermelho\n"
        "order = nao-e-numero\n",
    )
    services = load_services(path)
    assert [service.key for service in services] == ["valido"]
    assert services[0].color == DEFAULT_COLOR
    assert services[0].order == 100


def test_missing_file_is_empty(tmp_path):
    assert load_services(tmp_path / "nao-existe.ini") == []


def test_example_has_current_pi_services():
    services = load_services(ROOT / "services.ini.example")
    assert [service.key for service in services] == [
        "jellyfin",
        "cockpit",
        "dockge",
        "pihole",
    ]


class ServiceRenderTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="services-tester", password="test-password"
        )
        self.client.force_login(self.user)
        fake = fake_agent()
        for module in (core_views, storage_views, backup_views, context_processors):
            patcher = patch.object(module, "agent", fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        context_processors._cached_caps = None
        context_processors._cached_at = 0.0

    def test_dashboard_renders_configured_services(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_ini(
                Path(directory),
                "[jellyfin]\n"
                "name = Jellyfin\n"
                "url = http://jellyfin.example/\n"
                "icon = jellyfin\n",
            )
            with self.settings(SERVICES_FILE=str(path)):
                response = self.client.get("/")
        self.assertContains(response, "Jellyfin")
        self.assertContains(response, 'href="http://jellyfin.example/"')

    def test_dashboard_omits_services_when_file_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.settings(SERVICES_FILE=str(Path(directory) / "missing.ini")):
                response = self.client.get("/")
        self.assertNotContains(response, "Jellyfin")

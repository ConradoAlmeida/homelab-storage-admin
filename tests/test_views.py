from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

import backups.views as backup_views
import core.context_processors as context_processors
import core.views as core_views
import storage.views as storage_views
from core.agent import AgentError
from core.models import AuditLog


def fake_agent(capabilities=None):
    agent = Mock()
    agent.df.return_value = {"volumes": []}
    agent.list_shares.return_value = []
    agent.list_users.return_value = []
    agent.list_groups.return_value = []
    agent.snapshot_usage.return_value = []
    agent.refresh_storage.return_value = {"disks": []}
    agent.live_metrics.return_value = {
        "system": {
            "zones": [{"type": "cpu_thermal", "temp": 35.0}],
            "fans": [],
            "load": {"l1": 0.1, "l5": 0.2, "l15": 0.3},
            "cpu_percent": 5.0,
            "mem_total_mb": 1024,
            "mem_available_mb": 512,
        },
        "collected_at": "2026-10-26T23:00:00",
    }
    agent.backup_snapshots.return_value = {"snapshots": [], "errors": []}
    agent.backup_ls.return_value = {
        "snapshot_id": "a" * 64,
        "path": "/mnt/nas",
        "parent": "/mnt",
        "snapshot": {},
        "entries": [],
    }
    agent.backup_search.return_value = {
        "snapshot_id": "a" * 64,
        "query": "",
        "matches": [],
        "total": 0,
        "truncated": False,
    }
    agent.storage_overview.return_value = {
        "system": {
            "zones": [],
            "fans": [],
            "load": {"l1": 0, "l5": 0, "l15": 0},
            "cpu_percent": None,
            "mem_total_mb": 1024,
            "mem_available_mb": 512,
        },
        "disks": [],
        "raid": {"mdstat": "", "detail": ""},
        "btrfs": {"usage": "", "stats": "", "scrub": ""},
    }
    agent.backup_overview.return_value = {
        "disks": [],
        "jobs": [],
        "restic": False,
    }
    agent.cold_overview.return_value = {
        "disks": [],
        "restic": False,
        "primary": {},
        "primary_error": "",
        "config": None,
        "status": {},
    }
    agent.host_capabilities.return_value = capabilities or {
        "btrfs": False,
        "restic": False,
        "smartctl": False,
        "hdparm": False,
        "mdadm": False,
        "hwmon_fans": False,
        "storage_root_mounted": False,
        "storage_root_fstype": "ext4",
        "snapshot_backend": "none",
    }
    return agent


class ViewSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="test-password"
        )
        self.client.force_login(self.user)
        fake = fake_agent()
        self.fake = fake
        for module in (core_views, storage_views, backup_views, context_processors):
            patcher = patch.object(module, "agent", fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        context_processors._cached_caps = None
        context_processors._cached_at = 0.0

    def test_dashboard_renders_without_optional_capabilities(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "restic não encontrado")
        self.fake.list_shares.assert_any_call(include_size=False)
        self.fake.snapshot_usage.assert_any_call(include_size=False)

    def test_storage_renders_without_btrfs_or_smartctl(self):
        response = self.client.get("/storage/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Btrfs")

    def test_storage_refresh_triggers_agent(self):
        response = self.client.post("/storage/refresh/")
        self.assertRedirects(response, "/storage/")
        self.fake.refresh_storage.assert_called_once_with()

    def test_backups_renders_empty_state_without_restic(self):
        response = self.client.get("/backups/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "restic não encontrado")

    def test_restic_snapshots_page_renders(self):
        response = self.client.get("/backups/snapshots/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nenhum snapshot restic encontrado")

    def test_nav_hides_backups_without_restic(self):
        response = self.client.get("/")
        self.assertNotContains(response, 'href="/backups/"')

    def test_restic_snapshot_browser_lists_files(self):
        self.fake.backup_ls.return_value = {
            "snapshot_id": "a" * 64,
            "path": "/mnt/nas",
            "parent": "/mnt",
            "snapshot": {
                "short_id": "aaaaaaaa",
                "time": "2026-10-26T22:15:24-03:00",
                "hostname": "homelab",
                "paths": ["/mnt/nas"],
                "tags": ["homelab"],
            },
            "entries": [
                {
                    "name": "casa",
                    "path": "/mnt/nas/casa",
                    "type": "dir",
                    "size": None,
                    "mtime": "2026-10-25T22:37:27-03:00",
                    "permissions": "drwxrwxr-x",
                },
                {
                    "name": "a.txt",
                    "path": "/mnt/nas/a.txt",
                    "type": "file",
                    "size": 12,
                    "mtime": "2026-10-25T22:37:27-03:00",
                    "permissions": "-rw-r--r--",
                },
            ],
        }
        response = self.client.get(
            "/backups/snapshots/aaaaaaaa/browse/?disk_uuid=u1&path=/mnt/nas"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "casa")
        self.assertContains(response, "a.txt")
        self.assertContains(response, "Baixar")
        self.assertContains(response, "2026-10-26T22:15:24-03:00")
        self.assertContains(response, "2026-10-25T22:37:27-03:00")
        self.fake.backup_ls.assert_called_once_with("u1", "aaaaaaaa", "/mnt/nas")

    def test_restic_snapshot_search_lists_matches(self):
        self.fake.backup_search.return_value = {
            "snapshot_id": "a" * 64,
            "query": "README",
            "pattern": "*README*",
            "total": 2,
            "truncated": False,
            "matches": [
                {
                    "name": "README.md",
                    "path": "/mnt/nas/casa/README.md",
                    "parent": "/mnt/nas/casa",
                    "type": "file",
                    "size": 12,
                    "mtime": "2026-10-25T22:37:27-03:00",
                    "permissions": "-rw-r--r--",
                },
                {
                    "name": "Docs",
                    "path": "/mnt/nas/Docs",
                    "parent": "/mnt/nas",
                    "type": "dir",
                    "size": None,
                    "mtime": "2026-10-25T22:37:27-03:00",
                    "permissions": "drwxr-xr-x",
                },
            ],
        }
        response = self.client.get(
            "/backups/snapshots/aaaaaaaa/browse/"
            "?disk_uuid=u1&path=/mnt/nas&q=README"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resultados para")
        self.assertContains(response, "/mnt/nas/casa/README.md")
        self.assertContains(response, "Baixar")
        self.assertContains(response, "Abrir pasta")
        self.assertContains(response, "Abrir")
        self.fake.backup_search.assert_called_once_with("u1", "aaaaaaaa", "README")

    def test_restic_snapshot_download_serves_file_and_audits(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            target = data_dir / "downloads" / "token" / "a.txt"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"conteudo")
            self.fake.backup_download.return_value = {
                "relative": "downloads/token/a.txt",
                "filename": "a.txt",
                "size": 8,
            }
            with self.settings(DATA_DIR=data_dir):
                response = self.client.get(
                    "/backups/snapshots/aaaaaaaa/download/"
                    "?disk_uuid=u1&path=/mnt/nas/a.txt"
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"conteudo")
            self.assertEqual(response["Content-Disposition"], 'attachment; filename="a.txt"')
        self.assertTrue(
            AuditLog.objects.filter(
                action="backup_snapshot_download", target="aaaaaaaa"
            ).exists()
        )

    def test_falha_ao_salvar_grupos_mostra_o_motivo(self):
        self.fake.list_groups.return_value = ["cnc", "teste2"]
        self.fake.list_users.return_value = [
            {"username": "teste2", "groups": ["teste2"], "enabled": True, "fullname": ""}
        ]
        self.fake.set_groups.side_effect = AgentError("Usuario nao existe: teste2")
        response = self.client.post(
            "/usuarios/grupos/?username=teste2",
            {"username": "teste2", "groups": ["cnc", "teste2"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Não foi possível concluir")
        self.assertContains(response, "Usuario nao existe: teste2")

    def test_group_create_posts_to_agent_and_audits(self):
        self.fake.create_group.return_value = {"name": "equipe", "gid": 1500}
        response = self.client.post(
            "/usuarios/grupos/novo/",
            {"name": "equipe", "gid": "1500"},
        )
        self.assertRedirects(response, "/usuarios/")
        self.fake.create_group.assert_called_once_with("equipe", 1500)
        self.assertTrue(
            AuditLog.objects.filter(action="group.create", target="equipe").exists()
        )

    def test_cbv_pages_render(self):
        paths = [
            "/usuarios/",
            "/usuarios/novo/",
            "/usuarios/grupos/novo/",
            "/usuarios/senha/?username=tester",
            "/usuarios/grupos/?username=tester",
            "/shares/",
            "/shares/novo/",
            "/snapshots/",
            "/backups/",
            "/backups/snapshots/",
            "/backups/credentials/",
            "/backups/jobs/new/",
            "/backups/cold/",
            "/storage/",
            "/history/",
        ]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, path)

    def test_share_create_cbv_posts_to_agent(self):
        self.fake.create_share.return_value = {"name": "docs"}
        response = self.client.post(
            "/shares/novo/",
            {
                "name": "docs",
                "path": "/mnt/nas/docs",
                "comment": "teste",
                "snapshot": "on",
                "snapshot_keep": "7",
            },
        )
        self.assertRedirects(response, "/shares/")
        self.fake.create_share.assert_called_once()
        self.assertTrue(
            AuditLog.objects.filter(action="share.create", target="docs").exists()
        )

    def test_live_metrics_endpoint_returns_hardware_only(self):
        response = self.client.get("/metrics/live/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["system"]["cpu_percent"], 5.0)
        self.assertNotIn("disks", response.json())
        self.fake.live_metrics.assert_called_once_with()

    def test_share_sizes_endpoint_returns_lazy_payload(self):
        self.fake.list_shares.return_value = [
            {
                "name": "docs",
                "size": 100,
                "size_snapshots": 20,
                "size_total": 120,
            }
        ]
        response = self.client.get("/metrics/shares/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "shares": [
                    {
                        "name": "docs",
                        "size": 100,
                        "size_snapshots": 20,
                        "size_total": 120,
                    }
                ]
            },
        )

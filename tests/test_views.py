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
from core.models import AuditLog


def fake_agent(capabilities=None):
    agent = Mock()
    agent.df.return_value = {"volumes": []}
    agent.list_shares.return_value = []
    agent.list_users.return_value = []
    agent.list_groups.return_value = []
    agent.snapshot_usage.return_value = []
    agent.refresh_storage.return_value = {"disks": []}
    agent.backup_snapshots.return_value = {"snapshots": [], "errors": []}
    agent.backup_ls.return_value = {
        "snapshot_id": "a" * 64,
        "path": "/mnt/nas",
        "parent": "/mnt",
        "snapshot": {},
        "entries": [],
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
        self.assertContains(response, "2026-10-25T22:37:27-03:00")
        self.fake.backup_ls.assert_called_once_with("u1", "aaaaaaaa", "/mnt/nas")

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

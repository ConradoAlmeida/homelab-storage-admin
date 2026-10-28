from __future__ import annotations

import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

import backups.views as backup_views
import core.context_processors as context_processors
from core.models import AuditLog
from tests.test_views import fake_agent

OVERVIEW = {
    "container": "gitea",
    "running": True,
    "volume": "/var/lib/docker/volumes/moya-gitea_gitea_data/_data",
    "volume_size": "4.4G",
    "backup_dir": "/var/backups/gitea",
    "keep": 2,
    "dumps": [
        {
            "name": "gitea-20261028-113707.zip",
            "size": 3972844748,
            "size_label": "3.7 GB",
            "created_label": "28/10/2026 11:37",
        }
    ],
    "status": {
        "status": "done",
        "stage": "done",
        "target": "host",
        "size_label": "3.7 GB",
        "finished_at": "2026-10-28T11:37:01",
    },
    "usb": [
        {
            "name": "sdb",
            "path": "/dev/sdb",
            "size": "32G",
            "model": "USB DISK",
            "serial": "123",
            "tran": "usb",
            "fstype": "ext4",
            "label": "GITEA",
            "mountpoint": None,
            "free": None,
            "free_label": "-",
            "has_filesystem": True,
            "partitions": [],
        }
    ],
}


class GiteaBackupViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="test-password"
        )
        self.client.force_login(self.user)
        fake = fake_agent()
        fake.gitea_overview.return_value = OVERVIEW
        fake.gitea_start.return_value = {"target": "host", "started": True}
        self.fake = fake
        patcher = patch.object(backup_views, "agent", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        context_processors._cached_caps = {
            "restic": True,
            "credenciais_backup": True,
        }
        context_processors._cached_at = time.monotonic()

    def test_pagina_mostra_estado_e_usb(self):
        resposta = self.client.get("/backups/gitea/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Backup do Gitea")
        self.assertContains(resposta, "gitea-20261028-113707.zip")
        self.assertContains(resposta, "sdb")
        self.assertContains(resposta, "Backup para USB")

    def test_dump_no_servidor(self):
        resposta = self.client.post(
            "/backups/gitea/start/",
            data={"target": "host"},
            follow=True,
        )
        self.assertContains(resposta, "Backup do Gitea iniciado")
        self.fake.gitea_start.assert_called_once_with("host")
        self.assertTrue(
            AuditLog.objects.filter(action="gitea_backup_start").exists()
        )

    def test_backup_para_usb(self):
        resposta = self.client.post(
            "/backups/gitea/start/",
            data={"target": "sdb"},
            follow=True,
        )
        self.assertContains(resposta, "USB sdb")
        self.fake.gitea_start.assert_called_once_with("sdb")

    def test_sem_usb_mostra_orientacao(self):
        self.fake.gitea_overview.return_value = {**OVERVIEW, "usb": []}
        resposta = self.client.get("/backups/gitea/")
        self.assertContains(resposta, "Nenhum drive USB detectado")

    def test_erro_do_agente_aparece(self):
        self.fake.gitea_start.side_effect = backup_views.AgentError(
            "Disco USB nao encontrado"
        )
        resposta = self.client.post(
            "/backups/gitea/start/",
            data={"target": "sdz"},
            follow=True,
        )
        self.assertContains(resposta, "Disco USB nao encontrado")

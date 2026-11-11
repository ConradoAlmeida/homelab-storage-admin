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
    "schedule": {
        "enabled": False,
        "frequency": "daily",
        "time": "05:00",
        "weekday": 0,
        "monthday": 1,
        "on_calendar": "",
        "label": "desligada",
        "next_run": None,
    },
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
            "gitea": True,
        }
        context_processors._cached_at = time.monotonic()

    def test_escopo_do_moya_mantem_gitea_e_arquivos(self):
        self.fake.arquivos_jobs.return_value = {
            "dir": "/var/backups/moya-credenciais",
            "jobs": [],
        }
        resposta = self.client.get("/backups/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(
            resposta, "Backups locais, do Gitea e repositórios restic."
        )
        self.assertContains(resposta, "Backup do Gitea")
        self.assertContains(resposta, "Backup de arquivos")
        pagina = self.client.get("/backups/gitea/")
        self.assertEqual(pagina.status_code, 200)

    def test_pagina_mostra_agenda(self):
        resposta = self.client.get("/backups/gitea/")
        self.assertContains(resposta, "Agenda")
        self.assertContains(resposta, "05:00")
        self.assertContains(resposta, "Salvar agenda")

    def test_pagina_mostra_estado_e_usb(self):
        resposta = self.client.get("/backups/gitea/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Backup do Gitea")
        self.assertContains(resposta, "gitea-20261028-113707.zip")
        self.assertContains(resposta, "Restaurar")
        self.assertContains(resposta, "Baixar")
        self.assertContains(resposta, "/var/backups/gitea")
        self.assertContains(resposta, "sdb")
        self.assertContains(resposta, "Backup para USB")

    def test_status_copiando_avisa_para_nao_desconectar(self):
        self.fake.gitea_overview.return_value = {
            **OVERVIEW,
            "status": {
                "status": "running",
                "stage": "copy",
                "target": "sdb",
                "size_label": "3.7 GB",
            },
        }
        resposta = self.client.get("/backups/gitea/")
        self.assertContains(resposta, "NÃO desconecte o drive USB")
        self.assertContains(resposta, "copiando para o USB")
        self.assertNotContains(resposta, "Cópia no USB verificada")
        self.assertContains(resposta, "data-gitea-status")

    def test_status_verificando_nao_parece_concluido(self):
        self.fake.gitea_overview.return_value = {
            **OVERVIEW,
            "status": {
                "status": "running",
                "stage": "verify",
                "target": "sdb",
                "size_label": "3.7 GB",
            },
        }
        resposta = self.client.get("/backups/gitea/")
        self.assertContains(resposta, "verificando o hash")
        self.assertContains(resposta, "NÃO desconecte o drive USB")
        self.assertNotContains(resposta, "Cópia no USB verificada")

    def test_falha_de_usb_mostra_mensagem_amigavel(self):
        self.fake.gitea_overview.return_value = {
            **OVERVIEW,
            "status": {
                "status": "failed",
                "stage": "verify",
                "size_label": "3.7 GB",
                "error": "[Errno 5] Input/output error: '/mnt/gitea-usb/sdb/gitea/x.zip'",
            },
        }
        resposta = self.client.get("/backups/gitea/")
        self.assertContains(resposta, "O drive USB desconectou ou falhou")
        self.assertContains(resposta, "O dump no servidor foi gerado e está íntegro")
        self.assertContains(resposta, "gitea-error-raw")

    def test_endpoint_de_status_entrega_json(self):
        resposta = self.client.get("/backups/gitea/status/")
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.json()
        self.assertEqual(dados["status"]["status"], "done")
        self.assertEqual(dados["dumps"][0]["name"], "gitea-20261028-113707.zip")
        self.assertTrue(dados["running"])

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

    def test_lista_diz_o_disco_do_diretorio(self):
        self.fake.storage_overview.return_value = {
            "disks": [
                {
                    "name": "sda",
                    "model": "ST2000NM012B-2TD",
                    "mounts": ["/", "/mnt/backup"],
                }
            ]
        }
        resposta = self.client.get("/backups/gitea/")
        self.assertContains(resposta, "Disco sda · ST2000NM012B-2TD")

    def test_download_entrega_o_zip_e_audita(self):
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            alvo = data_dir / "downloads" / "token" / "gitea-20261028-113707.zip"
            alvo.parent.mkdir(parents=True)
            alvo.write_bytes(b"zip")
            self.fake.gitea_download.return_value = {
                "relative": "downloads/token/gitea-20261028-113707.zip",
                "filename": "gitea-20261028-113707.zip",
                "size": 3,
            }
            with self.settings(DATA_DIR=data_dir):
                resposta = self.client.get(
                    "/backups/gitea/gitea-20261028-113707.zip/download/"
                )
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(b"".join(resposta.streaming_content), b"zip")
        self.fake.gitea_download.assert_called_once_with("gitea-20261028-113707.zip")
        self.assertTrue(AuditLog.objects.filter(action="gitea_download").exists())

    def test_restore_exige_confirmacao(self):
        resposta = self.client.post(
            "/backups/gitea/gitea-20261028-113707.zip/restore/",
            {"confirmation": "outro.zip"},
            follow=True,
        )
        self.fake.gitea_restore.assert_not_called()
        self.assertContains(resposta, "digite o nome do dump")

    def test_restore_audita(self):
        self.fake.gitea_restore.return_value = {
            "started": True,
            "task": "gitearestore-abcd1234",
            "status": "running",
        }
        resposta = self.client.post(
            "/backups/gitea/gitea-20261028-113707.zip/restore/",
            {"confirmation": "gitea-20261028-113707.zip"},
            follow=True,
        )
        self.assertContains(resposta, "Trabalho iniciado")
        self.assertContains(resposta, "data-task-poll")
        self.fake.gitea_restore.assert_called_once_with(
            "gitea-20261028-113707.zip", confirmation="gitea-20261028-113707.zip"
        )
        self.assertTrue(AuditLog.objects.filter(action="gitea_restore").exists())

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

    def test_salvar_agenda_ativa_audita(self):
        self.fake.gitea_schedule_save.return_value = {
            "enabled": True,
            "frequency": "daily",
            "time": "05:00",
        }
        resposta = self.client.post(
            "/backups/gitea/schedule/",
            data={
                "enabled": "1",
                "frequency": "daily",
                "time": "05:00",
                "weekday": "0",
                "monthday": "1",
            },
            follow=True,
        )
        self.fake.gitea_schedule_save.assert_called_once_with(
            enabled=True,
            frequency="daily",
            time="05:00",
            weekday=0,
            monthday=1,
        )
        self.assertContains(resposta, "Agenda do dump do Gitea salva")
        self.assertTrue(
            AuditLog.objects.filter(action="gitea_schedule_save").exists()
        )

    def test_erro_na_agenda_aparece(self):
        self.fake.gitea_schedule_save.side_effect = backup_views.AgentError(
            "Horario invalido; use HH:MM"
        )
        resposta = self.client.post(
            "/backups/gitea/schedule/",
            data={
                "frequency": "daily",
                "time": "25:00",
                "weekday": "0",
                "monthday": "1",
            },
            follow=True,
        )
        self.assertContains(resposta, "Horario invalido")

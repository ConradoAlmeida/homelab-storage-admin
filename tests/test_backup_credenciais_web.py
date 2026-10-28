from __future__ import annotations

import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

import backups.views as backup_views
import core.context_processors as context_processors
from core.agent import AgentError
from core.models import AuditLog
from tests.test_views import fake_agent

ARQUIVO = "moya-credenciais-20261027-033000.tar.gz"

OVERVIEW = {
    "available": True,
    "config": {
        "time": "03:30",
        "retention_days": 30,
        "db": "/home/conrado/moya_credenciais_app/data/db.sqlite3",
        "env": "/home/conrado/moya_credenciais_app/.env",
        "dir": "/var/backups/moya-credenciais",
        "container": "moya-credenciais",
    },
    "sources": [
        {
            "name": "Banco SQLite",
            "path": "/home/conrado/moya_credenciais_app/data/db.sqlite3",
            "ok": True,
            "size": "164.0 KB",
        },
        {
            "name": "Variaveis de ambiente",
            "path": "/home/conrado/moya_credenciais_app/.env",
            "ok": True,
            "size": "563 B",
        },
    ],
    "status": {
        "ok": True,
        "started_at": "2026-10-27T03:30:00",
        "finished_at": "2026-10-27T03:30:01",
        "duration_seconds": 0.6,
        "size_label": "20.0 KB",
        "archive": ARQUIVO,
    },
    "archives": [
        {
            "name": ARQUIVO,
            "size_bytes": 20480,
            "size": "20.0 KB",
            "created_at": "2026-10-27T03:30:00",
            "created_label": "27/10/2026 03:30",
            "age_days": 0,
        }
    ],
    "next_run": "2026-10-28T03:30",
    "timer": "active",
}


class ArquivosBackupViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="test-password"
        )
        self.client.force_login(self.user)
        fake = fake_agent()
        fake.arquivos_backup_overview.return_value = OVERVIEW
        fake.arquivos_backup_run.return_value = {
            "archive": ARQUIVO,
            "size_label": "20.0 KB",
        }
        fake.backup_overview.return_value = {"restic": False, "disks": [], "jobs": []}
        fake.arquivos_backup_add_file.return_value = {
            "files": ["/home/conrado/app.conf"]
        }
        fake.arquivos_backup_remove_file.return_value = {"files": []}
        fake.arquivos_backup_verify.return_value = {
            "archive": ARQUIVO,
            "integrity": "ok",
            "hashes_ok": True,
            "files": [".env", "db.sqlite3"],
        }
        fake.arquivos_backup_restore.return_value = {
            "archive": ARQUIVO,
            "integrity": "ok",
            "security_copy": "/var/backups/moya-credenciais/pre-restore-20261027-040000",
            "restarted": True,
        }
        self.fake = fake
        patcher = patch.object(backup_views, "agent", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        context_processors._cached_caps = {
            "restic": False,
            "credenciais_backup": True,
        }
        context_processors._cached_at = time.monotonic()

    def test_indice_mostra_o_job_local(self):
        resposta = self.client.get("/backups/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Backup local de arquivos")
        self.assertContains(resposta, "Credenciais")
        self.assertContains(resposta, "diário 03:30")

    def test_incluir_arquivo_individual(self):
        resposta = self.client.post(
            "/backups/arquivos/files/add/",
            data={"path": "/home/conrado/app.conf"},
            follow=True,
        )
        self.assertContains(resposta, "passa a entrar")
        self.fake.arquivos_backup_add_file.assert_called_once_with(
            "/home/conrado/app.conf"
        )
        self.assertTrue(
            AuditLog.objects.filter(action="credenciais_backup_add_file").exists()
        )

    def test_remover_arquivo_individual(self):
        resposta = self.client.post(
            "/backups/arquivos/files/remove/",
            data={"path": "/home/conrado/app.conf"},
            follow=True,
        )
        self.assertContains(resposta, "sai do proximo backup")
        self.fake.arquivos_backup_remove_file.assert_called_once_with(
            "/home/conrado/app.conf"
        )

    def test_incluir_arquivo_mostra_erro_do_agente(self):
        self.fake.arquivos_backup_add_file.side_effect = AgentError(
            "Use um caminho absoluto"
        )
        resposta = self.client.post(
            "/backups/arquivos/files/add/",
            data={"path": "relativo.conf"},
            follow=True,
        )
        self.assertContains(resposta, "Use um caminho absoluto")

    def test_salvar_agendamento(self):
        self.fake.arquivos_backup_settings.return_value = {
            "time": "04:15",
            "frequency": "weekly",
            "weekday": 2,
            "retention_days": 60,
        }
        resposta = self.client.post(
            "/backups/arquivos/settings/",
            data={
                "time": "04:15",
                "frequency": "weekly",
                "weekday": "2",
                "retention_days": "60",
            },
            follow=True,
        )
        self.assertContains(resposta, "Agendamento atualizado")
        self.fake.arquivos_backup_settings.assert_called_once_with(
            time="04:15",
            frequency="weekly",
            weekday="2",
            retention_days="60",
        )
        self.assertTrue(
            AuditLog.objects.filter(action="credenciais_backup_settings").exists()
        )

    def test_pagina_mostra_fonte_job_e_arquivo(self):
        resposta = self.client.get("/backups/arquivos/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Backup local de arquivos")
        self.assertContains(resposta, ARQUIVO)
        self.assertContains(resposta, "Banco SQLite")
        self.assertContains(resposta, "diário 03:30")

    def test_rodar_agora_aciona_o_agente(self):
        resposta = self.client.post("/backups/arquivos/run/")
        self.assertRedirects(resposta, "/backups/arquivos/")
        self.fake.arquivos_backup_run.assert_called_once_with()
        self.assertTrue(
            AuditLog.objects.filter(action="arquivos_backup_run").exists()
        )

    def test_verificar_mostra_sucesso(self):
        resposta = self.client.post(
            f"/backups/arquivos/{ARQUIVO}/verify/", follow=True
        )
        self.assertContains(resposta, "banco íntegro")
        self.fake.arquivos_backup_verify.assert_called_once_with(ARQUIVO)

    def test_restaurar_exige_confirmacao_exata(self):
        resposta = self.client.post(
            f"/backups/arquivos/{ARQUIVO}/restore/",
            data={"confirmation": "errado"},
            follow=True,
        )
        self.assertContains(resposta, "digite o nome do arquivo")
        self.fake.arquivos_backup_restore.assert_not_called()

    def test_restaurar_com_confirmacao_reinicia(self):
        resposta = self.client.post(
            f"/backups/arquivos/{ARQUIVO}/restore/",
            data={"confirmation": ARQUIVO, "restart": "1"},
            follow=True,
        )
        self.assertContains(resposta, "restaurado")
        self.fake.arquivos_backup_restore.assert_called_once_with(
            ARQUIVO, restart=True
        )
        self.assertTrue(
            AuditLog.objects.filter(action="arquivos_backup_restore").exists()
        )

    def test_erro_do_agente_aparece_como_mensagem(self):
        self.fake.arquivos_backup_run.side_effect = AgentError("sem permissao")
        resposta = self.client.post(
            "/backups/arquivos/run/", follow=True
        )
        self.assertContains(resposta, "sem permissao")

    def test_download_entrega_o_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "downloads" / "abc"
            destino.mkdir(parents=True)
            arquivo = destino / ARQUIVO
            arquivo.write_bytes(b"conteudo")
            self.fake.arquivos_backup_download.return_value = {
                "relative": f"downloads/abc/{ARQUIVO}",
                "filename": ARQUIVO,
                "size": 8,
            }
            with self.settings(DATA_DIR=pasta):
                resposta = self.client.get(
                    f"/backups/arquivos/{ARQUIVO}/download/"
                )
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta["Content-Disposition"].split(";")[0], "attachment")
            self.assertEqual(b"".join(resposta.streaming_content), b"conteudo")

    def test_nav_mostra_backups_com_backup_do_credenciais(self):
        resposta = self.client.get("/")
        self.assertContains(resposta, 'href="/backups/"')

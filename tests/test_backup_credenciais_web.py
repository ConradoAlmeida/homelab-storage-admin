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

ARQUIVO = "credenciais-20261028-033000.tar.gz"

JOB_CRED = {
    "name": "credenciais",
    "label": "Credenciais",
    "enabled": True,
    "time": "03:30",
    "frequency": "daily",
    "weekday": 0,
    "retention_days": 30,
    "sources": [
        {"kind": "sqlite", "path": "/home/conrado/moya_credenciais_app/data/db.sqlite3"},
        {"kind": "env", "path": "/home/conrado/moya_credenciais_app/.env"},
    ],
}

JOB_DOCS = {
    "name": "documentos",
    "label": "Documentos",
    "enabled": True,
    "time": "05:00",
    "frequency": "weekly",
    "weekday": 4,
    "retention_days": 12,
    "sources": [{"kind": "auto", "path": "/home/conrado/documentos"}],
}

STATUS = {
    "ok": True,
    "status": "success",
    "started_at": "2026-10-28T03:30:00",
    "finished_at": "2026-10-28T03:30:01",
    "duration_seconds": 0.6,
    "size_label": "20.0 KB",
    "archive": ARQUIVO,
}

ARQUIVOS = [
    {
        "name": ARQUIVO,
        "size_bytes": 20480,
        "size": "20.0 KB",
        "created_at": "2026-10-28T03:30:00",
        "created_label": "28/10/2026 03:30",
        "age_days": 0,
    }
]

OVERVIEW = {
    "dir": "/var/backups/moya-credenciais",
    "container": "moya-credenciais",
    "jobs": [
        {
            "name": "credenciais",
            "label": "Credenciais",
            "enabled": True,
            "agenda": "diário 03:30",
            "retention_days": 30,
            "next_run": "2026-10-29T03:30",
            "timer": "active",
            "sources": JOB_CRED["sources"],
            "status": STATUS,
            "archives": [ARQUIVOS[0]],
            "archives_count": 1,
        },
        {
            "name": "documentos",
            "label": "Documentos",
            "enabled": True,
            "agenda": "semanal (sexta) 05:00",
            "retention_days": 12,
            "next_run": "2026-10-30T05:00",
            "timer": "active",
            "sources": JOB_DOCS["sources"],
            "status": {},
            "archives": [],
            "archives_count": 0,
        },
    ],
}

DETALHE = {
    "job": JOB_CRED,
    "dir": "/var/backups/moya-credenciais",
    "usb": [
        {
            "name": "sdb",
            "path": "/dev/sdb",
            "model": "USB DISK",
            "fstype": "ext4",
            "label": "GITEA",
            "free_label": "20G",
            "has_filesystem": True,
        }
    ],
    "sources": [
        {
            "name": "db.sqlite3",
            "path": "/home/conrado/moya_credenciais_app/data/db.sqlite3",
            "kind": "Banco",
            "ok": True,
            "size": "164.0 KB",
        },
        {
            "name": ".env",
            "path": "/home/conrado/moya_credenciais_app/.env",
            "kind": "Ambiente",
            "ok": True,
            "size": "563 B",
        },
    ],
    "status": STATUS,
    "archives": ARQUIVOS,
    "next_run": "2026-10-29T03:30",
    "agenda": "diário 03:30",
    "timer": "active",
}


class ArquivosJobViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="test-password"
        )
        self.client.force_login(self.user)
        fake = fake_agent()
        fake.backup_overview.return_value = {"restic": False, "disks": [], "jobs": []}
        fake.arquivos_jobs.return_value = OVERVIEW
        fake.arquivos_job.return_value = DETALHE
        fake.arquivos_job_save.return_value = DETALHE
        fake.arquivos_job_run.return_value = {"name": "credenciais", "started": True}
        fake.arquivos_sugestoes.return_value = {
            "sources": ["/mnt/data/datasheets", "/home/conrado/caddy"]
        }
        fake.arquivos_job_usb_backup.return_value = {
            "job": "apps",
            "archive": "apps-20261028-130000.tar.gz",
            "size_label": "104 MB",
            "device": "sdb",
            "verified": True,
        }
        fake.arquivos_job_delete.return_value = {"name": "credenciais", "deleted": True}
        fake.arquivos_job_verify.return_value = {
            "archive": ARQUIVO,
            "integrity": "ok",
            "hashes_ok": True,
            "files": [".env", "db.sqlite3"],
        }
        fake.arquivos_job_restore.return_value = {
            "archive": ARQUIVO,
            "integrity": "ok",
            "security_copy": "/var/backups/moya-credenciais/pre-restore-20261028-040000",
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

    def test_lista_de_jobs(self):
        resposta = self.client.get("/backups/arquivos/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Credenciais")
        self.assertContains(resposta, "Documentos")
        self.assertContains(resposta, "diário 03:30")
        self.assertContains(resposta, "semanal (sexta) 05:00")
        self.assertContains(resposta, "Novo job")

    def test_lista_atualiza_sozinha_com_job_rodando(self):
        rodando = {
            **OVERVIEW,
            "jobs": [
                {**OVERVIEW["jobs"][0], "status": {"status": "running"}},
                OVERVIEW["jobs"][1],
            ],
        }
        self.fake.arquivos_jobs.return_value = rodando
        resposta = self.client.get("/backups/arquivos/")
        self.assertContains(resposta, 'data-status="running"')

    def test_indice_mostra_os_jobs(self):
        resposta = self.client.get("/backups/")
        self.assertContains(resposta, "Backups locais de arquivos")
        self.assertContains(resposta, "Credenciais")
        self.assertContains(resposta, "Documentos")
        self.assertContains(resposta, "/backups/arquivos/")

    def test_formulario_novo(self):
        resposta = self.client.get("/backups/arquivos/new/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Novo job de backup")
        self.assertContains(resposta, 'name="sources"')

    def test_modelo_de_apps_preenche_as_fontes(self):
        resposta = self.client.get("/backups/arquivos/new/?modelo=apps")
        self.assertContains(resposta, 'value="apps"')
        self.assertContains(resposta, "/mnt/data/datasheets")
        self.assertContains(resposta, "Dados dos apps")

    def test_backup_do_job_para_usb(self):
        resposta = self.client.post(
            "/backups/arquivos/apps/usb/",
            data={"device": "sdb"},
            follow=True,
        )
        self.assertContains(resposta, "copiado para sdb")
        self.assertContains(resposta, "verificado")
        self.fake.arquivos_job_usb_backup.assert_called_once_with("apps", "sdb")

    def test_formulario_edicao_traz_as_fontes(self):
        resposta = self.client.get("/backups/arquivos/credenciais/edit/")
        self.assertContains(resposta, "Editar job de backup")
        self.assertContains(resposta, "/home/conrado/moya_credenciais_app/data/db.sqlite3")

    def test_criar_job_com_fontes(self):
        resposta = self.client.post(
            "/backups/arquivos/new/",
            data={
                "name": "documentos",
                "label": "Documentos",
                "sources": "/home/conrado/documentos\n/etc/algum/arquivo.conf",
                "frequency": "weekly",
                "weekday": "4",
                "time": "05:00",
                "retention_days": "12",
                "enabled": "1",
            },
            follow=True,
        )
        self.assertContains(resposta, "salvo")
        dados = self.fake.arquivos_job_save.call_args.args[0]
        self.assertEqual(dados["name"], "documentos")
        self.assertEqual(
            [item["path"] for item in dados["sources"]],
            ["/home/conrado/documentos", "/etc/algum/arquivo.conf"],
        )
        self.assertEqual(dados["frequency"], "weekly")
        self.assertTrue(
            AuditLog.objects.filter(action="arquivos_job_save").exists()
        )

    def test_erro_ao_salvar_mostra_mensagem(self):
        self.fake.arquivos_job_save.side_effect = AgentError("Caminho nao encontrado")
        resposta = self.client.post(
            "/backups/arquivos/new/",
            data={
                "name": "documentos",
                "label": "Documentos",
                "sources": "/nao/existe",
                "frequency": "daily",
                "weekday": "0",
                "time": "05:00",
                "retention_days": "12",
                "enabled": "1",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Caminho nao encontrado")

    def test_rodar_agora(self):
        resposta = self.client.post(
            "/backups/arquivos/credenciais/run/", follow=True
        )
        self.assertContains(resposta, "Backup iniciado")
        self.fake.arquivos_job_run.assert_called_once_with("credenciais")

    def test_excluir_job(self):
        resposta = self.client.post(
            "/backups/arquivos/documentos/delete/", follow=True
        )
        self.assertRedirects(resposta, "/backups/arquivos/")
        self.fake.arquivos_job_delete.assert_called_once_with("documentos")

    def test_verificar_mostra_sucesso(self):
        resposta = self.client.post(
            f"/backups/arquivos/credenciais/{ARQUIVO}/verify/", follow=True
        )
        self.assertContains(resposta, "banco íntegro")
        self.fake.arquivos_job_verify.assert_called_once_with("credenciais", ARQUIVO)

    def test_restaurar_exige_confirmacao_exata(self):
        resposta = self.client.post(
            f"/backups/arquivos/credenciais/{ARQUIVO}/restore/",
            data={"confirmation": "errado"},
            follow=True,
        )
        self.assertContains(resposta, "digite o nome do arquivo")
        self.fake.arquivos_job_restore.assert_not_called()

    def test_restaurar_com_confirmacao_reinicia(self):
        resposta = self.client.post(
            f"/backups/arquivos/credenciais/{ARQUIVO}/restore/",
            data={"confirmation": ARQUIVO, "restart": "1"},
            follow=True,
        )
        self.assertContains(resposta, "restaurado")
        self.fake.arquivos_job_restore.assert_called_once_with(
            "credenciais", ARQUIVO, restart=True
        )
        self.assertTrue(
            AuditLog.objects.filter(action="arquivos_job_restore").exists()
        )

    def test_download_entrega_o_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "downloads" / "abc"
            destino.mkdir(parents=True)
            arquivo = destino / ARQUIVO
            arquivo.write_bytes(b"conteudo")
            self.fake.arquivos_job_download.return_value = {
                "relative": f"downloads/abc/{ARQUIVO}",
                "filename": ARQUIVO,
                "size": 8,
            }
            with self.settings(DATA_DIR=pasta):
                resposta = self.client.get(
                    f"/backups/arquivos/credenciais/{ARQUIVO}/download/"
                )
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(b"".join(resposta.streaming_content), b"conteudo")

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
    agent.health_overview.return_value = {
        "alerts": [],
        "volumes": [],
        "ok": True,
    }
    agent.network_overview.return_value = {
        "interfaces": [],
        "routes": [],
        "listening": [],
        "containers": [],
        "firewall": "inativo",
        "rules": [],
    }
    agent.containers_overview.return_value = {
        "runtime": "docker",
        "containers": [],
        "error": "",
    }
    agent.container_action.return_value = {
        "name": "teste",
        "action": "stop",
        "message": "",
    }
    agent.container_logs.return_value = {
        "name": "teste",
        "tail": 200,
        "logs": "linha de log",
        "runtime": "docker",
    }
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

    def test_dashboard_lista_jobs_de_arquivos(self):
        capacidades = dict(self.fake.host_capabilities.return_value)
        capacidades["credenciais_backup"] = True
        self.fake.host_capabilities.return_value = capacidades
        context_processors._cached_caps = None
        context_processors._cached_at = 0.0
        self.fake.arquivos_jobs.return_value = {
            "dir": "/var/backups/moya-credenciais",
            "jobs": [
                {
                    "name": "credenciais",
                    "label": "Credenciais",
                    "enabled": True,
                    "agenda": "diário 03:30",
                    "retention_days": 30,
                    "next_run": "2026-10-29T03:30",
                    "sources": [{"name": "banco"}],
                    "status": {
                        "status": "success",
                        "ok": True,
                        "finished_at": "2026-10-28T09:51:06",
                    },
                    "archives": [],
                    "archives_count": 7,
                }
            ],
        }
        response = self.client.get("/")
        self.assertContains(response, "Backup de arquivos")
        self.assertContains(response, "Credenciais")
        self.assertContains(response, "diário 03:30")
        self.assertNotContains(response, "Nenhum job de backup ainda")

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

    def test_excluir_usuario_chama_o_agente_e_avisa_se_falhar(self):
        response = self.client.post("/usuarios/excluir/", {"username": "teste2"})
        self.assertRedirects(response, "/usuarios/")
        self.fake.delete_user.assert_called_once_with("teste2")
        self.assertTrue(
            AuditLog.objects.filter(action="user.delete", target="teste2").exists()
        )

        self.fake.delete_user.side_effect = AgentError("Usuario protegido: conrado")
        response = self.client.post(
            "/usuarios/excluir/", {"username": "conrado"}, follow=True
        )
        self.assertContains(response, "Usuario protegido: conrado")

    def test_excluir_grupo_chama_o_agente(self):
        response = self.client.post("/usuarios/grupos/excluir/", {"name": "cnc"})
        self.assertRedirects(response, "/usuarios/")
        self.fake.delete_group.assert_called_once_with("cnc")
        self.assertTrue(
            AuditLog.objects.filter(action="group.delete", target="cnc").exists()
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

    def test_backup_check_chama_o_agente(self):
        self.fake.backup_check.return_value = {
            "ok": True,
            "finished_at": "2026-10-28T04:30:00",
        }
        resposta = self.client.post(
            "/backups/disks/check/", data={"uuid": "abc"}, follow=True
        )
        self.assertContains(resposta, "Repositorio integro")
        self.fake.backup_check.assert_called_once_with("abc")

    def test_dashboard_mostra_saude(self):
        resposta = self.client.get("/")
        self.assertContains(resposta, "Saúde")
        self.assertContains(resposta, "tudo ok")

    def test_rede_renderiza(self):
        resposta = self.client.get("/rede/")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Rede e firewall")
        self.assertContains(resposta, "UFW")
        self.assertContains(resposta, "Portas ouvindo")

    def test_rede_coloca_rota_e_regra_em_tabela(self):
        self.fake.network_overview.return_value = {
            "interfaces": [],
            "routes": [
                "default via 192.168.0.1 dev eth0 proto dhcp src 192.168.0.10 metric 100"
            ],
            "listening": [],
            "containers": [],
            "firewall": "ativo",
            "rules": [
                "New profiles: skip",
                "To                         Action      From",
                "--                         ------      ----",
                "22/tcp                     ALLOW IN    Anywhere",
            ],
        }
        resposta = self.client.get("/rede/")
        self.assertContains(resposta, "192.168.0.1")
        self.assertContains(resposta, "eth0")
        self.assertContains(resposta, "192.168.0.10")
        self.assertContains(resposta, "22/tcp")
        self.assertContains(resposta, "ALLOW IN")
        self.assertNotContains(resposta, "<pre")
        self.assertNotContains(resposta, "New profiles")

    def test_saude_usa_linha_com_pilula(self):
        self.fake.health_overview.return_value = {
            "alerts": [
                {"level": "warn", "title": "Disco cheio", "detail": "/mnt em 91%"}
            ],
            "volumes": [],
            "ok": False,
        }
        resposta = self.client.get("/")
        self.assertContains(resposta, "Disco cheio")
        self.assertContains(resposta, "/mnt em 91%")
        self.assertContains(resposta, "health-row")
        self.assertContains(resposta, "Nível")
        self.assertNotContains(resposta, "health-list")

    def test_usuarios_lista_grupos_em_tabela(self):
        self.fake.list_users.return_value = [
            {
                "username": "ana",
                "fullname": "Ana",
                "groups": ["midia"],
                "enabled": True,
            }
        ]
        self.fake.list_groups.return_value = ["ana", "midia"]
        resposta = self.client.get("/usuarios/")
        self.assertContains(resposta, "Grupos de share")
        self.assertContains(resposta, "Novo grupo")
        self.assertContains(resposta, "midia")
        self.assertNotContains(resposta, 'class="chip"')

    def test_discos_omite_uso_e_dump_do_dashboard(self):
        capacidades = dict(self.fake.host_capabilities.return_value)
        capacidades["smartctl"] = True
        self.fake.host_capabilities.return_value = capacidades
        context_processors._cached_caps = None
        context_processors._cached_at = 0.0
        self.fake.df.return_value = {
            "volumes": [
                {
                    "mount": "/mnt/nas",
                    "total": 1000,
                    "used": 100,
                    "free": 900,
                    "percent": 10,
                }
            ]
        }
        self.fake.storage_overview.return_value = {
            "collected_at": "2026-10-28T06:00:00",
            "stale": False,
            "disks": [
                {
                    "name": "sda",
                    "path": "/dev/sda",
                    "model": "Test",
                    "serial": "ABC",
                    "size": "1T",
                    "state": "active/idle",
                    "mounts": ["/mnt/nas"],
                    "fstype": "ext4",
                    "smart": {
                        "temperature": 30,
                        "health": "PASSED",
                        "state": "ok",
                    },
                }
            ],
            "raid": {"mdstat": "md0 : active", "detail": ""},
            "btrfs": {"usage": "Data,single", "stats": "", "scrub": ""},
        }
        resposta = self.client.get("/storage/")
        self.assertContains(resposta, "sda")
        self.assertContains(resposta, "Ler SMART")
        self.assertNotContains(resposta, "md0 : active")
        self.assertNotContains(resposta, "Data,single")
        self.assertNotContains(resposta, "livres")

    def test_containers_renderiza(self):
        self.fake.containers_overview.return_value = {
            "runtime": "docker",
            "error": "",
            "containers": [
                {
                    "name": "gitea",
                    "id": "abc123",
                    "image": "gitea/gitea",
                    "state": "running",
                    "status": "Up 2 hours",
                    "running": True,
                    "health": "healthy",
                    "restart_count": 0,
                    "project": "gitea",
                    "service": "server",
                    "ports": ["127.0.0.1:3000->3000/tcp"],
                },
                {
                    "name": "antigo",
                    "id": "def456",
                    "image": "alpine",
                    "state": "exited",
                    "status": "Exited (0) 2 days ago",
                    "running": False,
                    "health": "",
                    "restart_count": 0,
                    "project": "",
                    "service": "",
                    "ports": [],
                },
            ],
        }
        resposta = self.client.get("/containers/")
        self.assertContains(resposta, "gitea")
        self.assertContains(resposta, "127.0.0.1:3000")
        self.assertContains(resposta, "Parar")
        self.assertContains(resposta, "Reiniciar")
        self.assertContains(resposta, "Iniciar")
        self.assertContains(resposta, "Logs")

    def test_container_action_chama_agente_e_audita(self):
        resposta = self.client.post(
            "/containers/acao/", {"name": "gitea", "action": "stop"}
        )
        self.assertRedirects(resposta, "/containers/")
        self.fake.container_action.assert_called_once_with("gitea", "stop")
        self.assertTrue(
            AuditLog.objects.filter(action="container.stop", target="gitea").exists()
        )

    def test_container_action_invalida_nao_chama_agente(self):
        self.client.post(
            "/containers/acao/", {"name": "gitea", "action": "rm"}
        )
        self.fake.container_action.assert_not_called()

    def test_container_logs_renderiza(self):
        resposta = self.client.get(
            "/containers/logs/", {"name": "gitea", "tail": "100"}
        )
        self.assertContains(resposta, "linha de log")
        self.fake.container_logs.assert_called_once_with("gitea", 100)

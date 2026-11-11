from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

import backups.views as backup_views
import core.context_processors as context_processors
import core.downloads as core_downloads
import core.system_views as system_views_module
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
    agent.firewall_overview.return_value = {
        "installed": True,
        "active": False,
        "status": "inativo",
        "policies": {"incoming": "deny", "outgoing": "allow", "routed": "deny"},
        "rules": [],
        "ssh_allowed": True,
        "error": "",
    }
    agent.firewall_enable.return_value = agent.firewall_overview.return_value
    agent.firewall_disable.return_value = agent.firewall_overview.return_value
    agent.firewall_add_rule.return_value = agent.firewall_overview.return_value
    agent.firewall_delete_rule.return_value = agent.firewall_overview.return_value
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
        "apt": False,
        "journal": False,
        "systemctl": False,
        "system_manage": True,
        "terminal_enable": False,
    }
    agent.host_info.return_value = {
        "hostname": "test",
        "friendly_name": "",
        "system": "Test OS",
        "kernel": "1.0",
        "datetime": "2026-01-01 00:00:00",
    }
    agent.ssh_keys.return_value = {"keys": []}
    agent.journal.return_value = {"lines": [], "count": 0}
    agent.systemd_list_units.return_value = {"units": []}
    agent.apt_check.return_value = {"started": True, "task": "aptcheck-abcdef12", "status": "running"}
    agent.apt_upgrade.return_value = {"started": True, "task": "aptupgrade-abcd1234", "status": "running"}
    return agent


class ViewSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="test-password"
        )
        self.client.force_login(self.user)
        fake = fake_agent()
        self.fake = fake
        for module in (
            core_views,
            core_downloads,
            storage_views,
            backup_views,
            context_processors,
        ):
            patcher = patch.object(module, "agent", fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.qbit = Mock()
        self.qbit.estado.return_value = (
            {"available": False, "version": "", "reason": ""},
            [],
            "",
        )
        qbit_patch = patch.object(core_downloads, "qbittorrent", self.qbit)
        qbit_patch.start()
        self.addCleanup(qbit_patch.stop)
        context_processors._cached_caps = None
        context_processors._cached_at = 0.0

    def test_dashboard_mostra_uso_por_fatia(self):
        self.fake.storage_overview.return_value = {
            "collected_at": "2026-11-10T06:00:00",
            "stale": False,
            "disks": [
                {
                    "name": "sda",
                    "path": "/dev/sda",
                    "size": "2T",
                    "model": "ST2000NM012B-2TD",
                    "serial": "ABC",
                    "state": "active/idle",
                    "smart": {"temperature": 32, "health": "PASSED"},
                    "parts": [
                        {
                            "name": "sda1",
                            "size": "512M",
                            "fstype": "vfat",
                            "mounts": ["/boot/efi"],
                            "usages": [
                                {
                                    "mount": "/boot/efi",
                                    "total": 500_000_000,
                                    "used": 100_000_000,
                                    "free": 400_000_000,
                                    "percent": 20.0,
                                }
                            ],
                        },
                        {
                            "name": "data-lv",
                            "size": "1.5T",
                            "fstype": "ext4",
                            "mounts": ["/mnt/backup"],
                            "usages": [
                                {
                                    "mount": "/mnt/backup",
                                    "total": 1_500_000_000_000,
                                    "used": 300_000_000_000,
                                    "free": 1_200_000_000_000,
                                    "percent": 20.0,
                                }
                            ],
                        },
                    ],
                }
            ],
            "raid": {"mdstat": "", "detail": ""},
            "btrfs": {"usage": "", "stats": "", "scrub": ""},
            "system": {},
        }
        resposta = self.client.get("/")
        self.assertNotContains(resposta, "sem FS")
        self.assertContains(resposta, "/mnt/backup")
        self.assertContains(resposta, "data-lv")
        self.assertContains(resposta, "vfat")

    def test_dashboard_mostra_resync_do_mdstat(self):
        self.fake.storage_overview.return_value["raid"] = {
            "mdstat": "md0 : active raid1\n      [==>..]  resync = 32.0%",
            "detail": "",
        }
        resposta = self.client.get("/")
        self.assertContains(resposta, "resync = 32.0%")
        self.assertContains(resposta, "RAID sincronizando")

    def test_dashboard_renders_without_optional_capabilities(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "restic não encontrado")
        self.assertNotContains(response, 'href="/torrents/"')
        self.assertContains(response, "images/conradhub/sidebar-wordmark.png")
        self.assertContains(response, 'width="178"')
        self.assertContains(response, 'height="54"')
        self.assertContains(response, 'alt="Conrado Homelab"')
        self.assertNotContains(response, "object-view-box")
        self.assertContains(response, "Visão geral")
        self.assertContains(response, "Dados")
        self.assertContains(response, "Sistema")
        self.assertContains(response, 'class="ico"')
        self.assertNotContains(response, 'href="/containers/"')
        self.assertNotContains(response, 'href="/backups/"')
        self.assertNotContains(response, 'class="count"')
        self.assertContains(response, "images/conradhub/apple-touch-icon.png")
        self.assertContains(response, "images/conradhub/site.webmanifest")
        self.assertNotContains(response, "images/conrado/")
        self.assertNotContains(response, "moya_wordmark_official.svg")
        self.assertNotContains(response, "brand-moya")
        self.fake.list_shares.assert_any_call(include_size=False)
        self.fake.snapshot_usage.assert_any_call(include_size=False)

    def test_login_e_favicon_usam_a_marca_do_homelab(self):
        self.client.logout()
        login = self.client.get("/login/")
        self.assertContains(login, "images/conradhub/wordmark.png")
        self.assertContains(login, 'width="1800"')
        self.assertContains(login, 'height="650"')
        self.assertContains(login, 'alt="Conradhub Homelab"')
        self.assertNotContains(login, "images/conrado/")
        self.assertNotContains(login, "login-house.png")
        self.assertContains(login, "images/conradhub/favicon-32.png")
        icone = self.client.get("/favicon.ico")
        self.assertRedirects(
            icone,
            "/static/images/conradhub/favicon.ico",
            fetch_redirect_response=False,
        )

    @override_settings(CREDENTIALS_MANAGE_USERS=True)
    def test_moya_mantem_o_wordmark_proprio(self):
        response = self.client.get("/")
        self.assertContains(response, "moya_wordmark_official.svg")
        self.assertContains(response, 'alt="Moya"')
        self.assertContains(response, 'class="brand-moya"')
        self.assertNotContains(response, "images/conradhub/")
        self.assertNotContains(response, "images/conrado/")
        icone = self.client.get("/favicon.ico")
        self.assertRedirects(
            icone,
            "/static/images/favicon.ico",
            fetch_redirect_response=False,
        )

    def _liga_jellyfin(self):
        capacidades = dict(self.fake.host_capabilities.return_value)
        capacidades["jellyfin"] = True
        self.fake.host_capabilities.return_value = capacidades
        context_processors._cached_caps = None
        context_processors._cached_at = 0.0

    @override_settings(TORRENT_API_TOKEN="")
    def test_torrents_somem_sem_jellyfin_e_aparecem_com_ele(self):
        self.assertRedirects(self.client.get("/torrents/"), "/")
        self._liga_jellyfin()
        self.fake.torrent_overview.return_value = {
            "libraries": [
                {"id": "filmes", "name": "Filmes", "path": "/mnt/jellyfin/filmes"}
            ],
            "libraries_error": "",
        }
        self.qbit.estado.return_value = (
            {"available": True, "version": "v5.0.1", "reason": ""},
            [
                {
                    "hash": "a" * 40,
                    "name": "Filme",
                    "progress_label": "10%",
                    "state": "downloading",
                    "state_label": "baixando",
                    "speed": "1 MB/s",
                    "eta": "5 min",
                    "size": "1 GB",
                    "library": "Filmes",
                    "active": True,
                    "can_pause": True,
                    "can_resume": False,
                }
            ],
            "",
        )
        resposta = self.client.get("/torrents/")
        self.assertContains(resposta, "Filmes")
        self.assertContains(resposta, "Pausar")
        self.assertContains(resposta, "Download")
        self.assertNotContains(resposta, 'data-sort="upload"')
        self.assertContains(resposta, "Apagar os arquivos deste torrent")
        self.assertContains(resposta, "Adicionar torrent")
        self.assertContains(resposta, "Configurar API")
        self.assertContains(resposta, 'id="torrent-panel-add"')
        self.assertContains(resposta, 'id="torrent-panel-organizar"')
        self.assertContains(resposta, 'for="torrent-panel-organizar">Organizar')
        self.assertContains(resposta, 'name="torrent-panel"')
        self.assertNotRegex(
            resposta.content.decode(),
            r'id="torrent-panel-organizar"[^>]*\schecked',
        )
        self.assertContains(resposta, "API de envio")
        self.assertContains(resposta, "https://homelab.conradhub.com/api/torrents/")
        self.assertContains(resposta, "torrent já existe na lista")
        self.assertContains(resposta, "GET /api/torrents/bibliotecas/")
        self.assertContains(resposta, "downloads.js")
        self.assertContains(resposta, "Filtrar pelo nome")
        self.assertContains(resposta, "Limpar filtros")
        self.assertContains(resposta, "Baixando")
        self.assertContains(resposta, "Aguardando")
        self.assertContains(resposta, "Concluídos")
        self.assertContains(resposta, "Com erro")
        self.assertContains(resposta, 'data-sort="progress"')
        self.assertContains(resposta, 'id="torrent-filtro-pasta"')
        self.assertContains(resposta, 'class="torrent-meter"')
        self.assertContains(resposta, 'data-torrent-status="/torrents/estado/"')
        self.assertContains(resposta, "data-torrent-refresh")
        self.assertContains(resposta, "data-torrent-auto")
        self.assertContains(resposta, 'id="torrent-linha"')
        self.assertContains(resposta, "data-torrent-pause")
        self.assertContains(resposta, "data-torrent-resume")
        self.assertContains(resposta, 'name="action" value="pause"')
        self.assertContains(resposta, 'name="action" value="resume"')
        self.assertNotContains(resposta, "data-torrent-poll")
        self.assertNotContains(resposta, 'id="torrent-ordem"')
        painel = self.client.get("/")
        self.assertContains(painel, 'href="/torrents/"')
        self.assertContains(resposta, "A criação do token pede a senha do administrador.")
        self.assertNotContains(resposta, "Consultar token")
        self.assertNotContains(resposta, 'name="password"')

    @override_settings(TORRENT_API_TOKEN="token-da-api")
    def test_admin_consulta_o_token_com_a_propria_senha(self):
        self._liga_jellyfin()
        self.fake.torrent_overview.return_value = {
            "libraries": [
                {"id": "filmes", "name": "Filmes", "path": "/mnt/jellyfin/filmes"}
            ],
            "libraries_error": "",
        }
        self.qbit.estado.return_value = (
            {"available": True, "version": "v5", "reason": ""},
            [],
            "",
        )
        self.user.is_superuser = True
        self.user.set_password("test-password")
        self.user.save()
        self.client.force_login(self.user)
        pagina = self.client.get("/torrents/")
        self.assertContains(pagina, "Senha do administrador")
        self.assertContains(pagina, "Consultar token")
        self.assertNotContains(pagina, 'value="criar"')
        self.assertNotContains(pagina, "token-da-api")
        recusa = self.client.post("/torrents/", {"password": "errada"})
        self.assertContains(recusa, "Senha do administrador incorreta.")
        self.assertNotContains(recusa, "token-da-api")
        ok = self.client.post("/torrents/", {"password": "test-password"})
        self.assertContains(ok, "token-da-api")
        self.assertEqual(ok.headers["Cache-Control"], "no-store")
        log = AuditLog.objects.get(action="torrent.token.view")
        self.assertEqual(log.target, "TORRENT_API_TOKEN")
        self.assertNotIn("token-da-api", log.detail)
        self.user.is_superuser = False
        self.user.save()
        self.client.force_login(self.user)
        bloqueado = self.client.post("/torrents/", {"password": "test-password"})
        self.assertContains(bloqueado, "Só o administrador consulta o token.")
        self.assertNotContains(bloqueado, "token-da-api")

    @override_settings(TORRENT_API_TOKEN="")
    def test_admin_sem_token_ve_criar_e_nao_consultar(self):
        self._liga_jellyfin()
        self.fake.torrent_overview.return_value = {
            "libraries": [
                {"id": "filmes", "name": "Filmes", "path": "/mnt/jellyfin/filmes"}
            ],
            "libraries_error": "",
        }
        self.qbit.estado.return_value = (
            {"available": True, "version": "v5", "reason": ""},
            [],
            "",
        )
        self.user.is_superuser = True
        self.user.set_password("test-password")
        self.user.save()
        self.client.force_login(self.user)
        vazio = self.client.get("/torrents/")
        self.assertContains(vazio, "Criar token")
        self.assertContains(vazio, "Ainda não há token.")
        self.assertContains(vazio, "Nenhum torrent nas pastas do Jellyfin.")
        self.assertContains(vazio, 'data-torrent-status="/torrents/estado/"')
        self.assertContains(vazio, "data-torrent-refresh")
        self.assertContains(vazio, "data-torrent-auto")
        self.assertContains(vazio, 'id="torrent-linha"')
        self.assertContains(vazio, "data-torrent-table")
        self.assertNotContains(vazio, "Consultar token")
        criado = self.client.post(
            "/torrents/",
            {
                "password": "test-password",
                "acao": "criar",
                "token": "token-criado-na-pagina",
            },
        )
        self.assertContains(criado, "Token da API criado.")
        self.assertContains(criado, "token-criado-na-pagina")
        self.assertContains(criado, "Consultar token")
        self.assertNotContains(criado, ">Criar token<")

    @override_settings(TORRENT_API_TOKEN="")
    def test_token_aparece_no_django_admin(self):
        from core.models import TorrentApiToken, token_da_api

        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        indice = self.client.get("/admin/")
        self.assertContains(indice, "Token da API de torrents")
        TorrentApiToken.objects.create(pk=1, token="")
        self.assertEqual(
            self.client.get("/admin/core/torrentapitoken/add/").status_code, 403
        )
        pagina = self.client.get("/admin/core/torrentapitoken/1/change/")
        self.assertContains(pagina, "Vazio desliga a API.")
        self.assertNotContains(pagina, "/admin/core/torrentapitoken/1/delete/")
        curto = self.client.post(
            "/admin/core/torrentapitoken/1/change/",
            {"token": "curto"},
        )
        self.assertContains(curto, "16 a 256")
        self.assertEqual(token_da_api(), "")
        gravado = self.client.post(
            "/admin/core/torrentapitoken/1/change/",
            {"token": "token-gravado-no-admin"},
            follow=True,
        )
        self.assertEqual(gravado.status_code, 200)
        self.assertEqual(token_da_api(), "token-gravado-no-admin")
        de_novo = self.client.get("/admin/core/torrentapitoken/1/change/")
        self.assertContains(de_novo, "token-gravado-no-admin")

    def test_admin_troca_o_token_e_o_host_env_nao_volta(self):
        self._liga_jellyfin()
        self.fake.torrent_overview.return_value = {
            "libraries": [
                {"id": "filmes", "name": "Filmes", "path": "/mnt/jellyfin/filmes"}
            ],
            "libraries_error": "",
        }
        self.qbit.estado.return_value = (
            {"available": True, "version": "v5", "reason": ""},
            [],
            "",
        )
        self.user.is_superuser = True
        self.user.set_password("test-password")
        self.user.save()
        self.client.force_login(self.user)
        novo = "token-novo-da-api"
        with self.settings(TORRENT_API_TOKEN="token-antigo-env"):
            troca = self.client.post(
                "/torrents/",
                {"password": "test-password", "acao": "trocar", "token": novo},
            )
            self.assertContains(troca, novo)
            self.assertContains(troca, "Token da API atualizado.")
            log = AuditLog.objects.get(action="torrent.token.replace")
            self.assertNotIn(novo, log.detail)
            self.assertNotIn(novo, log.target)
            curto = self.client.post(
                "/torrents/",
                {"password": "test-password", "acao": "trocar", "token": "curto"},
            )
            self.assertContains(curto, "16 a 256")
            from core.models import token_da_api

            self.assertEqual(token_da_api(), novo)
            errada = self.client.post(
                "/torrents/",
                {
                    "password": "errada",
                    "acao": "trocar",
                    "token": "outro-token-longo-16",
                },
            )
            self.assertContains(errada, "Senha do administrador incorreta.")
            self.assertEqual(token_da_api(), novo)

    def test_torrent_recusa_endereco_http_e_audita_magnet(self):
        self._liga_jellyfin()
        libraries = [
            {"id": "filmes", "name": "Filmes", "path": "/mnt/jellyfin/filmes"}
        ]
        self.fake.torrent_overview.return_value = {
            "libraries": libraries,
            "libraries_error": "",
        }
        self.qbit.estado.return_value = (
            {"available": True, "version": "v5", "reason": ""},
            [],
            "",
        )
        recusa = self.client.post(
            "/torrents/adicionar/",
            {"magnet": "https://example.test/filme.torrent", "library": "filmes"},
        )
        self.assertContains(recusa, "magnet:?xt=urn:btih:")
        self.qbit.adicionar.assert_not_called()
        self.qbit.adicionar.return_value = {
            "library": "Filmes",
            "path": "/mnt/jellyfin/filmes",
        }
        magnet = "magnet:?xt=urn:btih:" + "a" * 40
        ok = self.client.post(
            "/torrents/adicionar/",
            {"magnet": magnet, "library": "filmes"},
        )
        self.assertRedirects(ok, "/torrents/")
        self.qbit.adicionar.assert_called_once_with(magnet, "filmes", libraries)
        self.assertTrue(
            AuditLog.objects.filter(action="torrent.add", target="Filmes").exists()
        )

    def test_apagar_arquivos_de_torrent_audita(self):
        self._liga_jellyfin()
        self.fake.torrent_overview.return_value = {
            "libraries": [],
            "libraries_error": "",
            "client": {"available": False, "version": "", "reason": "parado"},
            "torrents": [],
            "error": "",
            "active": False,
        }
        self.qbit.acao.return_value = {
            "hash": "a" * 40,
            "action": "delete_files",
        }
        resposta = self.client.post(
            "/torrents/acao/",
            {"hash": "a" * 40, "action": "delete_files"},
        )
        self.assertRedirects(resposta, "/torrents/")
        self.qbit.acao.assert_called_once_with("a" * 40, "delete_files", [])
        self.assertTrue(
            AuditLog.objects.filter(
                action="torrent.delete_files", target="a" * 40
            ).exists()
        )

    def test_acao_delete_instavel_mostra_frase(self):
        self._liga_jellyfin()
        self.fake.torrent_overview.return_value = {
            "libraries": [
                {"id": "filmes", "name": "Filmes", "path": "/mnt/jellyfin/filmes"}
            ],
            "libraries_error": "",
            "client": {"available": True, "version": "v5", "reason": ""},
            "torrents": [],
            "error": "",
            "active": True,
        }
        self.qbit.acao.side_effect = AgentError(
            "Torrent em movimentação/verificação; aguarde o estado estabilizar antes de remover."
        )
        resposta = self.client.post(
            "/torrents/acao/",
            {"hash": "b" * 40, "action": "delete_files"},
            follow=True,
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(
            resposta,
            "Torrent em movimentação/verificação; aguarde o estado estabilizar antes de remover.",
        )
        self.qbit.acao.assert_called_once()
        self.assertFalse(
            AuditLog.objects.filter(action="torrent.delete_files").exists()
        )

    def test_organizar_reexibe_relatorio(self):
        self._liga_jellyfin()
        self.fake.torrent_overview.return_value = {
            "libraries": [
                {"id": "series", "name": "Séries", "path": "/mnt/jellyfin/series"}
            ],
            "libraries_error": "",
        }
        self.qbit.estado.return_value = (
            {"available": True, "version": "v5.0.1", "reason": ""},
            [],
            "",
        )
        self.qbit.organizar_linhas.return_value = {
            "feitos": [{"de": "Colony S01", "para": "Colony (2016)"}],
            "nao_feitos": [{"nome": "Outra", "motivo": "Arquivo diferente: x.mkv"}],
            "ignorados": [],
        }
        resposta = self.client.post(
            "/torrents/organizar/",
            {"library": "series", "marcar": ["Colony S01"]},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Organização")
        self.assertContains(resposta, "Colony S01")
        self.assertContains(resposta, "Colony (2016)")
        self.assertContains(resposta, "Arquivo diferente")
        self.assertContains(resposta, "Andamento")
        self.assertRegex(
            resposta.content.decode(),
            r'id="torrent-panel-organizar"[^>]*\schecked',
        )
        self.qbit.organizar_linhas.assert_called_once()
        log = AuditLog.objects.get(action="torrent.organize")
        self.assertIn("1 feitos", log.target)

    def test_organizar_lista_pastas(self):
        self._liga_jellyfin()
        self.fake.torrent_overview.return_value = {
            "libraries": [
                {"id": "series", "name": "Séries", "path": "/mnt/jellyfin/series"}
            ],
            "libraries_error": "",
        }
        self.qbit.estado.return_value = (
            {"available": True, "version": "v5.0.1", "reason": ""},
            [],
            "",
        )
        self.qbit.listar_pastas_fora_padrao.return_value = [
            {
                "atual": "Silo (2023) Season 1",
                "alvo": "Silo (2023)",
                "tem_torrent": False,
                "hash": "",
            }
        ]
        resposta = self.client.post(
            "/torrents/organizar/listar/",
            {"library": "series"},
        )
        self.assertContains(resposta, "Organizar biblioteca")
        self.assertContains(resposta, "Silo (2023) Season 1")
        self.assertContains(resposta, "Organizar marcadas")
        self.assertRegex(
            resposta.content.decode(),
            r'id="torrent-panel-organizar"[^>]*\schecked',
        )
        self.qbit.listar_pastas_fora_padrao.assert_called_once()

    def test_organizar_só_com_cliente_disponivel(self):
        self._liga_jellyfin()
        self.fake.torrent_overview.return_value = {
            "libraries": [
                {"id": "filmes", "name": "Filmes", "path": "/mnt/jellyfin/filmes"}
            ],
            "libraries_error": "",
        }
        self.qbit.estado.return_value = (
            {"available": False, "version": "", "reason": "parado"},
            [],
            "",
        )
        sem = self.client.get("/torrents/")
        self.assertNotContains(sem, "Listar pastas")
        self.qbit.estado.return_value = (
            {"available": True, "version": "v5.0.1", "reason": ""},
            [],
            "",
        )
        com = self.client.get("/torrents/")
        self.assertContains(com, "Organizar biblioteca")
        self.assertContains(com, "Listar pastas")

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
        self.assertContains(response, "Repositórios restic.")
        self.assertNotContains(response, "Gitea")
        self.assertNotContains(response, "Credenciais")

    def test_gitea_e_arquivos_ficam_fora_sem_o_recurso(self):
        gitea = self.client.get("/backups/gitea/")
        self.assertRedirects(gitea, "/backups/")
        arquivos = self.client.get("/backups/arquivos/")
        self.assertRedirects(arquivos, "/backups/")

    def test_snapshot_restore_exige_confirmacao(self):
        resposta = self.client.post(
            "/snapshots/restaurar/",
            {
                "share": "docs",
                "name": "@GMT-2026.01.01-00.00.00",
                "confirmation": "errado",
            },
        )
        self.assertRedirects(resposta, "/snapshots/")
        self.fake.snapshot_restore.assert_not_called()

    def test_snapshot_restore_audita(self):
        self.fake.snapshot_restore.return_value = {
            "share": "docs",
            "name": "@GMT-2026.01.01-00.00.00",
        }
        resposta = self.client.post(
            "/snapshots/restaurar/",
            {
                "share": "docs",
                "name": "@GMT-2026.01.01-00.00.00",
                "confirmation": "@GMT-2026.01.01-00.00.00",
            },
        )
        self.assertRedirects(resposta, "/snapshots/")
        self.fake.snapshot_restore.assert_called_once()
        self.assertTrue(
            AuditLog.objects.filter(action="snapshot.restore", target="docs/@GMT-2026.01.01-00.00.00").exists()
        )

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
        self.assertContains(response, "Restaurar")
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

    def test_restic_restore_exige_confirmacao(self):
        resposta = self.client.post(
            "/backups/snapshots/aaaaaaaa/restore/",
            {"disk_uuid": "u1", "confirmation": "errado"},
        )
        self.assertRedirects(resposta, "/backups/snapshots/")
        self.fake.backup_restore.assert_not_called()

    def test_restic_restore_audita(self):
        self.fake.backup_restore.return_value = {
            "snapshot_id": "aaaaaaaa",
            "paths": ["/mnt/nas/casa"],
        }
        resposta = self.client.post(
            "/backups/snapshots/aaaaaaaa/restore/",
            {"disk_uuid": "u1", "confirmation": "aaaaaaaa"},
        )
        self.assertRedirects(resposta, "/backups/snapshots/")
        self.fake.backup_restore.assert_called_once()
        self.assertTrue(
            AuditLog.objects.filter(action="backup_restore", target="aaaaaaaa").exists()
        )

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
            "/snapshots/politica/nova/",
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
        self.fake.share_sizes.return_value = {
            "pending": False,
            "error": "",
            "shares": [
                {
                    "name": "docs",
                    "size": 100,
                    "size_snapshots": 20,
                    "size_total": 120,
                }
            ],
        }
        response = self.client.get("/metrics/shares/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["pending"], False)
        self.assertEqual(response.json()["shares"][0]["name"], "docs")
        self.fake.share_sizes.assert_called_once_with()

    def test_shares_renderiza_antes_de_medir_o_disco(self):
        self.fake.list_shares.return_value = [
            {
                "name": "docs",
                "path": "/mnt/nas/docs",
                "browseable": True,
                "read_only": False,
                "comment": "",
                "valid_users": "",
            }
        ]
        self.fake.snapshot_usage.return_value = [
            {"share": "docs", "enabled": True, "keep": 7, "count": 2}
        ]
        response = self.client.get("/shares/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-share="docs"')
        self.assertContains(response, "/metrics/shares/")
        self.assertContains(response, "share-sizes.js")
        self.assertContains(response, "keep 7")
        self.fake.list_shares.assert_called_once_with(include_size=False)
        self.fake.snapshot_usage.assert_called_once_with(include_size=False)

    def test_shares_mostra_o_disco_do_caminho(self):
        self.fake.list_shares.return_value = [
            {"name": "veronte", "path": "/mnt/data/Veronte_Images", "browseable": True, "read_only": False},
            {"name": "print", "path": "/srv/samba/print_files", "browseable": True, "read_only": False},
        ]
        self.fake.snapshot_usage.return_value = []
        self.fake.storage_overview.return_value = {
            "disks": [
                {"name": "sda", "model": "ST2000NM012B-2TD", "mounts": ["/", "/mnt/backup"]},
                {"name": "sdc", "model": "WDC WD40EFZZ-68C", "mounts": ["/mnt/data"]},
                {"name": "sdb", "model": "WDC WD40EFZZ-68C", "mounts": ["/mnt/data"]},
            ],
            "raid": {"mdstat": "", "detail": ""},
            "btrfs": {},
            "system": {},
        }
        response = self.client.get("/shares/")
        self.assertContains(response, "Discos sdb + sdc · WDC WD40EFZZ-68C")
        self.assertContains(response, "Disco sda · ST2000NM012B-2TD")
        painel = self.client.get("/")
        self.assertContains(painel, "Discos sdb + sdc · WDC WD40EFZZ-68C")
        snaps = self.client.get("/snapshots/")
        self.assertContains(snaps, "Disco sda · ST2000NM012B-2TD")

    def test_snapshots_oferece_configurar_editar_e_criar(self):
        self.fake.list_shares.return_value = [
            {"name": "docs", "path": "/mnt/nas/docs"},
            {"name": "midia", "path": "/mnt/nas/midia"},
            {"name": "arquivo", "path": "/mnt/nas/arquivo"},
        ]
        self.fake.snapshot_usage.return_value = [
            {
                "share": "midia",
                "path": "/mnt/nas/midia",
                "enabled": True,
                "keep": 7,
                "count": 1,
                "size": 0,
                "snapshots": [{"name": "@GMT-2026.01.01-00.00.00", "mtime": "01/01/2026 00:00"}],
            },
            {
                "share": "arquivo",
                "path": "/mnt/nas/arquivo",
                "enabled": False,
                "keep": 4,
                "count": 0,
                "size": 0,
                "snapshots": [],
            },
        ]
        response = self.client.get("/snapshots/")
        self.assertContains(response, "Nova política")
        self.assertContains(response, "Configurar")
        self.assertContains(response, "Editar política")
        self.assertContains(response, "Criar snapshot agora")
        self.assertContains(response, "Sem política de snapshot")
        self.assertContains(response, "desativada")
        self.assertContains(response, "permanecem no disco")
        self.assertContains(response, "Restaurar")
        self.assertContains(response, 'action="/snapshots/restaurar/"')
        self.assertContains(response, "share-sizes.js")
        self.fake.snapshot_usage.assert_called_with(include_size=False)

    def test_nova_politica_lista_somente_share_sem_politica(self):
        self.fake.list_shares.return_value = [
            {"name": "docs", "path": "/mnt/nas/docs"},
            {"name": "midia", "path": "/mnt/nas/midia"},
        ]
        self.fake.snapshot_usage.return_value = [
            {"share": "midia", "enabled": True, "keep": 7}
        ]
        response = self.client.get("/snapshots/politica/nova/")
        self.assertContains(response, "docs — /mnt/nas/docs")
        self.assertNotContains(response, "midia —")
        self.assertContains(response, "Criar um snapshot agora")
        self.fake.list_shares.assert_called_with(include_size=False)
        self.fake.snapshot_usage.assert_called_with(include_size=False)

    def test_nova_politica_salva_e_audita(self):
        self.fake.list_shares.return_value = [
            {"name": "docs", "path": "/mnt/nas/docs"}
        ]
        self.fake.snapshot_usage.return_value = []
        self.fake.snapshot_policy_save.return_value = {
            "share": "docs",
            "enabled": True,
            "keep": 5,
            "created": "@GMT-2026.01.01-00.00.00",
        }
        response = self.client.post(
            "/snapshots/politica/nova/",
            {
                "share": "docs",
                "keep": "5",
                "enabled": "on",
                "create_now": "on",
            },
        )
        self.assertRedirects(response, "/snapshots/")
        self.fake.snapshot_policy_save.assert_called_once_with(
            share="docs", enabled=True, keep=5, create_now=True, confirmation=""
        )
        self.assertTrue(
            AuditLog.objects.filter(action="snapshot.policy", target="docs").exists()
        )

    def test_editar_politica_atualiza_sem_criar_snapshot(self):
        self.fake.list_shares.return_value = [
            {"name": "midia", "path": "/mnt/nas/midia"}
        ]
        self.fake.snapshot_usage.return_value = [
            {"share": "midia", "enabled": True, "keep": 7}
        ]
        pagina = self.client.get("/snapshots/midia/politica/")
        self.assertContains(pagina, "Editar política de midia")
        self.assertNotContains(pagina, "Criar um snapshot agora")
        self.fake.snapshot_policy_save.return_value = {
            "share": "midia",
            "enabled": True,
            "keep": 9,
            "created": None,
        }
        response = self.client.post(
            "/snapshots/midia/politica/",
            {"share": "outro", "keep": "9", "enabled": "on"},
        )
        self.assertRedirects(response, "/snapshots/")
        self.fake.snapshot_policy_save.assert_called_once_with(
            share="midia", enabled=True, keep=9, create_now=False, confirmation=""
        )

    def test_editar_politica_pode_desativar(self):
        self.fake.list_shares.return_value = [
            {"name": "midia", "path": "/mnt/nas/midia"}
        ]
        self.fake.snapshot_usage.return_value = [
            {"share": "midia", "enabled": True, "keep": 7}
        ]
        self.fake.snapshot_policy_save.return_value = {
            "share": "midia",
            "enabled": False,
            "keep": 7,
            "created": None,
        }
        response = self.client.post(
            "/snapshots/midia/politica/",
            {"share": "midia", "keep": "7"},
        )
        self.assertRedirects(response, "/snapshots/")
        self.fake.snapshot_policy_save.assert_called_once_with(
            share="midia", enabled=False, keep=7, create_now=False, confirmation=""
        )

    def test_configurar_share_especifico_oferece_o_primeiro_snapshot(self):
        self.fake.list_shares.return_value = [
            {"name": "docs", "path": "/mnt/nas/docs"}
        ]
        self.fake.snapshot_usage.return_value = []
        response = self.client.get("/snapshots/docs/politica/")
        self.assertContains(response, "Configurar snapshot de docs")
        self.assertContains(response, "Criar um snapshot agora")

    def test_politica_de_share_inexistente_volta_para_a_lista(self):
        response = self.client.get("/snapshots/ausente/politica/")
        self.assertRedirects(response, "/snapshots/")

    def test_nova_politica_avisa_quando_nao_ha_share_livre(self):
        self.fake.list_shares.return_value = [
            {"name": "docs", "path": "/mnt/nas/docs"}
        ]
        self.fake.snapshot_usage.return_value = [
            {"share": "docs", "enabled": True, "keep": 2}
        ]
        response = self.client.get("/snapshots/politica/nova/")
        self.assertContains(response, "já têm política")

    def test_politica_sem_confirmacao_reexibe_campo_converter(self):
        self.fake.list_shares.return_value = [
            {"name": "docs", "path": "/mnt/nas/docs"}
        ]
        self.fake.snapshot_usage.return_value = []
        self.fake.snapshot_policy_save.side_effect = AgentError(
            "Para ativar snapshots no Btrfs, confirme digitando o nome do share no "
            "campo de confirmação: a pasta será convertida em subvolume."
        )
        response = self.client.post(
            "/snapshots/politica/nova/",
            {"share": "docs", "keep": "7", "enabled": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conversão para subvolume Btrfs")
        self.assertContains(response, 'name="confirmation"')
        self.fake.snapshot_policy_save.assert_called_once_with(
            share="docs", enabled=True, keep=7, create_now=False, confirmation=""
        )
        self.assertFalse(AuditLog.objects.filter(action="snapshot.policy").exists())

    def test_politica_com_confirmacao_envia_ao_agente(self):
        self.fake.list_shares.return_value = [
            {"name": "docs", "path": "/mnt/nas/docs"}
        ]
        self.fake.snapshot_usage.return_value = []
        self.fake.snapshot_policy_save.return_value = {
            "share": "docs",
            "enabled": True,
            "keep": 7,
            "created": None,
        }
        response = self.client.post(
            "/snapshots/politica/nova/",
            {
                "share": "docs",
                "keep": "7",
                "enabled": "on",
                "confirmation": "docs",
            },
        )
        self.assertRedirects(response, "/snapshots/")
        self.fake.snapshot_policy_save.assert_called_once_with(
            share="docs", enabled=True, keep=7, create_now=False, confirmation="docs"
        )

    def test_politica_mostra_erro_do_agente(self):
        self.fake.list_shares.return_value = [
            {"name": "docs", "path": "/mnt/nas/docs"}
        ]
        self.fake.snapshot_usage.return_value = []
        self.fake.snapshot_policy_save.side_effect = AgentError(
            "Politica salva, mas o snapshot nao foi criado: rsync falhou"
        )
        response = self.client.post(
            "/snapshots/politica/nova/",
            {"share": "docs", "keep": "7", "enabled": "on", "create_now": "on"},
        )
        self.assertContains(response, "snapshot nao foi criado")
        self.assertFalse(AuditLog.objects.filter(action="snapshot.policy").exists())

    def test_backup_check_chama_o_agente(self):
        self.fake.backup_check.return_value = {
            "started": True,
            "task": "backupcheck-abcd1234",
            "status": "running",
        }
        resposta = self.client.post(
            "/backups/disks/check/", data={"uuid": "abc"}, follow=True
        )
        self.assertContains(resposta, "Trabalho iniciado")
        self.assertContains(resposta, "data-task-poll")
        self.assertContains(resposta, "/tarefas/backupcheck-abcd1234/")
        self.fake.backup_check.assert_called_once_with("abc")

    def test_status_da_tarefa_ausente_nao_vira_500(self):
        self.fake.task_status.side_effect = AgentError("Tarefa nao encontrada")
        resposta = self.client.get("/tarefas/backupcheck-abcd1234/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["status"], "failed")
        self.assertIn("nao encontrada", resposta.json()["message"])

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
        }
        self.fake.firewall_overview.return_value = {
            "installed": True,
            "active": True,
            "status": "ativo",
            "policies": {
                "incoming": "deny",
                "outgoing": "allow",
                "routed": "deny",
            },
            "rules": [
                {
                    "number": 1,
                    "spec": "allow 22/tcp",
                    "to": "22/tcp",
                    "action": "allow",
                    "direction": "in",
                    "from": "Anywhere",
                    "signature": "allow 22/tcp",
                }
            ],
            "ssh_allowed": True,
            "error": "",
        }
        resposta = self.client.get("/rede/")
        self.assertContains(resposta, "192.168.0.1")
        self.assertContains(resposta, "eth0")
        self.assertContains(resposta, "192.168.0.10")
        self.assertContains(resposta, "22/tcp")
        self.assertContains(resposta, "ALLOW IN")
        self.assertContains(resposta, "allow 22/tcp")
        self.assertContains(resposta, "Desativar firewall")
        self.assertNotContains(resposta, "<pre")
        self.assertNotContains(resposta, "New profiles")

    def test_rede_mostra_controles_quando_gestao_ligada(self):
        resposta = self.client.get("/rede/")
        self.assertContains(resposta, "Adicionar regra")
        self.assertContains(resposta, "Ativar firewall")

    @override_settings(FIREWALL_MANAGE=False)
    def test_rede_somente_leitura_quando_gestao_desligada(self):
        resposta = self.client.get("/rede/")
        self.assertContains(resposta, "UFW")
        self.assertNotContains(resposta, "Adicionar regra")
        self.assertNotContains(resposta, "Ativar firewall")
        self.assertNotContains(resposta, "Desativar firewall")

    def test_firewall_enable_chama_agente(self):
        resposta = self.client.post(
            "/rede/firewall/",
            {"acao": "enable", "allow_ssh": "1"},
        )
        self.assertRedirects(resposta, "/rede/")
        self.fake.firewall_enable.assert_called_once_with(allow_ssh=True)
        self.assertTrue(AuditLog.objects.filter(action="firewall.enable").exists())

    def test_firewall_disable_chama_agente(self):
        resposta = self.client.post("/rede/firewall/", {"acao": "disable"})
        self.assertRedirects(resposta, "/rede/")
        self.fake.firewall_disable.assert_called_once_with()
        self.assertTrue(AuditLog.objects.filter(action="firewall.disable").exists())

    def test_firewall_add_chama_agente(self):
        resposta = self.client.post(
            "/rede/firewall/",
            {
                "acao": "add",
                "rule_action": "allow",
                "port": "8080",
                "proto": "tcp",
                "source": "192.168.0.0/24",
            },
        )
        self.assertRedirects(resposta, "/rede/")
        self.fake.firewall_add_rule.assert_called_once_with(
            action="allow",
            port="8080",
            proto="tcp",
            source="192.168.0.0/24",
        )
        self.assertTrue(
            AuditLog.objects.filter(action="firewall.add", target="8080/tcp").exists()
        )

    def test_firewall_delete_chama_agente(self):
        resposta = self.client.post(
            "/rede/firewall/",
            {"acao": "delete", "spec": "allow 22/tcp"},
        )
        self.assertRedirects(resposta, "/rede/")
        self.fake.firewall_delete_rule.assert_called_once_with("allow 22/tcp")
        self.assertTrue(
            AuditLog.objects.filter(
                action="firewall.delete", target="allow 22/tcp"
            ).exists()
        )

    def test_firewall_acao_invalida_nao_chama_agente(self):
        resposta = self.client.post("/rede/firewall/", {"acao": "reset"})
        self.assertRedirects(resposta, "/rede/")
        self.fake.firewall_enable.assert_not_called()
        self.fake.firewall_disable.assert_not_called()
        self.fake.firewall_add_rule.assert_not_called()
        self.fake.firewall_delete_rule.assert_not_called()

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

    def test_senha_do_usuario_e_so_do_samba(self):
        resposta = self.client.get("/usuarios/senha/?username=ana")
        self.assertContains(resposta, "vale apenas para o Samba")
        self.assertNotContains(resposta, "login no servidor")
        self.assertContains(resposta, 'name="username"')
        self.assertContains(resposta, 'value="ana"')
        self.assertContains(resposta, "readonly")
        self.assertContains(resposta, "Mínimo 8 caracteres")

    def test_senha_post_sucesso_redireciona_e_audita(self):
        resposta = self.client.post(
            "/usuarios/senha/?username=ana",
            {"username": "ana", "password": "senhanova1"},
            follow=True,
        )
        self.assertEqual(resposta.status_code, 200)
        self.fake.set_password.assert_called_once_with("ana", "senhanova1")
        self.assertContains(resposta, "Senha de ana atualizada.")
        self.assertContains(resposta, "Concluído")
        self.assertContains(resposta, 'class="alert ok"')
        self.assertNotContains(resposta, "Não foi possível concluir")
        self.assertTrue(
            AuditLog.objects.filter(action="user.password", target="ana").exists()
        )

    def test_senha_post_agente_mostra_o_motivo(self):
        self.fake.set_password.side_effect = AgentError("Usuario nao existe: ana")
        resposta = self.client.post(
            "/usuarios/senha/?username=ana",
            {"username": "ana", "password": "senhanova1"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Não foi possível concluir")
        self.assertContains(resposta, "Usuario nao existe: ana")
        self.assertFalse(
            AuditLog.objects.filter(action="user.password", target="ana").exists()
        )

    def test_senha_post_sem_usuario_mostra_alerta(self):
        resposta = self.client.post(
            "/usuarios/senha/",
            {"password": "senhanova1"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.fake.set_password.assert_not_called()
        self.assertContains(resposta, "Não foi possível concluir")
        self.assertContains(resposta, "Este campo é obrigatório.")

    def test_senha_post_curta_mostra_alerta(self):
        resposta = self.client.post(
            "/usuarios/senha/?username=ana",
            {"username": "ana", "password": "curta"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.fake.set_password.assert_not_called()
        self.assertContains(resposta, "Não foi possível concluir")
        self.assertContains(resposta, "no mínimo 8 caracteres")

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
        self.assertContains(resposta, "person-card")
        self.assertContains(resposta, "Ana")
        self.assertContains(resposta, "Senha")
        self.assertContains(resposta, "share-row")
        self.assertContains(resposta, "person-actions")
        self.assertNotContains(resposta, "status ok")
        self.assertNotContains(resposta, ">ativo<")
        self.assertContains(
            resposta,
            'data-confirm="Excluir o grupo midia? Quem estava nele perde esse acesso."',
        )
        self.assertNotContains(resposta, "<th>Nome</th>")
        self.assertNotContains(resposta, "<th>Status</th>")
        self.assertNotContains(resposta, 'class="chip"')

    def test_usuarios_cartao_limita_chips_de_share(self):
        share = [f"grupo{i}" for i in range(22)]
        self.fake.list_users.return_value = [
            {
                "username": "conrado",
                "fullname": "Conrado Almeida com nome longo",
                "groups": share + ["sudo", "docker"],
                "enabled": True,
            }
        ]
        self.fake.list_groups.return_value = share + ["conrado", "sudo", "docker"]
        resposta = self.client.get("/usuarios/")
        self.assertContains(resposta, "tag-more")
        self.assertContains(resposta, ">+20<")
        self.assertContains(resposta, "grupo0")
        self.assertContains(resposta, "grupo1")
        html = resposta.content.decode()
        inicio = html.index("person-share-chips")
        fim = html.index("person-sys", inicio)
        faixa = html[inicio:fim]
        self.assertNotIn(">grupo2<", faixa)

    @patch(
        "core.middleware.sessao",
        return_value={"ok": True, "ativo": True, "autorizado": True},
    )
    @override_settings(
        CREDENTIALS_MANAGE_USERS=True,
        CREDENTIALS_URL="http://credenciais",
        CREDENTIALS_API_TOKEN="segredo",
    )
    def test_usuarios_moya_mostra_acoes_no_credenciais(self, _sessao):
        self.fake.list_users.return_value = [
            {
                "username": "barbara.luz",
                "fullname": "",
                "groups": ["barbara.luz", "veronte"],
                "enabled": True,
            }
        ]
        self.fake.list_groups.return_value = ["barbara.luz", "veronte"]
        resposta = self.client.get("/usuarios/")
        self.assertContains(resposta, "person-actions")
        self.assertContains(
            resposta,
            'href="http://credenciais/usuarios/senha/?username=barbara.luz"',
        )
        self.assertContains(
            resposta,
            'href="http://credenciais/usuarios/grupos/?username=barbara.luz"',
        )
        self.assertNotContains(resposta, 'action="/usuarios/toggle/"')

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
        capacidades = dict(self.fake.host_capabilities.return_value)
        capacidades["containers"] = True
        self.fake.host_capabilities.return_value = capacidades
        context_processors._cached_caps = None
        context_processors._cached_at = 0.0
        resposta = self.client.get("/containers/")
        self.assertContains(resposta, "gitea")
        self.assertContains(resposta, 'class="count">2<')
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

    def test_container_do_painel_nao_pode_ser_parado(self):
        self.client.post(
            "/containers/acao/",
            {"name": "homelab-storage-admin", "action": "stop"},
        )
        self.fake.container_action.assert_not_called()

    def test_container_logs_redireciona_para_sistema_logs(self):
        resposta = self.client.get(
            "/containers/logs/", {"name": "gitea", "tail": "100"}
        )
        self.assertEqual(resposta.status_code, 302)
        loc = resposta["Location"]
        self.assertIn("/sistema/logs/", loc)
        self.assertIn("filtro=container", loc)
        self.assertIn("name=gitea", loc)
        self.fake.container_logs.assert_not_called()


class SystemPagesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="sys-t", password="test-password"
        )
        self.client.force_login(self.user)
        self.fake = fake_agent()
        for module in (
            core_views,
            core_downloads,
            context_processors,
            system_views_module,
        ):
            patcher = patch.object(module, "agent", self.fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.fake.terminal_open.return_value = {"session_id": "abc", "cols": 80, "rows": 24}
        self.fake.terminal_io.return_value = {"output_b64": ""}
        self.fake.terminal_close.return_value = {"closed": True}
        context_processors._cached_caps = None
        context_processors._cached_at = 0.0

    def test_system_host_renders_sem_apt(self):
        resp = self.client.get("/sistema/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Hostname")

    @override_settings(SYSTEM_MANAGE=False)
    def test_apt_nao_dispara_com_system_manage_off(self):
        caps = dict(self.fake.host_capabilities.return_value)
        caps["apt"] = True
        caps["system_manage"] = True
        self.fake.host_capabilities.return_value = caps
        context_processors._cached_caps = None
        self.client.post("/sistema/", {"acao": "apt_check"})
        self.fake.apt_check.assert_not_called()
        self.client.post(
            "/sistema/",
            {"acao": "apt_upgrade", "confirmation": "ATUALIZAR"},
        )
        self.fake.apt_upgrade.assert_not_called()

    def test_frase_errada_nao_dispara_apt_upgrade(self):
        caps = dict(self.fake.host_capabilities.return_value)
        caps.update({"apt": True, "system_manage": True})
        self.fake.host_capabilities.return_value = caps
        context_processors._cached_caps = None
        self.client.post(
            "/sistema/",
            {"acao": "apt_upgrade", "confirmation": "errado"},
        )
        self.fake.apt_upgrade.assert_not_called()

    @override_settings(SYSTEM_MANAGE=True)
    def test_sistema_logs_filtro_invalido(self):
        caps = dict(self.fake.host_capabilities.return_value)
        caps["journal"] = True
        self.fake.host_capabilities.return_value = caps
        context_processors._cached_caps = None
        r = self.client.get("/sistema/logs/", {"filtro": "invalido"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "desconhecido")

    def test_systemd_unit_recusada(self):
        caps = dict(self.fake.host_capabilities.return_value)
        caps.update({"systemctl": True, "system_manage": True})
        self.fake.host_capabilities.return_value = caps
        context_processors._cached_caps = None
        r = self.client.post(
            "/sistema/servicos/acao/",
            {"unit": "ssh", "action": "stop", "confirmation": "ssh"},
        )
        self.assertRedirects(r, "/sistema/servicos/")
        self.fake.systemd_unit_action.assert_not_called()

    def test_keys_sem_jellyfin_sem_slot_torrent(self):
        self.fake.host_capabilities.return_value = {
            **dict(self.fake.host_capabilities.return_value),
            "jellyfin": False,
        }
        context_processors._cached_caps = None
        r = self.client.get("/sistema/chaves/")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Fingerprint SHA-256")

    @override_settings(TERMINAL_ENABLE=False)
    def test_terminal_rota_oculta(self):
        self.fake.host_capabilities.return_value = {
            **dict(self.fake.host_capabilities.return_value),
            "terminal_enable": False,
        }
        context_processors._cached_caps = None
        self.assertEqual(self.client.get("/sistema/terminal/").status_code, 404)

    @override_settings(TERMINAL_ENABLE=True)
    def test_terminal_abre_com_flag(self):
        self.fake.host_capabilities.return_value = {
            **dict(self.fake.host_capabilities.return_value),
            "terminal_enable": True,
        }
        context_processors._cached_caps = None
        r = self.client.get("/sistema/terminal/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Senha sudo")
        self.assertContains(r, "Desconectar")

    @override_settings(TERMINAL_ENABLE=True)
    def test_terminal_pede_senha_sudo(self):
        self.fake.host_capabilities.return_value = {
            **dict(self.fake.host_capabilities.return_value),
            "terminal_enable": True,
        }
        context_processors._cached_caps = None
        r = self.client.post(
            "/sistema/terminal/io/",
            json.dumps({"op": "open", "user": "ana"}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)
        self.fake.terminal_open.assert_not_called()

    @override_settings(TERMINAL_ENABLE=True)
    def test_terminal_io_audita_abrir(self):
        self.fake.host_capabilities.return_value = {
            **dict(self.fake.host_capabilities.return_value),
            "terminal_enable": True,
        }
        context_processors._cached_caps = None
        self.client.post(
            "/sistema/terminal/io/",
            json.dumps({"op": "open", "user": "ana", "password": "segredo"}),
            content_type="application/json",
        )
        self.fake.terminal_open.assert_called_once_with(
            cols=80, rows=24, user="ana", password="segredo"
        )
        log = AuditLog.objects.get(action="terminal.open")
        self.assertEqual(log.target, "ana")
        self.assertNotIn("segredo", log.detail or "")
        self.assertNotIn("segredo", log.target or "")

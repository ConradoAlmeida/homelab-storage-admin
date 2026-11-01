from __future__ import annotations

import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

import core.context_processors as context_processors
import core.downloads as core_downloads
from core.agent import AgentError
from core.models import AuditLog, token_da_api

from .test_views import fake_agent

TOKEN = "segredo"
MAGNET = "magnet:?xt=urn:btih:" + "a" * 40


@override_settings(TORRENT_API_TOKEN=TOKEN)
class TorrentApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tester", password="test-password"
        )
        self.fake = fake_agent()
        for module in (core_downloads, context_processors):
            patcher = patch.object(module, "agent", self.fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.qbit = Mock()
        self.qbit.adicionar.return_value = {
            "library": "Filmes",
            "path": "/mnt/jellyfin/filmes",
        }
        self.qbit.JA_EXISTE = "torrent já existe na lista"
        qbit_patch = patch.object(core_downloads, "qbittorrent", self.qbit)
        qbit_patch.start()
        self.addCleanup(qbit_patch.stop)
        self.libraries = [
            {"id": "filmes", "name": "Filmes", "path": "/mnt/jellyfin/filmes"}
        ]
        self.fake.torrent_overview.return_value = {
            "libraries": self.libraries,
            "libraries_error": "",
        }
        context_processors._cached_caps = None
        context_processors._cached_at = 0.0

    def _liga_jellyfin(self):
        capacidades = dict(self.fake.host_capabilities.return_value)
        capacidades["jellyfin"] = True
        self.fake.host_capabilities.return_value = capacidades
        context_processors._cached_caps = None
        context_processors._cached_at = 0.0

    def _post(self, payload, *, token=TOKEN, content_type="application/json", query=""):
        kwargs = {
            "data": json.dumps(payload),
            "content_type": content_type,
        }
        if token is not None:
            kwargs["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return self.client.post(f"/api/torrents/{query}", **kwargs)

    def test_host_env_so_semeia_a_primeira_linha(self):
        with override_settings(TORRENT_API_TOKEN="primeiro-token-longo"):
            self.assertEqual(token_da_api(), "primeiro-token-longo")
        with override_settings(TORRENT_API_TOKEN="segundo-token-longo"):
            self.assertEqual(token_da_api(), "primeiro-token-longo")

    def test_linha_vazia_nao_recebe_o_host_env_depois(self):
        with override_settings(TORRENT_API_TOKEN=""):
            self.assertEqual(token_da_api(), "")
        with override_settings(TORRENT_API_TOKEN="depois-do-vazio-16"):
            self.assertEqual(token_da_api(), "")

    def test_banco_vence_o_token_do_ambiente(self):
        self._liga_jellyfin()
        from core.models import definir_token_da_api

        definir_token_da_api("token-gravado-no-banco")
        with override_settings(TORRENT_API_TOKEN="token-do-ambiente"):
            ruim = self._post(
                {"magnet": MAGNET, "library": "Filmes"},
                token="token-do-ambiente",
            )
            ok = self._post(
                {"magnet": MAGNET, "library": "Filmes"},
                token="token-gravado-no-banco",
            )
        self.assertEqual(ruim.status_code, 401)
        self.assertEqual(ok.status_code, 201)

    def test_token_vazio_desliga_a_rota(self):
        with override_settings(TORRENT_API_TOKEN=""):
            resposta = self._post({"magnet": MAGNET, "library": "Filmes"})
        self.assertEqual(resposta.status_code, 404)
        self.qbit.adicionar.assert_not_called()
        self.fake.torrent_overview.assert_not_called()

    def test_token_errado_e_sessao_nao_autorizam(self):
        self._liga_jellyfin()
        errado = self._post({"magnet": MAGNET, "library": "Filmes"}, token="outro")
        self.assertEqual(errado.status_code, 401)
        self.client.force_login(self.user)
        sessao = self._post({"magnet": MAGNET, "library": "Filmes"}, token=None)
        self.assertEqual(sessao.status_code, 401)
        consulta = self.client.post(
            "/api/torrents/?token=segredo",
            data=json.dumps({"magnet": MAGNET, "library": "Filmes"}),
            content_type="application/json",
        )
        self.assertEqual(consulta.status_code, 401)
        self.qbit.adicionar.assert_not_called()

    def test_sem_jellyfin_responde_404(self):
        resposta = self._post({"magnet": MAGNET, "library": "Filmes"})
        self.assertEqual(resposta.status_code, 404)
        self.assertEqual(
            resposta.json()["error"],
            "O Jellyfin não está instalado neste servidor.",
        )
        self.qbit.adicionar.assert_not_called()

    def test_recusa_url_http(self):
        self._liga_jellyfin()
        resposta = self._post(
            {"magnet": "https://example.test/filme.torrent", "library": "Filmes"}
        )
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("magnet:?xt=urn:btih:", resposta.json()["error"])
        self.qbit.adicionar.assert_not_called()

    def test_magnet_valido_audita_sem_gravar_o_link(self):
        self._liga_jellyfin()
        cliente = Client(enforce_csrf_checks=True)
        resposta = cliente.post(
            "/api/torrents/",
            data=json.dumps({"magnet": MAGNET, "library": "filmes"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
        )
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json(), {"library": "Filmes"})
        self.qbit.adicionar.assert_called_once_with(MAGNET, "filmes", self.libraries)
        log = AuditLog.objects.get(action="torrent.add")
        self.assertEqual(log.target, "Filmes")
        self.assertEqual(log.detail, "api")
        self.assertIsNone(log.actor_id)
        self.assertNotIn(MAGNET, log.target)
        self.assertNotIn(MAGNET, log.detail)

    def test_aceita_biblioteca_pelo_nome_e_corpo_de_curl(self):
        self._liga_jellyfin()
        resposta = self._post(
            {"magnet": MAGNET, "library": "Filmes"},
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(resposta.status_code, 201)
        self.qbit.adicionar.assert_called_once_with(MAGNET, "filmes", self.libraries)

    def test_duplicado_responde_409(self):
        self._liga_jellyfin()
        self.qbit.adicionar.side_effect = AgentError("torrent já existe na lista")
        resposta = self._post({"magnet": MAGNET, "library": "Filmes"})
        self.assertEqual(resposta.status_code, 409)
        self.assertEqual(resposta.json()["error"], "torrent já existe na lista")
        self.assertFalse(AuditLog.objects.filter(action="torrent.add").exists())

    def test_falha_do_agente_responde_503(self):
        self._liga_jellyfin()
        self.fake.torrent_overview.side_effect = AgentError("agente fora")
        resposta = self._post({"magnet": MAGNET, "library": "Filmes"})
        self.assertEqual(resposta.status_code, 503)
        self.assertEqual(resposta.json()["error"], "agente fora")
        self.qbit.adicionar.assert_not_called()

    def test_bibliotecas_listam_id_e_nome(self):
        self._liga_jellyfin()
        resposta = self.client.get(
            "/api/torrents/bibliotecas/",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            resposta.json(),
            {"libraries": [{"id": "filmes", "name": "Filmes"}]},
        )
        self.assertNotIn("/mnt/jellyfin", resposta.content.decode())

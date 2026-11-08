from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

import core.context_processors as context_processors
import core.system_views as system_views_module
from core.config_locais import comando_ssh, contexto_config_locais
from tests.test_views import fake_agent


class ConfigLocaisPureTests(TestCase):
    def test_ssh_login_explicito(self):
        self.assertEqual(
            comando_ssh(
                ssh_login="conrado@homelab.local",
                share_owner="conrado",
                hostname="pi",
            ),
            "ssh conrado@homelab.local",
        )

    def test_ssh_sem_login_com_hostname(self):
        self.assertEqual(
            comando_ssh(ssh_login="", share_owner="conrado", hostname="nas"),
            "ssh conrado@nas",
        )

    def test_ssh_sem_hostname(self):
        self.assertEqual(
            comando_ssh(ssh_login="", share_owner="conrado", hostname=None),
            "ssh conrado",
        )

    def test_arquivos_pi_sem_credenciais(self):
        ctx = contexto_config_locais(
            ssh_login="conrado@homelab.local",
            share_owner="conrado",
            hostname=None,
            host_env_path="/etc/homelab-storage-admin/host.env",
            stack_env_path="/opt/stacks/homelab-storage-admin/.env",
            services_ini_host="/mnt/nas/apps/homelab-storage-admin/data/services.ini",
            credenciais_env="",
        )
        caminhos = [a.caminho for a in ctx["arquivos"]]
        self.assertEqual(len(caminhos), 3)
        self.assertIn("/mnt/nas/apps/homelab-storage-admin/data/services.ini", caminhos)


class SystemConfigViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="cfg-t", password="test-password"
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.fake = fake_agent()
        patcher = patch.object(system_views_module, "agent", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        context_processors._cached_caps = None
        context_processors._cached_at = 0.0

    @override_settings(
        SSH_LOGIN="conrado@homelab.local",
        CREDENCIAIS_ENV="",
        SERVICES_INI_HOST="/mnt/nas/apps/homelab-storage-admin/data/services.ini",
        STACK_ENV_PATH="/opt/stacks/homelab-storage-admin/.env",
    )
    def test_pagina_perfil_pi(self):
        self.fake.host_info.return_value = {"hostname": "homelab"}
        resp = self.client.get("/sistema/config/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ssh conrado@homelab.local")
        self.assertContains(resp, "/etc/homelab-storage-admin/host.env")
        self.assertContains(resp, "/mnt/nas/apps/homelab-storage-admin/data/services.ini")
        self.assertNotContains(resp, "moya_credenciais_app")

    @override_settings(
        SSH_LOGIN="conrado@10.72.60.181",
        CREDENCIAIS_ENV="/home/conrado/moya_credenciais_app/.env",
        SERVICES_INI_HOST="/opt/stacks/homelab-storage-admin/data/services.ini",
        STACK_ENV_PATH="/opt/stacks/homelab-storage-admin/.env",
    )
    def test_pagina_perfil_moya(self):
        self.fake.host_info.return_value = {"hostname": "moya"}
        resp = self.client.get("/sistema/config/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ssh conrado@10.72.60.181")
        self.assertContains(resp, "/opt/stacks/homelab-storage-admin/data/services.ini")
        self.assertContains(resp, "moya_credenciais_app")

    @override_settings(SSH_LOGIN="", SHARE_OWNER="conrado", CREDENCIAIS_ENV="")
    def test_agente_falha_mostra_ssh_owner(self):
        from core.agent import AgentError

        self.fake.host_info.side_effect = AgentError("off")
        resp = self.client.get("/sistema/config/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ssh conrado")
        self.assertContains(resp, "host.env")

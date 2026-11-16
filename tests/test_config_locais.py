from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

import core.context_processors as context_processors
import core.system_views as system_views_module
from core.config_locais import (
    comando_ssh,
    comandos_do_env,
    contexto_config_locais,
    perfil_do_env,
)
from tests.test_views import fake_agent


class ComandosDoEnvTests(TestCase):
    def test_perfil_do_caminho(self):
        self.assertEqual(perfil_do_env("/opt/x/deploy/moya/apps.env"), "moya")
        self.assertEqual(perfil_do_env("/opt/x/deploy/pi/apps.env"), "pi")
        self.assertEqual(perfil_do_env(""), "")
        self.assertEqual(perfil_do_env("/etc/homelab-storage-admin/apps.env"), "")

    def test_perfil_explicito_vence_o_caminho(self):
        # HOST_PROFILE e a fonte; o caminho so serve de fallback.
        self.assertEqual(
            perfil_do_env("/etc/homelab-storage-admin/apps.env", "nas2"), "nas2"
        )
        self.assertEqual(perfil_do_env("/etc/homelab-storage-admin/apps.env"), "")

    def test_qualquer_slug_ganha_o_flag(self):
        # Nada de lista fixa pi|moya: o que nao e o default precisa do flag.
        self.assertEqual(
            comandos_do_env("/etc/homelab-storage-admin/apps.env", "nas2")[
                "comando_apply"
            ],
            "sudo bash scripts/stacks/apps-sync.sh --perfil nas2 --apply",
        )
        self.assertEqual(
            comandos_do_env("/etc/homelab-storage-admin/apps.env", "pi")[
                "comando_apply"
            ],
            "sudo bash scripts/stacks/apps-sync.sh --apply",
        )

    def test_flag_perfil_so_onde_o_script_precisa(self):
        # apps-sync assume `pi`: no moya o flag e obrigatorio.
        self.assertEqual(
            comandos_do_env("/opt/x/deploy/moya/apps.env")["comando_apply"],
            "sudo bash scripts/stacks/apps-sync.sh --perfil moya --apply",
        )
        self.assertEqual(
            comandos_do_env("/opt/x/deploy/pi/apps.env")["comando_apply"],
            "sudo bash scripts/stacks/apps-sync.sh --apply",
        )


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
        self.assertEqual(
            caminhos,
            [
                "/etc/homelab-storage-admin/host.env",
                "/opt/stacks/homelab-storage-admin/.env",
            ],
        )
        # O gerado nao se mistura com o que se edita.
        self.assertEqual(
            [a.caminho for a in ctx["gerados"]],
            ["/mnt/nas/apps/homelab-storage-admin/data/services.ini"],
        )
        self.assertIsNone(ctx["apps_env"])
        self.assertFalse(ctx["tem_apps_env"])

    def test_arquivos_pi_com_apps_env(self):
        ctx = contexto_config_locais(
            ssh_login="conrado@homelab.local",
            share_owner="conrado",
            hostname=None,
            host_env_path="/etc/homelab-storage-admin/host.env",
            stack_env_path="/opt/stacks/homelab-storage-admin/.env",
            services_ini_host="/mnt/nas/apps/homelab-storage-admin/data/services.ini",
            credenciais_env="",
            apps_env="/opt/stacks/homelab-storage-admin/deploy/pi/apps.env",
        )
        self.assertEqual([a.nome for a in ctx["arquivos"]], ["host.env", ".env"])
        self.assertEqual([a.nome for a in ctx["gerados"]], ["services.ini"])
        self.assertTrue(ctx["tem_apps_env"])
        apps = ctx["apps_env"]
        self.assertEqual(
            apps.caminho, "/opt/stacks/homelab-storage-admin/deploy/pi/apps.env"
        )
        self.assertIn("apps-sync --apply", apps.vigencia)
        self.assertIn("atalho", apps.controlo)

    def test_moya_sem_apps_env_nao_tem_principal(self):
        ctx = contexto_config_locais(
            ssh_login="",
            share_owner="conrado",
            hostname="moya",
            host_env_path="/etc/homelab-storage-admin/host.env",
            stack_env_path="/opt/stacks/homelab-storage-admin/.env",
            services_ini_host="/opt/stacks/homelab-storage-admin/data/services.ini",
            credenciais_env="/home/conrado/moya_credenciais_app/.env",
        )
        self.assertIsNone(ctx["apps_env"])
        # O .env do Credenciais continua na lista dos raros.
        self.assertEqual(
            [a.nome for a in ctx["arquivos"]],
            ["host.env", ".env", ".env (Credenciais)"],
        )


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
        APPS_ENV_PATH="/opt/stacks/homelab-storage-admin/deploy/pi/apps.env",
    )
    def test_pagina_perfil_pi(self):
        self.fake.host_info.return_value = {"hostname": "homelab"}
        resp = self.client.get("/sistema/config/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ssh conrado@homelab.local")
        self.assertContains(resp, "/etc/homelab-storage-admin/host.env")
        self.assertContains(resp, "/mnt/nas/apps/homelab-storage-admin/data/services.ini")
        self.assertContains(resp, "/opt/stacks/homelab-storage-admin/deploy/pi/apps.env")
        self.assertContains(resp, "apps-sync.sh --apply")
        self.assertContains(resp, "Rotas, DNS e atalhos")
        self.assertContains(resp, "Como aplicar")
        self.assertContains(resp, "git pull")
        self.assertContains(resp, "apps-sync.sh --apply")
        self.assertContains(resp, "apps-sync.sh --doctor")
        # No Pi o script nao precisa de --perfil.
        self.assertNotContains(resp, "--perfil moya")
        self.assertContains(resp, "Gerados")
        self.assertContains(resp, "Ver rotas e atalhos")
        self.assertNotContains(resp, "moya_credenciais_app")

    @override_settings(
        SSH_LOGIN="conrado@10.72.60.181",
        CREDENCIAIS_ENV="/home/conrado/moya_credenciais_app/.env",
        SERVICES_INI_HOST="/opt/stacks/homelab-storage-admin/data/services.ini",
        STACK_ENV_PATH="/opt/stacks/homelab-storage-admin/.env",
        APPS_ENV_PATH="",
    )
    def test_pagina_perfil_moya(self):
        self.fake.host_info.return_value = {"hostname": "moya"}
        resp = self.client.get("/sistema/config/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ssh conrado@10.72.60.181")
        self.assertContains(resp, "/opt/stacks/homelab-storage-admin/data/services.ini")
        self.assertContains(resp, "moya_credenciais_app")
        # Sem APPS_ENV_PATH nao ha bloco principal; o services.ini continua
        # listado como gerado.
        self.assertNotContains(resp, "deploy/moya/apps.env")
        self.assertContains(resp, "Sem <span class=\"mono\">apps.env</span>")
        self.assertContains(resp, "Gerados")

    @override_settings(
        SSH_LOGIN="conrado@nas2.local",
        CREDENCIAIS_ENV="",
        HOST_PROFILE="nas2",
        APPS_ENV_PATH="/etc/homelab-storage-admin/apps.env",
    )
    def test_pagina_de_host_novo_mostra_o_flag_certo(self):
        # O caso que quebrava: APPS_ENV_PATH em /etc mostrava o comando do Pi.
        resp = self.client.get("/sistema/config/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "apps-sync.sh --perfil nas2 --apply")
        self.assertNotContains(resp, "apps-sync.sh --perfil pi")

    @override_settings(
        SSH_LOGIN="conrado@10.72.60.181",
        CREDENCIAIS_ENV="",
        HOST_PROFILE="moya",
        SERVICES_INI_HOST="/opt/stacks/homelab-storage-admin/data/services.ini",
        STACK_ENV_PATH="/opt/stacks/homelab-storage-admin/.env",
        APPS_ENV_PATH="/opt/stacks/homelab-storage-admin/deploy/moya/apps.env",
    )
    def test_pagina_moya_mostra_o_flag_perfil(self):
        resp = self.client.get("/sistema/config/")
        self.assertEqual(resp.status_code, 200)
        # No moya o script precisa do flag: a tela mostra o comando que funciona.
        self.assertContains(resp, "apps-sync.sh --perfil moya --apply")
        self.assertContains(resp, "apps-sync.sh --perfil moya --doctor")

    @override_settings(SSH_LOGIN="", SHARE_OWNER="conrado", CREDENCIAIS_ENV="")
    def test_agente_falha_mostra_ssh_owner(self):
        from core.agent import AgentError

        self.fake.host_info.side_effect = AgentError("off")
        resp = self.client.get("/sistema/config/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ssh conrado")
        self.assertContains(resp, "host.env")

from __future__ import annotations

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

import core.context_processors as context_processors
import core.views as core_views
from core.models import AuditLog


APPS = [
    {
        "app": "credenciais",
        "label": "Credenciais",
        "container": "moya-credenciais",
        "username": "admin",
        "installed": True,
        "running": True,
        "exists": False,
        "is_superuser": False,
        "is_staff": False,
        "is_active": False,
        "usable_password": False,
        "last_login": None,
        "date_joined": None,
        "superusers": ["conrado"],
        "error": "",
    },
    {
        "app": "processos",
        "label": "Process Manager",
        "container": "moya-processos",
        "username": "admin",
        "installed": True,
        "running": True,
        "exists": True,
        "is_superuser": True,
        "is_staff": True,
        "is_active": True,
        "usable_password": True,
        "last_login": None,
        "date_joined": None,
        "superusers": ["admin"],
        "error": "",
    },
]


def fake_agent():
    agente = Mock()
    agente.django_admin_status.return_value = {"enabled": True, "apps": APPS}
    agente.django_admin_ensure.return_value = {
        "app": "credenciais",
        "label": "Credenciais",
        "username": "admin",
        "created": True,
        "password_set": True,
        "password": "senha-unica-123",
        "message": "Superuser local criado.",
    }
    agente.django_admin_rotate.return_value = {
        "app": "processos",
        "label": "Process Manager",
        "username": "admin",
        "created": False,
        "password_set": True,
        "password": "senha-rotacionada-456",
        "message": "Senha do superuser local rotacionada.",
    }
    agente.host_capabilities.return_value = {
        "django_admin": True,
        "containers": True,
        "terminal_enable": False,
    }
    agente.df.return_value = {"volumes": []}
    agente.list_shares.return_value = []
    agente.snapshot_usage.return_value = []
    agente.storage_overview.return_value = {"disks": [], "raid": {}, "btrfs": {}}
    agente.backup_overview.return_value = {"disks": [], "jobs": []}
    agente.arquivos_jobs.return_value = {"jobs": [], "dir": ""}
    agente.versoes_schedule.return_value = {
        "per_day": 2,
        "first_time": "00:05",
        "times": ["00:05", "12:05"],
        "label": "2x/dia",
    }
    agente.health_overview.return_value = {"alerts": [], "volumes": [], "ok": True}
    return agente


class DjangoAdminsWebTests(TestCase):
    def setUp(self):
        self.root = get_user_model().objects.create_superuser(
            "root", "root@moya.local", "test-password"
        )
        self.user = get_user_model().objects.create_user(
            "tester", password="test-password"
        )
        self.agente = fake_agent()
        patcher = patch.object(core_views, "agent", self.agente)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(context_processors, "agent", self.agente)
        patcher.start()
        self.addCleanup(patcher.stop)
        context_processors._cached_caps = None
        context_processors._cached_at = 0.0

    def test_pagina_exige_superuser(self):
        self.client.force_login(self.user)
        resposta = self.client.get(reverse("django_admins"))
        self.assertEqual(resposta.status_code, 403)
        self.agente.django_admin_status.assert_not_called()

    def test_pagina_lista_apps_para_superuser(self):
        self.client.force_login(self.root)
        resposta = self.client.get(reverse("django_admins"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Admins locais")
        self.assertContains(resposta, "Credenciais")
        self.assertContains(resposta, "Process Manager")
        self.assertContains(resposta, "senha utilizável")
        self.agente.django_admin_status.assert_called_once()

    def test_ensure_mostra_senha_uma_vez_sem_auditar_o_segredo(self):
        self.client.force_login(self.root)
        resposta = self.client.post(
            reverse("django_admin_action"),
            {"acao": "ensure", "app": "credenciais"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "senha-unica-123")
        self.assertTrue(resposta["Cache-Control"].startswith("no-store"))
        self.agente.django_admin_ensure.assert_called_once_with("credenciais")
        log = AuditLog.objects.get(action="django_admin.ensure")
        self.assertEqual(log.target, "credenciais:admin")
        self.assertNotIn("senha-unica-123", log.detail)

    def test_rotate_exige_confirmacao_do_app(self):
        self.client.force_login(self.root)
        resposta = self.client.post(
            reverse("django_admin_action"),
            {"acao": "rotate", "app": "processos"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.agente.django_admin_rotate.assert_not_called()

        resposta = self.client.post(
            reverse("django_admin_action"),
            {"acao": "rotate", "app": "processos", "confirmation": "processos"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "senha-rotacionada-456")
        self.agente.django_admin_rotate.assert_called_once_with("processos")

    def test_acao_de_nao_superuser_bloqueada(self):
        self.client.force_login(self.user)
        resposta = self.client.post(
            reverse("django_admin_action"),
            {"acao": "ensure", "app": "credenciais"},
        )
        self.assertEqual(resposta.status_code, 403)
        self.agente.django_admin_ensure.assert_not_called()

    def test_acao_invalida_nao_chama_o_agente(self):
        self.client.force_login(self.root)
        resposta = self.client.post(
            reverse("django_admin_action"),
            {"acao": "apagar", "app": "credenciais"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.agente.django_admin_ensure.assert_not_called()
        self.agente.django_admin_rotate.assert_not_called()

    @override_settings(DJANGO_ADMIN_MANAGE=False)
    def test_flag_desliga_pagina_e_acoes(self):
        self.client.force_login(self.root)
        resposta = self.client.get(reverse("django_admins"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Gestão desativada")
        self.agente.django_admin_status.assert_not_called()

        resposta = self.client.post(
            reverse("django_admin_action"),
            {"acao": "ensure", "app": "credenciais"},
        )
        self.assertEqual(resposta.status_code, 302)
        self.agente.django_admin_ensure.assert_not_called()

    def test_menu_so_aparece_para_superuser(self):
        self.client.force_login(self.root)
        resposta = self.client.get(reverse("dashboard"))
        self.assertContains(resposta, reverse("django_admins"))

        self.client.force_login(self.user)
        resposta = self.client.get(reverse("dashboard"))
        self.assertNotContains(resposta, reverse("django_admins"))

    def test_erro_do_agente_aparece_na_pagina(self):
        self.agente.django_admin_status.side_effect = core_views.AgentError(
            "agente fora"
        )
        self.client.force_login(self.root)
        resposta = self.client.get(reverse("django_admins"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "agente fora")

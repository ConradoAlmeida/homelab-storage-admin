from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db

CFG = dict(
    CREDENTIALS_URL="http://credenciais",
    CREDENTIALS_API_TOKEN="segredo",
    CREDENTIALS_APP="storage",
)


@override_settings(**CFG)
def test_sessao_autorizada_abre():
    pessoa = get_user_model().objects.create_user("nome.sobrenome", password="x")
    cliente = Client()
    cliente.force_login(pessoa)
    with patch(
        "core.middleware.sessao",
        return_value={"ok": True, "ativo": True, "autorizado": True},
    ):
        assert cliente.get("/").status_code == 200


@override_settings(**CFG)
def test_sessao_revogada_derruba():
    pessoa = get_user_model().objects.create_user("nome.sobrenome", password="x")
    cliente = Client()
    cliente.force_login(pessoa)
    with patch(
        "core.middleware.sessao",
        return_value={"ok": True, "ativo": True, "autorizado": False},
    ):
        resposta = cliente.get("/")
    assert resposta.status_code == 302
    assert resposta.url.startswith("/login/")


@override_settings(**CFG)
def test_admin_local_ignora_credenciais():
    admin = get_user_model().objects.create_superuser("admin", "a@moya.local", "x")
    cliente = Client()
    cliente.force_login(admin)
    with patch("core.middleware.sessao", return_value={"ok": False}):
        assert cliente.get("/").status_code == 200

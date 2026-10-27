from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db


@override_settings(
    ROOT_URLCONF="tests.urls_credenciais",
    CREDENTIALS_URL="http://credenciais",
    CREDENTIALS_API_TOKEN="segredo",
    CREDENTIALS_APP="storage",
)
def test_login_aceito_cria_usuario_local():
    with patch(
        "core.auth.consultar",
        return_value={"ok": True, "username": "nome.sobrenome", "apps": ["storage"]},
    ):
        resposta = Client().post(
            "/login/", {"username": "nome.sobrenome", "password": "secreta"}
        )
    assert resposta.status_code == 302
    pessoa = get_user_model().objects.get(username="nome.sobrenome")
    assert not pessoa.has_usable_password()


@override_settings(
    ROOT_URLCONF="tests.urls_credenciais",
    CREDENTIALS_URL="http://credenciais",
    CREDENTIALS_API_TOKEN="segredo",
    CREDENTIALS_APP="storage",
)
def test_login_sem_storage_e_negado():
    with patch(
        "core.auth.consultar",
        return_value={"ok": True, "username": "nome.sobrenome", "apps": ["drawings"]},
    ):
        resposta = Client().post(
            "/login/", {"username": "nome.sobrenome", "password": "secreta"}
        )
    assert resposta.status_code == 200
    assert "não tem acesso" in resposta.content.decode("utf-8")


@override_settings(
    ROOT_URLCONF="tests.urls_credenciais",
    CREDENTIALS_URL="http://credenciais",
    CREDENTIALS_API_TOKEN="segredo",
    CREDENTIALS_APP="storage",
)
def test_login_com_senha_temporaria_nao_abre():
    with patch(
        "core.auth.consultar",
        return_value={"ok": False, "motivo": "trocar_senha"},
    ):
        resposta = Client().post(
            "/login/", {"username": "nome.sobrenome", "password": "temporaria"}
        )
    assert resposta.status_code == 200
    assert "temporária" in resposta.content.decode("utf-8")


@override_settings(
    ROOT_URLCONF="tests.urls_credenciais",
    CREDENTIALS_URL="http://credenciais",
    CREDENTIALS_API_TOKEN="segredo",
    CREDENTIALS_APP="storage",
)
def test_credenciais_fora_nao_abre():
    with patch("core.auth.consultar", return_value={"ok": False, "motivo": "fora"}):
        resposta = Client().post(
            "/login/", {"username": "nome.sobrenome", "password": "secreta"}
        )
    assert resposta.status_code == 200
    assert "não respondeu" in resposta.content.decode("utf-8")


@override_settings(
    ROOT_URLCONF="tests.urls_credenciais",
    CREDENTIALS_URL="http://credenciais",
    CREDENTIALS_API_TOKEN="segredo",
    CREDENTIALS_APP="storage",
)
def test_admin_local_funciona_como_emergencia():
    get_user_model().objects.create_superuser("admin", "a@moya.local", "senha-admin-forte")
    cliente = Client()
    with patch("core.auth.consultar", return_value={"ok": False, "motivo": "fora"}):
        resposta = cliente.post(
            "/login/", {"username": "admin", "password": "senha-admin-forte"}
        )
    assert resposta.status_code == 302
    assert "_auth_user_id" in cliente.session

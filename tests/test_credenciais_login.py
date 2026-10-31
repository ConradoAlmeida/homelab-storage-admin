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
def test_login_do_moya_pede_a_conta_do_credenciais():
    pagina = Client().get("/login/")
    texto = pagina.content.decode("utf-8")
    assert "mesma conta do Credenciais" in texto
    assert "conta deste servidor" not in texto


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


@override_settings(
    ROOT_URLCONF="tests.urls_credenciais",
    CREDENTIALS_URL="",
    CREDENTIALS_API_TOKEN="",
)
def test_login_local_quando_credenciais_nao_esta_no_host():
    get_user_model().objects.create_user("conrado", password="senha-local-forte")
    cliente = Client()
    pagina = cliente.get("/login/")
    texto = pagina.content.decode("utf-8")
    assert "Credenciais" not in texto
    assert "conta deste servidor" in texto
    with patch("core.auth.consultar") as consultar:
        resposta = cliente.post(
            "/login/", {"username": "conrado", "password": "senha-local-forte"}
        )
    consultar.assert_not_called()
    assert resposta.status_code == 302

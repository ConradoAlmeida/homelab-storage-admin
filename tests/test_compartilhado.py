import pytest
from django.test import Client, override_settings
from django.urls import reverse

ROTAS = (
    "user_create",
    "group_create",
    "user_password",
    "user_groups",
    "user_toggle",
    "user_delete",
    "group_delete",
)


@pytest.mark.parametrize("name", ROTAS)
@override_settings(
    CREDENTIALS_URL="http://credenciais",
    CREDENTIALS_API_TOKEN="segredo",
    CREDENTIALS_APP="storage",
    CREDENTIALS_MANAGE_USERS=False,
)
def test_rotas_continuam_existindo_no_pi(name):
    """O Storage Admin é compartilhado com o Pi: não remove features por ambiente."""
    assert reverse(name)


@override_settings(
    CREDENTIALS_URL="http://credenciais",
    CREDENTIALS_API_TOKEN="segredo",
    CREDENTIALS_APP="storage",
    CREDENTIALS_MANAGE_USERS=True,
)
def test_moya_bloqueia_apenas_identidade():
    cliente = Client()
    for caminho in (
        "/usuarios/novo/",
        "/usuarios/senha/",
        "/usuarios/toggle/",
        "/usuarios/excluir/",
        "/usuarios/grupos/",
    ):
        assert cliente.get(caminho).status_code == 404, caminho
    # Grupo é operação de servidor e continua disponível (redireciona para login).
    assert cliente.get("/usuarios/grupos/novo/").status_code == 302

import pytest
from django.test import override_settings
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
)
def test_gestao_de_usuarios_continua_existindo(name):
    """O Storage Admin é compartilhado com o Pi: não remover features por ambiente."""
    assert reverse(name)

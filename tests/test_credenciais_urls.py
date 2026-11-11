from django.test import SimpleTestCase, override_settings

from core.credenciais import painel_base, urls_usuario


@override_settings(CREDENTIALS_BROWSER_URL="https://credenciais.exemplo")
def test_urls_usuario_usa_browser_url():
    links = urls_usuario("conrado")
    assert links["senha"] == "https://credenciais.exemplo/usuarios/senha/?username=conrado"
    assert links["grupos"].endswith("username=conrado")


class CredenciaisPainelBaseTests(SimpleTestCase):
    @override_settings(CREDENTIALS_BROWSER_URL="", CREDENTIALS_URL="http://moya-credenciais:8080")
    def test_ignora_hostname_interno(self):
        assert painel_base() == ""

    @override_settings(CREDENTIALS_BROWSER_URL="", CREDENTIALS_URL="http://credenciais")
    def test_fallback_para_url_utilizavel(self):
        assert painel_base() == "http://credenciais"

from __future__ import annotations

from pathlib import Path

import pytest

from core.homelab_config import (
    ConfigError,
    carregar,
    carregar_arquivo,
    render_host_env,
    render_sync_env,
    requisitos,
    slugs,
    texto_host_env,
    texto_sync_env,
)

from .conftest import ROOT, parse_env_file

FIXTURES = Path(__file__).parent / "fixtures"
CHAVES_NOVAS = {"HOST_PROFILE"}


def env_efetivo(slug: str) -> dict[str, str]:
    return parse_env_file(FIXTURES / f"host.env.{slug}")


def test_slugs_lista_os_hosts_versionados():
    assert slugs() == ["moya", "pi"]


@pytest.mark.parametrize("slug", ["pi", "moya"])
def test_render_reproduz_o_host_env_efetivo(slug):
    rendered = dict(render_host_env(carregar(slug)))
    efetivo = env_efetivo(slug)

    # Toda chave que existia continua com o mesmo valor...
    assert {k: rendered.get(k) for k in efetivo} == efetivo
    # ...e o render so acrescenta o perfil explicito (fim do chute pelo diretorio).
    assert set(rendered) - set(efetivo) == CHAVES_NOVAS
    assert rendered["HOST_PROFILE"] == slug


@pytest.mark.parametrize("slug", ["pi", "moya"])
def test_texto_host_env_e_relegivel(slug, tmp_path):
    destino = tmp_path / "host.env"
    destino.write_text(texto_host_env(carregar(slug)), encoding="utf-8")
    assert parse_env_file(destino) == {**env_efetivo(slug), "HOST_PROFILE": slug}


def test_sync_env_do_pi():
    dados = dict(render_sync_env(carregar("pi")))
    assert dados["SCHEME"] == "https"
    assert dados["DOMAIN"] == "conradhub.com"
    assert dados["DNS_IP"] == "192.168.0.150"
    assert dados["DNS_MODE"] == "wildcard"
    assert dados["DNS_CONF"].endswith("10-conradhub.com-wildcard.conf")
    assert dados["CADDY_CONTAINER"] == "caddy"
    assert dados["CADDY_TLS"] == "import cf"
    assert dados["CADDY_PROXY"] == "import proxy"
    assert dados["CADDY_PORTA"] == ""
    assert dados["UPSTREAM_HOST"] == "192.168.0.150"
    assert dados["QUARANTINE"] == "/opt/stacks/_removidos"
    assert dados["SCAN_ROOTS"] == "/opt"
    assert dados["DIRS_PERMITIDOS"] == "/opt/stacks /opt"
    assert dados["PORTAL_INI"] == ""
    assert dados["SERVICES_INI"] == (
        "/mnt/nas/apps/homelab-storage-admin/data/services.ini"
    )


def test_sync_env_do_moya():
    dados = dict(render_sync_env(carregar("moya")))
    assert dados["SCHEME"] == "http"
    assert dados["DOMAIN"] == "local"
    assert dados["DNS_IP"] == "192.168.0.10"
    assert dados["DNS_MODE"] == "nome"
    assert dados["DNS_CONF"] == (
        "/home/conrado/pihole/etc-dnsmasq.d/10-apps-local.conf"
    )
    assert dados["CADDY_CONTAINER"] == "moya-caddy"
    assert dados["CADDY_PORTA"] == ":80"
    assert dados["CADDY_TLS"] == ""
    assert dados["CADDY_PROXY"] == "reverse_proxy"
    assert dados["UPSTREAM_HOST"] == "localhost"
    assert dados["QUARANTINE"] == "/home/conrado/_removidos"
    assert dados["SCAN_ROOTS"] == "/opt /home/conrado"
    assert dados["PORTAL_INI"] == "/var/lib/homelab-storage-admin/apps-portal.ini"
    assert dados["SERVICES_INI"] == (
        "/opt/stacks/homelab-storage-admin/data/services.ini"
    )


def test_texto_sync_env_escapa_valor_com_espaco():
    texto = texto_sync_env(carregar("pi"))
    assert "CADDY_TLS='import cf'" in texto
    assert "CADDY_PROXY='import proxy'" in texto
    # Vazio vira '' para o `source` nao depender do que veio antes.
    assert "CADDY_PORTA=''" in texto


def test_sync_env_sem_portal_fica_vazio():
    # Host sem portal (Pi) nao pode herdar o caminho do moya.
    assert dict(render_sync_env(carregar("pi")))["PORTAL_INI"] == ""


BASE = (ROOT / "hosts" / "pi" / "host.toml").read_text(encoding="utf-8")


def _config_com(tmp_path: Path, troca: tuple[str, str]) -> Path:
    procurar, substituir = troca
    assert procurar in BASE, procurar
    arquivo = tmp_path / "host.toml"
    arquivo.write_text(BASE.replace(procurar, substituir), encoding="utf-8")
    return arquivo


@pytest.mark.parametrize(
    ("troca", "mensagem"),
    [
        (('dns_modo = "wildcard"', 'dns_modo = "inventado"'), "dns_modo"),
        (("bind_port = 8060", 'bind_port = "8060"'), "bind_port"),
        (('nome = "pi"', 'nome = "Pi!"'), "slug"),
        (('dados = "/mnt/nas"', 'dados = "mnt/nas"'), "absoluto"),
        (("samba = true", "samba = true\nsamba2 = true"), "desconhecidas"),
        (("samba = true", 'samba = "sim"'), "true/false"),
        (('esquema = "https"', 'esquema = "ftp"'), "esquema"),
        (('apps = "deploy/pi/apps.env"', 'apps = "/etc/apps.env"'), "relativo"),
        (('dir = "/opt/stacks/caddy"', 'dir = ""'), "caddy"),
        (("credenciais = false", "credenciais = true"), "credenciais"),
    ],
)
def test_validacao_recusa_config_ruim(tmp_path, troca, mensagem):
    arquivo = _config_com(tmp_path, troca)
    with pytest.raises(ConfigError) as exc:
        carregar_arquivo(arquivo)
    assert mensagem in str(exc.value)


def test_validacao_exige_as_secoes(tmp_path):
    arquivo = tmp_path / "host.toml"
    arquivo.write_text(BASE.split("[features]")[0], encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        carregar_arquivo(arquivo)
    assert "features" in str(exc.value)


def test_slug_do_diretorio_quando_falta_nome(tmp_path):
    arquivo = tmp_path / "outro" / "host.toml"
    arquivo.parent.mkdir()
    arquivo.write_text(BASE.replace('nome = "pi"\n', ""), encoding="utf-8")
    cfg = carregar_arquivo(arquivo)
    assert cfg.slug == "outro"


def test_sem_host_env_escrito_nao_ha_segredo(tmp_path):
    texto = texto_host_env(carregar("moya"))
    for proibido in ("SECRET", "PASSWORD", "API_TOKEN"):
        assert proibido not in texto


def test_requisitos_seguem_as_features_ligadas():
    dados = {nome: tipo for tipo, nome, _pacotes in requisitos(carregar("pi"))}
    assert dados.get("pdbedit") == "obrig"
    # Opcional: sem btrfs o snapshot cai no rsync, nao falha.
    assert dados.get("btrfs") == "opc"
    assert dados.get("smartctl") == "opc"


def test_requisitos_sem_feature_nao_pede_o_binario(tmp_path):
    arquivo = tmp_path / "host.toml"
    texto = BASE.replace("samba = true", "samba = false").replace(
        "restic = true", "restic = false"
    )
    arquivo.write_text(texto, encoding="utf-8")
    nomes = {nome for _tipo, nome, _pacote in requisitos(carregar_arquivo(arquivo))}
    assert "pdbedit" not in nomes
    assert "restic" not in nomes
    # As demais continuam.
    assert "ufw" in nomes

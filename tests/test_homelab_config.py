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
# O render passou a gravar 0 explicito nas features de UI (o default do
# settings e 1); so o Pi nao tinha DJANGO_ADMIN_MANAGE no host.env efetivo.
EXTRAS = {
    "pi": {"HOST_PROFILE", "DJANGO_ADMIN_MANAGE", "QBITTORRENT_ENABLE"},
    "moya": {"HOST_PROFILE"},
}


def env_efetivo(slug: str) -> dict[str, str]:
    return parse_env_file(FIXTURES / f"host.env.{slug}")


def test_slugs_lista_os_hosts_versionados():
    # A bancada cria hosts/generico dentro do clone; o que importa e que os
    # presets versionados aparecem.
    assert {"pi", "moya"} <= set(slugs())


@pytest.mark.parametrize("slug", ["pi", "moya"])
def test_render_reproduz_o_host_env_efetivo(slug):
    rendered = dict(render_host_env(carregar(slug)))
    efetivo = env_efetivo(slug)

    # Toda chave que existia continua com o mesmo valor...
    assert {k: rendered.get(k) for k in efetivo} == efetivo
    # ...e o render so acrescenta o perfil explicito e os zeros de feature.
    assert set(rendered) - set(efetivo) == EXTRAS[slug]
    assert rendered["HOST_PROFILE"] == slug


@pytest.mark.parametrize("slug", ["pi", "moya"])
def test_texto_host_env_e_relegivel(slug, tmp_path):
    destino = tmp_path / "host.env"
    destino.write_text(texto_host_env(carregar(slug)), encoding="utf-8")
    esperado = {**env_efetivo(slug), "HOST_PROFILE": slug}
    if slug == "pi":
        esperado["DJANGO_ADMIN_MANAGE"] = "0"
        esperado["QBITTORRENT_ENABLE"] = "1"
    assert parse_env_file(destino) == esperado


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
        "/mnt/data/apps/storage/data/services.ini"
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


def test_host_sem_feature_grava_zero_explicito(tmp_path):
    # O default do settings/agente e 1: host sem a feature precisa dizer 0,
    # senao herda o comportamento do Pi e mostra acao que nao funciona.
    texto = BASE.replace("ufw = true", "ufw = false").replace(
        "terminal = true", "terminal = false"
    )
    arquivo = tmp_path / "host.toml"
    arquivo.write_text(texto, encoding="utf-8")
    render = texto_host_env(carregar_arquivo(arquivo))
    assert "FIREWALL_MANAGE=0" in render
    assert "TERMINAL_ENABLE=0" in render
    assert "DJANGO_ADMIN_MANAGE=0" in render
    assert "CREDENTIALS_MANAGE_USERS=0" in render
    # Nada de credenciais no host sem a feature.
    assert "CREDENCIAIS_DB" not in render
    assert "FIREWALL_SAFE_PORTS" not in render


MINIMO = """\
[host]
schema = 1
nome = "mini"
ssh = "conrado@mini"
lan_ip = "10.0.0.2"
repo = "/opt/stacks/homelab-storage-admin"

[app]
site_name = "Mini Storage"
bind_addr = "10.0.0.2"

[caminhos]
dados = "/srv/dados"
backup = "/mnt/backup"

[armazenamento]
proprietario = "conrado"

[rotas]
apps = "deploy/mini/apps.env"

[features]
samba = false
"""


def test_defaults_nao_quebram_toml_minimo(tmp_path):
    # Chave nova com default nao obriga reescrever o host.toml de quem ja tem.
    arquivo = tmp_path / "host.toml"
    arquivo.write_text(MINIMO, encoding="utf-8")
    cfg = carregar_arquivo(arquivo)
    assert cfg.valor("app", "bind_port") == 8060
    assert cfg.valor("app", "compose_overlay") == ""
    assert cfg.valor("caminhos", "dados_app") == (
        "/srv/dados/apps/homelab-storage-admin/data"
    )
    assert cfg.valor("caminhos", "snapshots") == "/srv/dados/.snapshots"
    assert cfg.valor("caminhos", "quarentena") == "/opt/stacks/_removidos"
    assert cfg.valor("rotas", "dns_ip") == "10.0.0.2"
    assert cfg.valor("rotas", "dns_modo") == "nenhum"
    assert cfg.valor("rotas", "upstream") == "nenhum"

    host_env = texto_host_env(cfg)
    assert "COMPOSE_OVERLAY=\n" in host_env
    assert "FIREWALL_MANAGE=0" in host_env
    # Sem DNS gerenciado: nenhum caminho de Pi-hole no sync.env.
    sync_env = texto_sync_env(cfg)
    assert "DNS_MODE=nenhum" in sync_env
    assert "CADDY_CONTAINER=''" in sync_env


def test_schema_mais_novo_que_a_ferramenta_recusa(tmp_path):
    arquivo = tmp_path / "host.toml"
    arquivo.write_text(MINIMO.replace("schema = 1", "schema = 99"), encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        carregar_arquivo(arquivo)
    assert "schema 99" in str(exc.value)
    assert "atualize o repo" in str(exc.value)


def test_unit_de_boot_do_pi_vem_do_toml():
    from core.homelab_config import texto_unit

    gerado = texto_unit(carregar("pi"))
    versionado = (ROOT / "deploy" / "pi" / "homelab-compose.service").read_text(
        encoding="utf-8"
    )
    # A unit do Pi e dado, nao arquivo escrito a mao: IP, pasta e stacks saem
    # do TOML e o teste garante que o versionado nao driftou.
    assert gerado == versionado
    assert "inet 192.168.0.150/" in gerado
    assert "mnt-nas.mount" in gerado
    assert "cd /opt/stacks/pihole" in gerado


def test_host_sem_boot_nao_gera_unit():
    from core.homelab_config import texto_unit

    with pytest.raises(ConfigError) as exc:
        texto_unit(carregar("moya"))
    assert "[boot]" in str(exc.value)

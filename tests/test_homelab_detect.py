from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from core.homelab_config import carregar_arquivo, texto_host_env, texto_sync_env
from core.homelab_detect import DetectError, Sistema, detectar, propor, texto_toml

from .conftest import ROOT

FIXTURES = Path(__file__).parent / "fixtures" / "deteccao"

PRESENTES = {
    "pdbedit", "smbpasswd", "parted", "mkfs.ext4", "rsync", "restic",
    "smartctl", "ufw", "apt-get", "systemctl", "docker",
}


class Runner:
    """Devolve a fixture certa por comando: nada do host real entra no teste."""

    def __init__(self, containers: str = "containers.txt", comando: set[str] | None = None):
        self.containers = FIXTURES / containers
        self.presentes = PRESENTES if comando is None else comando

    def __call__(self, cmd: list[str]) -> str:
        if cmd[0] == "lsblk":
            return (FIXTURES / "lsblk.json").read_text()
        if cmd[0] == "findmnt":
            return (FIXTURES / "findmnt.json").read_text()
        if cmd[0] == "ip":
            return (FIXTURES / "ip-route.json").read_text()
        if cmd[0] == "docker":
            return self.containers.read_text()
        if cmd[:2] == ["sh", "-c"]:
            nome = cmd[2].rsplit(" ", 1)[-1]
            return f"/usr/bin/{nome}" if nome in self.presentes else ""
        return ""


@pytest.fixture(autouse=True)
def _hostname(monkeypatch):
    monkeypatch.setenv("HOSTNAME", "nas-lab")
    monkeypatch.setenv("USER", "conrado")
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.delenv("HOMELAB_REPO", raising=False)


def test_detecta_identidade_e_ip_da_lan():
    sistema = detectar(Runner())
    assert sistema.hostname == "nas-lab"
    assert sistema.usuario == "conrado"
    assert sistema.lan_ip == "192.168.0.50"
    assert sistema.repo == "/opt/stacks/homelab-storage-admin"


def test_discos_e_papeis_sugeridos():
    proposta = propor(detectar(Runner()))
    papeis = {d["device"]: d["papel"] for d in proposta["discos"]}
    # O disco de / nao tem papel: o app nao mexe no sistema.
    assert papeis["/dev/nvme0n1"] == []
    # O disco montado em /srv/samba e o dos dados.
    assert papeis["/dev/sda"] == ["dados"]
    # O USB sem montagem vira candidato a backup.
    assert papeis["/dev/sdb"] == ["backup"]


def test_proposta_gera_toml_valido(tmp_path):
    proposta = propor(detectar(Runner("containers-vazio.txt")))
    arquivo = tmp_path / "host.toml"
    arquivo.write_text(texto_toml(proposta), encoding="utf-8")
    cfg = carregar_arquivo(arquivo)
    assert cfg.slug == "nas-lab"
    assert cfg.valor("caminhos", "dados") == "/srv/samba"
    assert cfg.valor("armazenamento", "snapshot_backend") == "rsync"
    # Sem Caddy nem Pi-hole detectado: nada de proxy nem DNS.
    assert cfg.valor("rotas", "upstream") == "nenhum"
    assert cfg.valor("rotas", "dns_modo") == "nenhum"
    # Sem overlay: o host usa so o docker-compose.yml.
    assert cfg.valor("app", "compose_overlay") == ""

    host_env = texto_host_env(cfg)
    assert "COMPOSE_OVERLAY=\n" in host_env
    assert "CREDENTIALS_MANAGE_USERS=0" in host_env
    sync_env = texto_sync_env(cfg)
    assert "DNS_MODE=nenhum" in sync_env
    assert "CADDY_CONTAINER=''" in sync_env


def test_com_caddy_e_pihole_detectados():
    proposta = propor(detectar(Runner()))
    # A fixture tem moya-caddy e pihole no docker ps.
    cfg_texto = texto_toml(proposta)
    assert 'upstream = "localhost"' in cfg_texto
    assert 'dns_modo = "nome"' in cfg_texto
    assert 'container = "moya-caddy"' in cfg_texto
    assert 'pihole_container = "pihole"' in cfg_texto


def test_features_seguem_os_binarios_presentes():
    sem_samba = PRESENTES - {"pdbedit", "smbpasswd"}
    proposta = propor(detectar(Runner(comando=sem_samba)))
    assert proposta["features"]["samba"] is False
    assert proposta["features"]["ufw"] is True


def test_sem_ip_falha_com_mensagem():
    class SemRede(Runner):
        def __call__(self, cmd):
            return "" if cmd[0] == "ip" else super().__call__(cmd)

    with pytest.raises(DetectError) as exc:
        detectar(SemRede())
    assert "IP" in str(exc.value)


def test_proposta_nao_escreve_no_repo(tmp_path):
    antes = set(p.name for p in ROOT.iterdir())
    proposta = propor(detectar(Runner()))
    texto_toml(proposta)
    assert set(p.name for p in ROOT.iterdir()) == antes
    assert not (ROOT / "hosts" / "nas-lab").exists()


@pytest.mark.skipif(shutil.which("ip") is None, reason="host sem iproute2")
def test_cli_detect_imprime_toml():
    from .test_homelabctl import rodar

    resultado = rodar("detect", "--quieto")
    assert resultado.returncode == 0, resultado.stderr
    assert "[features]" in resultado.stdout
    assert "bind_port = 8060" in resultado.stdout

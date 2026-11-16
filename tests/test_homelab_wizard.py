from __future__ import annotations

from pathlib import Path

import pytest

from core.homelab_config import ConfigError, carregar_arquivo
from core.homelab_wizard import (
    aplicar,
    caminho_do_host,
    executar,
    perguntas,
    salvar,
    sequencial,
    validar,
)

BASE = {
    "host": {
        "nome": "nas-lab",
        "descricao": "lab",
        "ssh": "conrado@nas-lab",
        "lan_ip": "192.168.0.50",
        "repo": "/opt/stacks/homelab-storage-admin",
    },
    "app": {
        "site_name": "NAS Lab",
        "bind_addr": "192.168.0.50",
        "bind_port": 8060,
        "compose_overlay": "",
    },
    "caminhos": {
        "dados": "/srv/samba",
        "snapshots": "/srv/samba/.snapshots",
        "backup": "/mnt/backup",
        "dados_app": "/srv/samba/apps/homelab-storage-admin/data",
        "stacks": "/opt",
        "quarentena": "/opt/stacks/_removidos",
        "estado": "/var/lib/homelab-storage-admin",
        "sockets": "/run/homelab-storage-admin",
        "config": "/etc/homelab-storage-admin",
    },
    "armazenamento": {
        "proprietario": "conrado",
        "snapshot_backend": "auto",
        "snapshot_denylist": "",
        "prefixos_permitidos": ["/srv/samba"],
        "mounts": ["/", "/srv/samba"],
        "firewall_safe_ports": ["22/tcp"],
    },
    "rotas": {
        "esquema": "http",
        "apps": "deploy/nas-lab/apps.env",
        "dominio": "local",
        "dns_ip": "192.168.0.50",
        "dns_modo": "nenhum",
        "dns_conf": "/opt/stacks/pihole/etc-dnsmasq.d/10-nas-lab-local.conf",
        "pihole_dir": "/opt/stacks/pihole",
        "pihole_container": "pihole",
        "upstream": "nenhum",
        "dirs_permitidos": ["/opt/stacks", "/opt"],
        "scan_roots": ["/opt"],
        "caddy": {},
    },
    "discos": [],
    "features": {"samba": True, "restic": False},
}


def test_trocar_dados_acerta_os_caminhos_derivados():
    nova = aplicar(BASE, {"caminhos.dados": "/mnt/dados/"})
    assert nova["caminhos"]["dados"] == "/mnt/dados/"
    assert nova["caminhos"]["snapshots"] == "/mnt/dados/.snapshots"
    assert nova["caminhos"]["dados_app"] == (
        "/mnt/dados/apps/homelab-storage-admin/data"
    )
    assert nova["armazenamento"]["prefixos_permitidos"] == ["/mnt/dados"]
    # A proposta original nao e mutada (a TUI pode cancelar depois de editar).
    assert BASE["caminhos"]["dados"] == "/srv/samba"


def test_slug_vira_o_caminho_do_apps_env():
    nova = aplicar(BASE, {"host.nome": "nas2"})
    assert nova["rotas"]["apps"] == "deploy/nas2/apps.env"


def test_porta_invalida_volta_para_o_padrao():
    # A UI nao tem campo para a porta, mas a proposta pode vir de outra fonte.
    BASE_COM_PORTA = {**BASE, "app": {**BASE["app"], "bind_port": "abc"}}
    assert aplicar(BASE_COM_PORTA, {})["app"]["bind_port"] == 8060


def test_feature_editada_no_wizard():
    nova = aplicar(BASE, {"feature.samba": False, "feature.gitea": True})
    assert nova["features"]["samba"] is False
    assert nova["features"]["gitea"] is True


def test_validar_aponta_o_campo_errado():
    erros = validar(aplicar(BASE, {"caminhos.dados": "srv/sem-barra"}))
    assert erros
    assert "absoluto" in erros[0]


def test_salvar_recusa_sobrescrever_sem_flag(tmp_path):
    salvar(BASE, raiz=tmp_path)
    destino = caminho_do_host("nas-lab", tmp_path)
    assert destino.is_file()
    with pytest.raises(ConfigError) as exc:
        salvar(BASE, raiz=tmp_path)
    assert "ja existe" in str(exc.value)


def test_salvar_grava_toml_valido(tmp_path):
    destino = salvar(aplicar(BASE, {"host.nome": "outro"}), raiz=tmp_path)
    assert destino == tmp_path / "outro" / "host.toml"
    cfg = carregar_arquivo(destino)
    assert cfg.slug == "outro"
    assert cfg.valor("rotas", "apps") == "deploy/outro/apps.env"


def test_salvar_recusa_proposta_invalida(tmp_path):
    with pytest.raises(ConfigError):
        salvar(aplicar(BASE, {"rotas.dns_modo": "inventado"}), raiz=tmp_path)
    assert not list(tmp_path.rglob("host.toml"))


def test_perguntas_mostram_o_valor_atual():
    respostas = perguntas(BASE)
    assert respostas["host.nome"] == "nas-lab"
    assert respostas["caminhos.dados"] == "/srv/samba"
    assert len(respostas) == len(perguntas(BASE))


def test_sequencial_mantem_o_padrao_com_enter():
    respostas = sequencial(BASE, perguntar=lambda _p: "")
    assert respostas == {}


def test_sequencial_aceita_troca_e_desliga_features():
    roteiro = iter(["nas2"] + [""] * 11 + ["n"])
    respostas = sequencial(BASE, perguntar=lambda _p: next(roteiro))
    assert respostas["host.nome"] == "nas2"
    assert respostas["feature.samba"] == "0"
    assert respostas["feature.restic"] == "0"


def test_executar_usa_a_tui_injetada():
    chamadas = []

    def tui(proposta):
        chamadas.append(proposta["host"]["nome"])
        return {"host.nome": "editado"}

    assert executar(BASE, tui=tui) == {"host.nome": "editado"}
    assert chamadas == ["nas-lab"]


def test_executar_cancelado_devolve_none():
    assert executar(BASE, tui=lambda _p: None) is None


def test_tui_monta_e_grava_editado(monkeypatch):
    import asyncio
    import importlib.util

    if importlib.util.find_spec("textual") is None:
        pytest.skip("textual nao instalado (extras de setup)")

    from core.homelab_wizard import criar_app

    async def cenario():
        app = criar_app(BASE)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#campo-host-nome").value = "pelo-wizard"
            app.query_one("#feature-restic").value = True
            app.query_one("#gravar").press()
            await pilot.pause()
        return app.resultado

    resultado = asyncio.run(cenario())
    assert resultado["host.nome"] == "pelo-wizard"
    assert resultado["feature.restic"] is True
    assert resultado["feature.samba"] is True

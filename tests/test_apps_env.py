from __future__ import annotations

from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from core.apps_env import (
    apps_do_env,
    le_declarado,
    le_estado,
    nome_padrao,
    resumo,
)

ROOT = Path(__file__).resolve().parent.parent

ENV = """\
# comentario
homelab|homelab.conradhub.com|192.168.0.150:8060|/opt/stacks/homelab-storage-admin|

dockge|dockge.conradhub.com|192.168.0.150:5001|/opt/dockge|atalho=painel,nome=Dockge,descricao=Containers,cor=#fbbf24,icone=dockge
jellyfin|jellyfin.conradhub.com|127.0.0.1:8096|/opt/stacks/jellyfin|snippet=jellyfin,atalho=painel
portal|app.local|10.0.0.2:80|-|atalho=portal,nome=Portal,grupo=tools
ambos|ambos.local|10.0.0.3:81|-|redir=/admin/,atalho=painel+portal,grupo=infrastructure
sem|sem.local|10.0.0.4:82|-|atalho=nao
quebrada|faltando-local|
"""

ESTADO = (
    "dockge|dockge.conradhub.com|192.168.0.150:5001|/opt/dockge|"
    "atalho=painel,nome=Dockge,descricao=Containers,cor=#fbbf24,icone=dockge\n"
    # Linha velha: o env mudou depois do ultimo --apply.
    "jellyfin|jellyfin.conradhub.com|127.0.0.1:9999|/opt/stacks/jellyfin|snippet=jellyfin\n"
    "sumiu|sumiu.local|10.0.0.9:90|-|atalho=portal\n"
)


def _escreve(tmp_path: Path, env: str = ENV, estado: str | None = None) -> tuple[Path, Path]:
    env_file = tmp_path / "apps.env"
    env_file.write_text(env, encoding="utf-8")
    estado_file = tmp_path / "apps.aplicados"
    if estado is not None:
        estado_file.write_text(estado, encoding="utf-8")
    return env_file, estado_file


def _apps(tmp_path: Path, estado: str | None = None, scheme: str = "https"):
    env_file, estado_file = _escreve(tmp_path, estado=estado)
    return apps_do_env(env=env_file, estado=estado_file, scheme=scheme)


def test_ignora_comentarios_e_marca_linha_incompleta(tmp_path):
    env_file, _ = _escreve(tmp_path)
    linhas = le_declarado(env_file, scheme="https")
    assert [linha.key for linha in linhas] == [
        "homelab",
        "dockge",
        "jellyfin",
        "portal",
        "ambos",
        "sem",
        "quebrada",
    ]
    # A linha incompleta e marcada, nao derruba o resto.
    assert linhas[-1].erro
    assert "5 campos" in linhas[-1].erro


def test_flags_viram_campos(tmp_path):
    env_file, _ = _escreve(tmp_path)
    linhas = {linha.key: linha for linha in le_declarado(env_file, scheme="http")}
    assert linhas["dockge"].campos["cor"] == "#fbbf24"
    assert linhas["dockge"].campos["atalho"] == "painel"
    assert linhas["ambos"].campos["redir"] == "/admin/"
    assert linhas["homelab"].flags == ""


def test_arquivo_ausente_devolve_vazio():
    assert le_declarado("/nao/existe/apps.env", scheme="https") == []
    assert le_estado("/nao/existe/apps.aplicados") == {}


def test_nome_padrao_igual_ao_script():
    # apps-sync: base do fqdn, hifen vira espaco, so a primeira letra sobe.
    assert nome_padrao("moya-versoes.local") == "Moya versoes"
    assert nome_padrao("dockge.conradhub.com") == "Dockge"


def test_estado_le_key_e_assinatura(tmp_path):
    estado_file = tmp_path / "apps.aplicados"
    estado_file.write_text(
        "# Gerado por scripts/stacks/apps-sync.sh\n"
        "dockge|dockge.conradhub.com|192.168.0.150:5001|/opt/dockge|atalho=painel\n",
        encoding="utf-8",
    )
    estado = le_estado(estado_file)
    assert estado["dockge"] == (
        "dockge.conradhub.com|192.168.0.150:5001|/opt/dockge|atalho=painel"
    )


def test_estados_aplicado_pendente_novo_e_fora_do_env(tmp_path):
    apps, fora, invalidas = _apps(tmp_path, estado=ESTADO)
    por_key = {app.key: app for app in apps}
    assert por_key["dockge"].estado == "aplicado"
    assert por_key["jellyfin"].estado == "pendente"
    assert por_key["homelab"].estado == "novo"
    assert [app.key for app in fora] == ["sumiu"]
    assert fora[0].estado == "fora do env"
    assert len(invalidas) == 1


def test_atalhos_e_grupo(tmp_path):
    apps, _, _ = _apps(tmp_path)
    por_key = {app.key: app for app in apps}
    assert por_key["dockge"].no_painel
    assert not por_key["dockge"].no_portal
    assert por_key["ambos"].no_painel and por_key["ambos"].no_portal
    assert por_key["ambos"].atalhos == ("painel", "portal")
    assert por_key["ambos"].grupo == "infrastructure"
    assert por_key["sem"].sem_atalho
    assert por_key["portal"].grupo == "tools"
    assert por_key["dockge"].grupo == "services"


def test_extras_da_rota(tmp_path):
    apps, _, _ = _apps(tmp_path)
    por_key = {app.key: app for app in apps}
    assert por_key["jellyfin"].extras == ("snippet=jellyfin",)
    assert por_key["ambos"].extras == ("redir=/admin/",)
    assert por_key["dockge"].extras == ()


def test_url_usa_o_esquema_do_host(tmp_path):
    apps, _, _ = _apps(tmp_path, scheme="http")
    por_key = {app.key: app for app in apps}
    assert por_key["dockge"].url == "http://dockge.conradhub.com"


def test_resumo(tmp_path):
    apps, _, _ = _apps(tmp_path)
    assert resumo(apps) == {
        "total": 6,
        "painel": 3,
        "portal": 2,
        "sem_atalho": 2,
        "pendentes": 6,
    }


def test_env_do_moya_real():
    env_file = ROOT / "deploy" / "moya" / "apps.env"
    apps, fora, invalidas = apps_do_env(
        env=env_file, estado="/nao/existe", scheme="http"
    )
    assert invalidas == []
    assert len(apps) == 12
    assert fora == []
    numeros = resumo(apps)
    assert numeros["painel"] == 2
    assert numeros["portal"] == 11
    assert numeros["sem_atalho"] == 1  # moya-portal nao aponta para si mesmo
    assert {app.grupo for app in apps if app.no_portal} == {
        "services",
        "infrastructure",
        "tools",
    }


def test_env_do_pi_real():
    env_file = ROOT / "deploy" / "pi" / "apps.env"
    apps, _, invalidas = apps_do_env(
        env=env_file, estado="/nao/existe", scheme="https"
    )
    assert invalidas == []
    assert [app.key for app in apps] == ["homelab", "dockge", "pihole", "jellyfin"]
    assert resumo(apps)["painel"] == 3
    assert resumo(apps)["portal"] == 0


def _cliente() -> Client:
    user = get_user_model().objects.create_user(
        username="rotas-t", password="test-password"
    )
    cliente = Client()
    cliente.force_login(user)
    return cliente


@pytest.mark.django_db
@override_settings(
    APPS_ENV_PATH="/opt/stacks/homelab-storage-admin/deploy/moya/apps.env",
    APPS_SCHEME="http",
)
def test_pagina_lista_as_apps(tmp_path):
    env_file, estado_file = _escreve(tmp_path, estado=ESTADO)
    with override_settings(
        APPS_ENV_FILE=str(env_file), APPS_STATE_FILE=str(estado_file)
    ):
        resp = _cliente().get("/sistema/rotas/")
    assert resp.status_code == 200
    html = resp.content.decode()
    for termo in (
        "Rotas e atalhos",
        "dockge",
        "Dockge",
        "http://dockge.conradhub.com",
        "aplicado",
        "pendente",
        "painel",
        "portal",
        "infrastructure",
        "snippet=jellyfin",
        "sem atalho",
        "Fora do env",
        "sumiu",
    ):
        assert termo in html, termo


@pytest.mark.django_db
def test_sem_env_nao_quebra(tmp_path):
    with override_settings(
        APPS_ENV_FILE=str(tmp_path / "nao-existe.env"),
        APPS_STATE_FILE=str(tmp_path / "nao-existe.estado"),
        APPS_ENV_PATH="",
    ):
        resp = _cliente().get("/sistema/rotas/")
    assert resp.status_code == 200
    assert "apps.env não encontrado" in resp.content.decode()


@pytest.mark.django_db
def test_linha_invalida_aparece_como_aviso(tmp_path):
    env_file, estado_file = _escreve(tmp_path, estado="")
    with override_settings(
        APPS_ENV_FILE=str(env_file), APPS_STATE_FILE=str(estado_file)
    ):
        resp = _cliente().get("/sistema/rotas/")
    html = resp.content.decode()
    assert resp.status_code == 200
    assert "linha inválida" in html
    assert "esperava 5 campos" in html


@pytest.mark.django_db
def test_sem_estado_avisa_que_nada_esta_aplicado(tmp_path):
    env_file, _ = _escreve(tmp_path)
    with override_settings(
        APPS_ENV_FILE=str(env_file),
        APPS_STATE_FILE=str(tmp_path / "apps.aplicados"),
    ):
        resp = _cliente().get("/sistema/rotas/")
    html = resp.content.decode()
    assert resp.status_code == 200
    assert "Estado do último" in html
    assert "novo" in html

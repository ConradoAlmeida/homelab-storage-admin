"""Caminhos de configuração no host e comando SSH para exibição.

A página Configuração separa o que se edita do que é artefato: o ``apps.env``
é o único arquivo do dia a dia (rotas, DNS e atalhos); ``host.env`` e o ``.env``
do stack mudam raramente; ``services.ini`` e a lista do portal são gerados pelo
``apps-sync`` e não se editam no host.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

HOST_ENV_PADRAO = "/etc/homelab-storage-admin/host.env"
STACK_ENV_PADRAO = "/opt/stacks/homelab-storage-admin/.env"


@dataclass(frozen=True)
class ArquivoConfig:
    nome: str
    caminho: str
    controlo: str
    vigencia: str


@dataclass(frozen=True)
class ArquivoGerado:
    nome: str
    caminho: str
    origem: str


def comando_ssh(
    *,
    ssh_login: str,
    share_owner: str,
    hostname: str | None,
) -> str:
    login = (ssh_login or "").strip()
    if login:
        return f"ssh {login}"
    owner = (share_owner or "conrado").strip() or "conrado"
    host = (hostname or "").strip()
    if host:
        return f"ssh {owner}@{host}"
    return f"ssh {owner}"


def perfil_do_env(apps_env: str, perfil: str = "") -> str:
    """Perfil do host: ``HOST_PROFILE`` ou, na falta dele, o diretorio.

    ``.../deploy/moya/apps.env`` -> ``moya``. Nao ha lista fixa: qualquer slug
    serve, desde que seja um nome simples (o render grava HOST_PROFILE, entao
    o caminho e so o fallback para host ainda nao migrado).
    """
    explicito = (perfil or "").strip()
    if explicito:
        return explicito
    caminho = Path((apps_env or "").strip())
    if caminho.name == "apps.env" and caminho.parent.parent.name == "deploy":
        return caminho.parent.name
    return ""


def comandos_do_env(apps_env: str, perfil: str = "") -> dict[str, str]:
    """Comandos reais do host, com `--perfil` so quando o script exige.

    O `apps-sync` assume o perfil `pi`; qualquer outro precisa do flag, e a
    tela mostra exatamente o que deve ser colado no terminal.
    """
    nome = perfil_do_env(apps_env, perfil)
    flag = f" --perfil {nome}" if nome and nome != "pi" else ""
    base = "sudo bash scripts/stacks/apps-sync.sh"
    return {
        "comando_apply": f"{base}{flag} --apply",
        "comando_doctor": f"{base}{flag} --doctor",
    }


def arquivos_config(
    *,
    host_env_path: str,
    stack_env_path: str,
    services_ini_host: str,
    credenciais_env: str,
    apps_env: str = "",
    perfil: str = "",
) -> dict:
    """``apps_env`` (editavel), ``arquivos`` (raros) e ``gerados`` (artefatos)."""
    apps = (apps_env or "").strip()
    principal = (
        ArquivoConfig(
            nome="apps.env",
            caminho=apps,
            controlo="Rotas do Caddy, DNS e atalhos do painel e do portal.",
            vigencia="Depois de git pull no host e do apps-sync --apply.",
        )
        if apps
        else None
    )

    raros = [
        ArquivoConfig(
            nome="host.env",
            caminho=host_env_path or HOST_ENV_PADRAO,
            controlo="Perfil do host (portas, prefixos, SSH, overlay do Compose).",
            vigencia="Após sudo ./install-agent.sh e ./deploy.sh.",
        ),
        ArquivoConfig(
            nome=".env",
            caminho=stack_env_path or STACK_ENV_PADRAO,
            controlo="Segredo do Django (SECRET_KEY e flags do app).",
            vigencia="Após ./deploy.sh.",
        ),
    ]
    cred = (credenciais_env or "").strip()
    if cred:
        raros.append(
            ArquivoConfig(
                nome=".env (Credenciais)",
                caminho=cred,
                controlo="Segredo do app Credenciais no moyaserver.",
                vigencia="Após alterar o ficheiro e reiniciar o Credenciais.",
            )
        )

    gerados = [
        ArquivoGerado(
            nome="services.ini",
            caminho=services_ini_host,
            origem="Atalhos do botão Serviços, gerados das flags atalho=painel.",
        ),
    ]
    return {
        "apps_env": principal,
        "arquivos": raros,
        "gerados": gerados,
        "perfil": perfil_do_env(apps, perfil),
        **comandos_do_env(apps, perfil),
    }


def contexto_config_locais(
    *,
    ssh_login: str,
    share_owner: str,
    hostname: str | None,
    host_env_path: str,
    stack_env_path: str,
    services_ini_host: str,
    credenciais_env: str,
    apps_env: str = "",
    perfil: str = "",
) -> dict:
    caminhos = arquivos_config(
        host_env_path=host_env_path,
        stack_env_path=stack_env_path,
        services_ini_host=services_ini_host,
        credenciais_env=credenciais_env,
        apps_env=apps_env,
        perfil=perfil,
    )
    return {
        "ssh_comando": comando_ssh(
            ssh_login=ssh_login,
            share_owner=share_owner,
            hostname=hostname,
        ),
        **caminhos,
        "tem_apps_env": caminhos["apps_env"] is not None,
    }

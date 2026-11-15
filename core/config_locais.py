"""Caminhos de configuração no host e comando SSH para exibição.

A página Configuração separa o que se edita do que é artefato: o ``apps.env``
é o único arquivo do dia a dia (rotas, DNS e atalhos); ``host.env`` e o ``.env``
do stack mudam raramente; ``services.ini`` e a lista do portal são gerados pelo
``apps-sync`` e não se editam no host.
"""

from __future__ import annotations

from dataclasses import dataclass

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


def arquivos_config(
    *,
    host_env_path: str,
    stack_env_path: str,
    services_ini_host: str,
    credenciais_env: str,
    apps_env: str = "",
) -> dict:
    """``apps_env`` (editavel), ``arquivos`` (raros) e ``gerados`` (artefatos)."""
    apps = (apps_env or "").strip()
    principal = (
        ArquivoConfig(
            nome="apps.env",
            caminho=apps,
            controlo="Rotas do Caddy, DNS e atalhos do painel e do portal.",
            vigencia="Após sudo scripts/stacks/apps-sync.sh --apply.",
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
    return {"apps_env": principal, "arquivos": raros, "gerados": gerados}


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
) -> dict:
    caminhos = arquivos_config(
        host_env_path=host_env_path,
        stack_env_path=stack_env_path,
        services_ini_host=services_ini_host,
        credenciais_env=credenciais_env,
        apps_env=apps_env,
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

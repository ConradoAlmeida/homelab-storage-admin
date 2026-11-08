"""Caminhos de configuração no host e comando SSH para exibição."""

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
) -> list[ArquivoConfig]:
    itens = [
        ArquivoConfig(
            nome="host.env",
            caminho=host_env_path or HOST_ENV_PADRAO,
            controlo="Perfil do host (prefixos, SSH, overlay do Compose).",
            vigencia="Após sudo ./install-agent.sh e ./deploy.sh.",
        ),
        ArquivoConfig(
            nome=".env",
            caminho=stack_env_path or STACK_ENV_PADRAO,
            controlo="Segredo do Django (SECRET_KEY e flags do app).",
            vigencia="Após ./deploy.sh.",
        ),
        ArquivoConfig(
            nome="services.ini",
            caminho=services_ini_host,
            controlo="Atalhos da home do painel.",
            vigencia="Ao recarregar a página (dashboard).",
        ),
    ]
    cred = (credenciais_env or "").strip()
    if cred:
        itens.append(
            ArquivoConfig(
                nome=".env (Credenciais)",
                caminho=cred,
                controlo="Segredo do app Credenciais no moyaserver.",
                vigencia="Após alterar o ficheiro e reiniciar o Credenciais.",
            )
        )
    return itens


def contexto_config_locais(
    *,
    ssh_login: str,
    share_owner: str,
    hostname: str | None,
    host_env_path: str,
    stack_env_path: str,
    services_ini_host: str,
    credenciais_env: str,
) -> dict:
    return {
        "ssh_comando": comando_ssh(
            ssh_login=ssh_login,
            share_owner=share_owner,
            hostname=hostname,
        ),
        "arquivos": arquivos_config(
            host_env_path=host_env_path,
            stack_env_path=stack_env_path,
            services_ini_host=services_ini_host,
            credenciais_env=credenciais_env,
        ),
    }

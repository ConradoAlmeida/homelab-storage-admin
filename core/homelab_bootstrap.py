"""`homelabctl bootstrap`: o que falta para o host rodar, em uma passada.

Nao instala o SO: assume Ubuntu com o repo clonado. Faz o que da para conferir e
gerar sem adivinhar -- `host.env`/`sync.env`, `.env` com segredo aleatorio,
dependencias por feature e a unit de boot. Sem `--escrever` so relata; sem
`--apt` so lista os pacotes. Nunca sobrescreve arquivo existente.
"""

from __future__ import annotations

import os
import secrets
import shlex
import shutil
import subprocess
from pathlib import Path

from .homelab_config import (
    RAIZ,
    ConfigError,
    HostConfig,
    render_host_env,
    render_sync_env,
    requisitos,
    texto_host_env,
    texto_sync_env,
)


def _escolhe(cfg: HostConfig, exemplo: str) -> str:
    """`.env` do exemplo, com segredo novo e os enderecos deste host."""
    lan_ip = str(cfg.valor("host", "lan_ip"))
    nome = str(cfg.valor("host", "nome") or cfg.slug)
    porta = cfg.valor("app", "bind_port")
    esquema = cfg.valor("rotas", "esquema")
    linhas: list[str] = []
    viu_segredo = False
    for linha in exemplo.splitlines():
        if linha.startswith("DJANGO_SECRET_KEY="):
            linha = "DJANGO_SECRET_KEY=" + secrets.token_hex(32)
            viu_segredo = True
        elif linha.startswith("DJANGO_ALLOWED_HOSTS="):
            linha = f"DJANGO_ALLOWED_HOSTS={lan_ip},{nome},localhost,127.0.0.1"
        elif linha.startswith("DJANGO_CSRF_TRUSTED_ORIGINS="):
            linha = (
                f"DJANGO_CSRF_TRUSTED_ORIGINS={esquema}://{lan_ip}:{porta},"
                f"http://{nome}:{porta},http://localhost:{porta},"
                f"http://127.0.0.1:{porta}"
            )
        linhas.append(linha)
    if not viu_segredo:
        raise ConfigError(
            f"{exemplo}: sem DJANGO_SECRET_KEY; o exemplo do repo esta incompleto"
        )
    return "\n".join(linhas) + "\n"


def _pacotes(cfg: HostConfig, which) -> list[str]:
    """Tokens de apt das features obrigatorias cujo binario falta."""
    vistos: list[str] = []
    for tipo, nome, pacotes in requisitos(cfg):
        if tipo != "obrig" or which(nome):
            continue
        for token in shlex.split(pacotes):
            if token not in vistos:
                vistos.append(token)
    return vistos


def _grava_novo(caminho: Path, texto: str, linhas: list[str]) -> None:
    if caminho.is_file():
        linhas.append(f"mantido: {caminho} (render --write troca de proposito)")
        return
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    caminho.chmod(0o644)
    linhas.append(f"escrito: {caminho}")


def preparar(
    cfg: HostConfig,
    *,
    escrever: bool = False,
    apt: bool = False,
    config_dir: Path | None = None,
    env_file: Path | None = None,
    repo: Path | None = None,
    which=shutil.which,
    executar=None,
    geteuid=None,
) -> list[str]:
    """Relata (e com `escrever`, grava) o que falta; devolve as linhas."""
    repo = Path(repo or cfg.valor("host", "repo") or RAIZ)
    config = Path(config_dir or cfg.valor("caminhos", "config"))
    env_file = Path(env_file or repo / ".env")
    geteuid = geteuid or os.geteuid
    linhas: list[str] = []

    for nome, texto in (
        ("host.env", texto_host_env(cfg)),
        ("sync.env", texto_sync_env(cfg)),
    ):
        caminho = config / nome
        if escrever:
            _grava_novo(caminho, texto, linhas)
        else:
            linhas.append(f"(sim) geraria {caminho}")

    if env_file.is_file():
        modo = env_file.stat().st_mode & 0o777
        if modo == 0o600:
            linhas.append(f"mantido: {env_file} (modo 600)")
        else:
            linhas.append(f"aviso: {env_file} com modo {modo:o}; use chmod 600")
    elif escrever:
        exemplo = repo / ".env.example"
        if not exemplo.is_file():
            raise ConfigError(f"falta {exemplo} para gerar o .env")
        texto = _escolhe(cfg, exemplo.read_text(encoding="utf-8"))
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text(texto, encoding="utf-8")
        env_file.chmod(0o600)
        linhas.append(f"escrito: {env_file} (segredo aleatorio; revise o admin)")
    else:
        linhas.append(f"(sim) geraria {env_file} a partir de .env.example")

    pacotes = _pacotes(cfg, which)
    if not pacotes:
        linhas.append("dependencias obrigatorias: presentes")
    elif not apt:
        linhas.append(f"faltam dependencias: apt install {' '.join(pacotes)}")
    elif geteuid() != 0:
        raise ConfigError(
            "apt install exige root: sudo python3 scripts/homelabctl.py "
            f"bootstrap {cfg.slug} --apt"
        )
    else:
        comando = ["apt-get", "install", "-y", *pacotes]
        linhas.append(f"apt install {' '.join(pacotes)}")
        (executar or (lambda cmd: subprocess.run(cmd, check=True)))(comando)

    chaves = len(render_host_env(cfg)) + len(render_sync_env(cfg))
    linhas += [
        f"env do host: {chaves} chaves (host.env + sync.env)",
        "proximos passos:",
        "  1. ./deploy.sh",
        "  2. sudo bash scripts/stacks/apps-sync.sh --apply",
        f"  3. python3 scripts/homelabctl.py doctor {cfg.slug}",
    ]
    if cfg.secao("boot"):
        linhas.append(
            "  unit de boot: python3 scripts/homelabctl.py boot "
            f"{cfg.slug} --write, depois instale em /etc/systemd/system"
        )
    linhas.append("  disco de dados e montagem continuam manuais (nada e formatado aqui).")
    return linhas

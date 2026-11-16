"""Preflight do host: le e diz o que impede o deploy.

Roda antes do `deploy.sh` num host novo e depois de mudar o TOML. Nada aqui
escreve: o conserto e sempre um comando impresso no achado (`render --write`,
`apt install`, `chmod 600`).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .homelab_config import (
    HostConfig,
    requisitos,
    texto_host_env,
    texto_sync_env,
    texto_unit,
)

# Segredo de exemplo do .env.example: valor que nunca deve ir para producao.
SEGREDOS_DE_EXEMPLO = {
    "troque-por-uma-chave-aleatoria-longa",
    "changeme",
    "secret",
    "",
}


@dataclass(frozen=True)
class Achado:
    nivel: str  # erro | aviso | ok
    mensagem: str


def _pares(texto: str) -> dict[str, str]:
    dados: dict[str, str] = {}
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        dados[chave] = valor.strip().strip("'\"")
    return dados


def _compara(caminho: Path, esperado: str, rotulo: str, slug: str) -> list[Achado]:
    if not caminho.is_file():
        return [
            Achado(
                "erro",
                f"falta {rotulo} ({caminho}); rode: python3 scripts/homelabctl.py "
                f"render {slug} --write --ambos",
            )
        ]
    instalado = _pares(caminho.read_text(encoding="utf-8"))
    novo = _pares(esperado)
    if instalado == novo:
        return [Achado("ok", f"{rotulo} em sync com o host.toml")]
    diferentes = sorted(
        chave
        for chave in set(instalado) | set(novo)
        if instalado.get(chave) != novo.get(chave)
    )
    return [
        Achado(
            "erro",
            f"{rotulo} difere do host.toml ({', '.join(diferentes[:4])}"
            f"{'...' if len(diferentes) > 4 else ''}); rode: "
            f"python3 scripts/homelabctl.py render {slug} --write --ambos",
        )
    ]


def _checa_env(caminho: Path) -> list[Achado]:
    if not caminho.is_file():
        return [Achado("erro", f"falta {caminho}; copie de .env.example")]
    achados: list[Achado] = []
    modo = caminho.stat().st_mode & 0o777
    if modo != 0o600:
        achados.append(
            Achado("erro", f"{caminho} com modo {modo:o} (tem segredo); chmod 600")
        )
    segredo = _pares(caminho.read_text(encoding="utf-8")).get("DJANGO_SECRET_KEY", "")
    if segredo in SEGREDOS_DE_EXEMPLO:
        achados.append(
            Achado("erro", f"{caminho}: DJANGO_SECRET_KEY vazio ou de exemplo; "
                           "gere com openssl rand -hex 32")
        )
    if not achados:
        achados.append(Achado("ok", f"{caminho} com segredo e modo 600"))
    return achados


def analisar(
    cfg: HostConfig,
    *,
    config_dir: Path | None = None,
    env_file: Path | None = None,
    which=shutil.which,
    montado=os.path.ismount,
    unit_dir: Path | None = None,
) -> list[Achado]:
    """Lista de achados do host; erro = nao deploye antes de resolver."""
    config = Path(config_dir or cfg.valor("caminhos", "config"))
    repo = Path(cfg.valor("host", "repo") or "/")
    achados: list[Achado] = []

    achados += _compara(config / "host.env", texto_host_env(cfg), "host.env", cfg.slug)
    achados += _compara(config / "sync.env", texto_sync_env(cfg), "sync.env", cfg.slug)

    obrigatorios = [r for r in requisitos(cfg) if r[0] == "obrig"]
    opcionais = [r for r in requisitos(cfg) if r[0] == "opc"]
    faltando = [r for r in obrigatorios if not which(r[1])]
    for _tipo, nome, pacotes in faltando:
        achados.append(
            Achado("erro", f"falta '{nome}' (feature ligada); apt install {pacotes}")
        )
    for _tipo, nome, pacotes in opcionais:
        if not which(nome):
            achados.append(
                Achado("aviso", f"'{nome}' ausente; o recurso fica escondido "
                                f"(apt install {pacotes})")
            )
    if not faltando:
        achados.append(Achado("ok", "dependencias obrigatorias presentes"))

    achados += _checa_env(Path(env_file or repo / ".env"))

    for ponto in cfg.valor("armazenamento", "mounts") or ():
        caminho = Path(str(ponto))
        if not caminho.exists():
            achados.append(Achado("erro", f"mount {ponto} nao existe"))
        elif str(ponto) != "/" and not montado(caminho):
            achados.append(
                Achado("aviso", f"{ponto} existe mas nao e ponto de montagem")
            )

    if not which("docker"):
        achados.append(
            Achado("aviso", "docker fora do PATH; o deploy.sh nao roda sem ele")
        )

    apps_env = repo / str(cfg.valor("rotas", "apps"))
    if apps_env.is_file():
        achados.append(Achado("ok", f"apps.env presente ({apps_env})"))
    else:
        achados.append(Achado("erro", f"falta {apps_env}"))

    if cfg.secao("boot"):
        unidade = str(cfg.valor("boot", "unit"))
        instalada = Path(unit_dir or "/etc/systemd/system") / unidade
        if not instalada.is_file():
            achados.append(
                Achado("aviso", f"unit {unidade} nao instalada; "
                                f"sudo install -m 0644 deploy/{cfg.slug}/{unidade} "
                                f"/etc/systemd/system/{unidade}")
            )
        elif instalada.read_text(encoding="utf-8") != texto_unit(cfg):
            achados.append(
                Achado("erro", f"unit {unidade} difere do host.toml; "
                               f"rode: homelabctl boot {cfg.slug} --write e reinstale")
            )
        else:
            achados.append(Achado("ok", f"unit {unidade} em sync"))

    return achados


def perfil_instalado(config_dir: Path) -> str:
    """Slug que o `/etc` deste host diz que ele e (vazio se nao houver env).

    O `check` roda no repo, que tem hosts de varias maquinas: comparar todos
    com o `/etc` de um host so daria aviso falso para os outros.
    """
    host_env = Path(config_dir) / "host.env"
    if not host_env.is_file():
        return ""
    return _pares(host_env.read_text(encoding="utf-8")).get("HOST_PROFILE", "")


def drift(cfg: HostConfig, *, config_dir: Path | None = None) -> list[Achado]:
    """So o que ja esta instalado e difere do TOML (ausente nao conta).

    Serve para o `check`: no CI e num host sem render nada aparece, e no host
    que ja tem `host.env` a divergencia vira aviso em vez de silencio.
    """
    config = Path(config_dir or cfg.valor("caminhos", "config"))
    achados: list[Achado] = []
    for rotulo, esperado in (
        ("host.env", texto_host_env(cfg)),
        ("sync.env", texto_sync_env(cfg)),
    ):
        if not (config / rotulo).is_file():
            continue
        achado = _compara(config / rotulo, esperado, rotulo, cfg.slug)
        if achado and achado[0].nivel == "erro":
            achados += achado
    return achados


def resumo(achados: list[Achado]) -> str:
    erros = sum(1 for a in achados if a.nivel == "erro")
    avisos = sum(1 for a in achados if a.nivel == "aviso")
    return f"erros: {erros}; avisos: {avisos}"

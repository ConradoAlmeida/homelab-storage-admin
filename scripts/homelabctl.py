#!/usr/bin/env python3
"""Configurador do homelab: TOML do host -> host.env/sync.env.

Roda com python3 puro (sem Django, sem uv):

    python3 scripts/homelabctl.py list
    python3 scripts/homelabctl.py check
    python3 scripts/homelabctl.py render pi            # imprime o host.env
    python3 scripts/homelabctl.py render pi --sync     # imprime o sync.env
    python3 scripts/homelabctl.py render pi --write    # grava em [caminhos] config
    python3 scripts/homelabctl.py requisitos pi        # binarios que o host precisa
    python3 scripts/homelabctl.py detect               # so le: propoe um TOML
    python3 scripts/homelabctl.py init                 # TUI (ou perguntas) para confirmar
    python3 scripts/homelabctl.py init --escrever      # grava hosts/<slug>/host.toml
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.homelab_detect import DetectError, detectar, propor, texto_toml  # noqa: E402
from core.homelab_wizard import (  # noqa: E402
    CAMPOS,
    aplicar,
    executar,
    salvar,
    validar,
)
from core.homelab_config import (  # noqa: E402
    ConfigError,
    HostConfig,
    carregar,
    requisitos,
    slugs,
    texto_host_env,
    texto_sync_env,
    texto_unit,
)


def cmd_list(_args) -> int:
    for slug in slugs():
        cfg = carregar(slug)
        print(f"{slug:12} {cfg.valor('host', 'descricao') or cfg.nome}")
    return 0


def cmd_check(_args) -> int:
    nomes = slugs()
    if not nomes:
        print("ERRO: nenhum hosts/<slug>/host.toml", file=sys.stderr)
        return 1
    erros = 0
    for slug in nomes:
        try:
            cfg = carregar(slug)
        except ConfigError as exc:
            erros += 1
            print(f"ERRO {slug}: {exc}", file=sys.stderr)
            continue
        recursos = ", ".join(cfg.features_ligadas) or "nenhuma"
        print(f"ok {slug:12} {len(cfg.features_ligadas)} features: {recursos}")
    return 1 if erros else 0


# Quantos backups por arquivo o render mantem. O `/etc` nao pode virar
# deposito de .bak a cada render (o moya ja tinha tres sem poda).
BACKUPS = 3


def _poda_backups(caminho: Path, manter: int = BACKUPS) -> None:
    antigos = sorted(caminho.parent.glob(caminho.name + ".bak-*"))
    for velho in antigos[:-manter]:
        try:
            velho.unlink()
        except OSError:
            pass


def _grava(caminho: Path, texto: str) -> None:
    if caminho.exists() and caminho.read_text(encoding="utf-8") == texto:
        print(f"sem mudanca: {caminho}")
        return
    if caminho.exists():
        backup = caminho.with_name(f"{caminho.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        backup.write_text(caminho.read_text(encoding="utf-8"), encoding="utf-8")
        _poda_backups(caminho)
        print(f"backup: {backup}")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(texto, encoding="utf-8")
    os.chmod(temporario, 0o644)
    temporario.replace(caminho)
    print(f"escrito: {caminho}")


def cmd_requisitos(args) -> int:
    """Lista `tipo|binario|pacotes` para o install-agent checar."""
    for tipo, nome, pacotes in requisitos(carregar(args.host)):
        print(f"{tipo}|{nome}|{pacotes}")
    return 0


def cmd_render(args) -> int:
    cfg = carregar(args.host)
    if args.sync:
        texto = texto_sync_env(cfg)
        nome = "sync.env"
    else:
        texto = texto_host_env(cfg)
        nome = "host.env"
    if not args.write:
        sys.stdout.write(texto)
        return 0
    destino = Path(args.destino or cfg.valor("caminhos", "config"))
    _grava(destino / nome, texto)
    if args.ambos:
        outro = "host.env" if nome == "sync.env" else "sync.env"
        outro_texto = texto_host_env(cfg) if outro == "host.env" else texto_sync_env(cfg)
        _grava(destino / outro, outro_texto)
    return 0


def cmd_boot(args) -> int:
    """Unit de boot do host (a do Pi inclui os stacks de terceiros)."""
    cfg = carregar(args.host)
    texto = texto_unit(cfg)
    if not args.write:
        sys.stdout.write(texto)
        return 0
    unidade = str(cfg.valor("boot", "unit"))
    destino = Path(args.destino or Path("deploy") / cfg.slug) / unidade
    _grava(destino, texto)
    return 0


def cmd_detect(args) -> int:
    """So le o host e imprime a proposta de hosts/<slug>/host.toml."""
    try:
        sistema = detectar()
    except DetectError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    proposta = propor(sistema)
    if args.json:
        dados = dict(proposta)
        dados["host"] = {**proposta["host"], "hostname": sistema.hostname}
        print(json.dumps(dados, indent=2, ensure_ascii=False))
        return 0
    sys.stdout.write(texto_toml(proposta))
    if not args.quieto:
        print(
            f"# arquivo sugerido: hosts/{proposta['host']['nome']}/host.toml",
            file=sys.stderr,
        )
    return 0


def cmd_init(args) -> int:
    """Wizard: detecta, confirma com o dono e (com --escrever) grava o TOML."""
    try:
        sistema = detectar()
    except DetectError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    proposta = propor(sistema)
    if args.host:
        proposta = aplicar(proposta, {"host.nome": args.host})
    if not args.sim:
        respostas = executar(proposta)
        if respostas is None:
            print("cancelado; nada foi escrito.", file=sys.stderr)
            return 1
        proposta = aplicar(proposta, respostas)
    erros = validar(proposta)
    if erros:
        for erro in erros:
            print(f"ERRO: {erro}", file=sys.stderr)
        return 2
    destino = Path("hosts") / proposta["host"]["nome"] / "host.toml"
    if not args.escrever:
        sys.stdout.write(texto_toml(proposta))
        print(
            f"# nada escrito. Para gravar: homelabctl init --escrever"
            f" (destino: {destino})",
            file=sys.stderr,
        )
        return 0
    try:
        caminho = salvar(proposta, sobrescrever=args.sobrescrever)
    except ConfigError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    print(f"escrito: {caminho}", file=sys.stderr)
    print(
        f"# agora: python3 scripts/homelabctl.py render {proposta['host']['nome']}"
        " --write --ambos",
        file=sys.stderr,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="homelabctl",
        description="Configuracao do host (hosts/<slug>/host.toml) e render do host.env.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("list", help="lista os hosts configurados").set_defaults(func=cmd_list)

    check = sub.add_parser("check", help="valida todos os hosts (sai 1 se algum falhar)")
    check.set_defaults(func=cmd_check)

    detect = sub.add_parser(
        "detect", help="so le: propoe um host.toml a partir do host atual"
    )
    detect.add_argument("--json", action="store_true", help="imprime a deteccao crua")
    detect.add_argument(
        "--quieto", action="store_true", help="nao imprime o nome do arquivo sugerido"
    )
    detect.set_defaults(func=cmd_detect)

    init = sub.add_parser(
        "init", help="wizard: detecta o host e propoe hosts/<slug>/host.toml"
    )
    init.add_argument("host", nargs="?", help="slug a usar no lugar do hostname")
    init.add_argument(
        "--escrever",
        action="store_true",
        help="grava o TOML (padrao: so mostra e nao escreve nada)",
    )
    init.add_argument(
        "--sobrescrever", action="store_true", help="com --escrever, troca um host existente"
    )
    init.add_argument(
        "--sim",
        action="store_true",
        help="nao pergunta: usa a deteccao como esta (para script)",
    )
    init.set_defaults(func=cmd_init)

    req = sub.add_parser(
        "requisitos", help="lista os binarios que o host precisa (para o install-agent)"
    )
    req.add_argument("host")
    req.set_defaults(func=cmd_requisitos)

    boot = sub.add_parser(
        "boot", help="gera a unit de boot do [boot] do host.toml"
    )
    boot.add_argument("host")
    boot.add_argument(
        "--write", action="store_true", help="grava em deploy/<slug>/<unit>"
    )
    boot.add_argument(
        "--destino", help="diretorio de saida (padrao: deploy/<slug>)"
    )
    boot.set_defaults(func=cmd_boot)

    render = sub.add_parser("render", help="gera o host.env (ou o sync.env com --sync)")
    render.add_argument("host")
    render.add_argument("--sync", action="store_true", help="gera o sync.env do apps-sync")
    render.add_argument(
        "--write",
        action="store_true",
        help="grava no diretorio de [caminhos] config (padrao: so imprime)",
    )
    render.add_argument(
        "--ambos", action="store_true", help="com --write, grava host.env e sync.env"
    )
    render.add_argument(
        "--destino", help="diretorio de saida (padrao: [caminhos] config do host)"
    )
    render.set_defaults(func=cmd_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

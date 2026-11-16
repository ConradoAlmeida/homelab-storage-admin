#!/usr/bin/env python3
"""Configurador do homelab: TOML do host -> host.env/sync.env.

Roda com python3 puro (sem Django, sem uv):

    python3 scripts/homelabctl.py list
    python3 scripts/homelabctl.py check
    python3 scripts/homelabctl.py render pi            # imprime o host.env
    python3 scripts/homelabctl.py render pi --sync     # imprime o sync.env
    python3 scripts/homelabctl.py render pi --write    # grava em [caminhos] config
    python3 scripts/homelabctl.py detect               # so le: propoe um TOML
    python3 scripts/homelabctl.py init novo-host       # TUI para confirmar
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.homelab_config import (  # noqa: E402
    ConfigError,
    HostConfig,
    carregar,
    slugs,
    texto_host_env,
    texto_sync_env,
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


def _grava(caminho: Path, texto: str) -> None:
    if caminho.exists() and caminho.read_text(encoding="utf-8") == texto:
        print(f"sem mudanca: {caminho}")
        return
    if caminho.exists():
        backup = caminho.with_name(f"{caminho.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        backup.write_text(caminho.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"backup: {backup}")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(texto, encoding="utf-8")
    os.chmod(temporario, 0o644)
    temporario.replace(caminho)
    print(f"escrito: {caminho}")


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="homelabctl",
        description="Configuracao do host (hosts/<slug>/host.toml) e render do host.env.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("list", help="lista os hosts configurados").set_defaults(func=cmd_list)

    check = sub.add_parser("check", help="valida todos os hosts (sai 1 se algum falhar)")
    check.set_defaults(func=cmd_check)

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

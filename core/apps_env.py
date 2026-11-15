"""Leitura do ``apps.env`` e do estado aplicado pelo apps-sync.

Somente leitura: esta tela mostra o que está declarado no env do checkout e o
que a última execução do ``scripts/stacks/apps-sync.sh --apply`` aplicou, para
que ninguém precise abrir o arquivo por SSH só para conferir.

Formato do env (uma app por linha)::

    key|fqdn|upstream|dir|flags

``flags`` é uma lista separada por vírgula: ``manual``, ``redir=...``,
``snippet=...``, ``atalho=painel|portal|painel+portal|nao``, ``nome=``,
``descricao=``, ``cor=#rrggbb``, ``icone=``, ``grupo=``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ATALHOS = ("painel", "portal")
GRUPOS = ("services", "infrastructure", "tools")
COR_PADRAO = "#38bdf8"
ICONE_PADRAO = "generic"

# Flags que valem como "caso especial" na coluna de rota.
EXTRAS = ("manual", "redir", "snippet")


@dataclass(frozen=True)
class App:
    key: str
    fqdn: str
    upstream: str
    dir: str
    url: str
    nome: str
    descricao: str
    cor: str
    icone: str
    grupo: str
    atalhos: tuple[str, ...]
    extras: tuple[str, ...]
    flags: str
    estado: str  # aplicado | pendente | fora do env

    @property
    def no_painel(self) -> bool:
        return "painel" in self.atalhos

    @property
    def no_portal(self) -> bool:
        return "portal" in self.atalhos

    @property
    def sem_atalho(self) -> bool:
        return not self.atalhos


@dataclass(frozen=True)
class Declarado:
    """Linha crua do env, antes de comparar com o estado."""

    key: str
    fqdn: str
    upstream: str
    dir: str
    flags: str
    linha: int
    erro: str = ""
    campos: dict[str, str] = field(default_factory=dict)


def _divide(valor: str) -> dict[str, str]:
    """``atalho=painel,nome=App`` -> ``{"atalho": "painel", "nome": "App"}``."""
    dados: dict[str, str] = {}
    for parte in valor.split(","):
        parte = parte.strip()
        if not parte:
            continue
        if "=" in parte:
            chave, _, conteudo = parte.partition("=")
        else:
            chave, conteudo = parte, ""
        dados.setdefault(chave.strip(), conteudo.strip())
    return dados


def nome_padrao(fqdn: str) -> str:
    """Mesmo default do ``apps-sync``: base do fqdn, sem hífen, inicial alta."""
    base = (fqdn or "").split(".")[0].replace("-", " ")
    return base[:1].upper() + base[1:]


def url_do_scheme(fqdn: str, scheme: str) -> str:
    return f"{scheme}://{fqdn}" if fqdn else ""


def le_declarado(caminho: Path | str, *, scheme: str) -> list[Declarado]:
    """Lê o env. Arquivo ausente devolve lista vazia (quem chama avisa)."""
    arquivo = Path(caminho)
    try:
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    linhas: list[Declarado] = []
    for numero, bruta in enumerate(texto.splitlines(), start=1):
        linha = bruta.rstrip("\r")
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        campos = linha.split("|")
        if len(campos) != 5:
            linhas.append(
                Declarado(
                    key=campos[0].strip(),
                    fqdn="",
                    upstream="",
                    dir="",
                    flags="",
                    linha=numero,
                    erro=f"esperava 5 campos, achei {len(campos)}",
                )
            )
            continue
        key, fqdn, upstream, dir_, flags = (campo.strip() for campo in campos)
        linhas.append(
            Declarado(
                key=key,
                fqdn=fqdn,
                upstream=upstream,
                dir=dir_,
                flags=flags,
                campos=_divide(flags),
                linha=numero,
            )
        )
    return linhas


def le_estado(caminho: Path | str) -> dict[str, str]:
    """``apps.aplicados`` -> ``{key: "fqdn|upstream|dir|flags"}``."""
    arquivo = Path(caminho)
    try:
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    estado: dict[str, str] = {}
    for linha in texto.splitlines():
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        campos = linha.split("|")
        if len(campos) < 5:
            continue
        estado[campos[0].strip()] = "|".join(campos[1:5]).strip()
    return estado


def _assina_estado(fqdn: str, upstream: str, dir_: str, flags: str) -> str:
    return f"{fqdn}|{upstream}|{dir_}|{flags}"


def _atalhos(flags: dict[str, str]) -> tuple[str, ...]:
    valor = flags.get("atalho", "")
    if valor in ("", "nao"):
        return ()
    escolhidos = [nome for nome in ATALHOS if nome in valor.split("+")]
    return tuple(escolhidos)


def _extras(flags: dict[str, str]) -> tuple[str, ...]:
    rotulos = []
    for nome in EXTRAS:
        if nome not in flags:
            continue
        if nome == "manual":
            rotulos.append("manual")
        else:
            rotulos.append(f"{nome}={flags[nome]}" if flags[nome] else nome)
    return tuple(rotulos)


def apps_do_env(
    *, env: Path | str, estado: Path | str, scheme: str
) -> tuple[list[App], list[App], list[Declarado]]:
    """Devolve ``(apps, fora do env, linhas invalidas)``."""
    declaradas = le_declarado(env, scheme=scheme)
    aplicado = le_estado(estado)

    apps: list[App] = []
    invalidas: list[Declarado] = []
    for item in declaradas:
        if item.erro:
            invalidas.append(item)
            continue
        flags = item.campos
        assinatura = _assina_estado(item.fqdn, item.upstream, item.dir, item.flags)
        if item.key not in aplicado:
            situacao = "novo"
        elif aplicado[item.key] == assinatura:
            situacao = "aplicado"
        else:
            situacao = "pendente"
        apps.append(
            App(
                key=item.key,
                fqdn=item.fqdn,
                upstream=item.upstream,
                dir=item.dir,
                url=url_do_scheme(item.fqdn, scheme),
                nome=flags.get("nome") or nome_padrao(item.fqdn),
                descricao=flags.get("descricao", ""),
                cor=flags.get("cor") or COR_PADRAO,
                icone=flags.get("icone") or ICONE_PADRAO,
                grupo=flags.get("grupo") or "services",
                atalhos=_atalhos(flags),
                extras=_extras(flags),
                flags=item.flags,
                estado=situacao,
            )
        )

    no_env = {item.key for item in apps}
    fora: list[App] = []
    for key, valor in aplicado.items():
        if key in no_env:
            continue
        fqdn, upstream, dir_, flags = (valor.split("|") + ["", "", "", ""])[:4]
        campos = _divide(flags)
        fora.append(
            App(
                key=key,
                fqdn=fqdn,
                upstream=upstream,
                dir=dir_,
                url=url_do_scheme(fqdn, scheme),
                nome=campos.get("nome") or nome_padrao(fqdn),
                descricao=campos.get("descricao", ""),
                cor=campos.get("cor") or COR_PADRAO,
                icone=campos.get("icone") or ICONE_PADRAO,
                grupo=campos.get("grupo") or "services",
                atalhos=_atalhos(campos),
                extras=_extras(campos),
                flags=flags,
                estado="fora do env",
            )
        )
    fora.sort(key=lambda app: app.key)
    return apps, fora, invalidas


def resumo(apps: list[App]) -> dict[str, int]:
    return {
        "total": len(apps),
        "painel": sum(1 for app in apps if app.no_painel),
        "portal": sum(1 for app in apps if app.no_portal),
        "sem_atalho": sum(1 for app in apps if app.sem_atalho),
        "pendentes": sum(1 for app in apps if app.estado != "aplicado"),
    }

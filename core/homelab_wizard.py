"""Wizard `homelabctl init`: detector -> confirmacao -> hosts/<slug>/host.toml.

A logica (editar, validar, salvar) e pura e testavel; a TUI (textual) so
apresenta. Sem textual instalado -- host recem-instalado, SSH sem `uv sync` --
cai num questionario no terminal com as mesmas perguntas.

O wizard nunca formata, monta ou apaga disco: os papeis so decidem o que a UI
mostra depois (regra 5).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .homelab_config import DIR_HOSTS, ConfigError, carregar_arquivo
from .homelab_detect import Sistema, propor, texto_toml

# Campos que o wizard pergunta, na ordem. (secao, chave, rotulo, dica)
CAMPOS = (
    ("host", "nome", "Slug do host", "a-z, 0-9 e -; vira o nome de hosts/<slug>"),
    ("host", "descricao", "Descrição", "texto curto para o `homelabctl list`"),
    ("host", "ssh", "SSH", "usuario@host, como aparece na tela de Configuração"),
    ("host", "lan_ip", "IP da LAN", "IP fixo; é ele que o DNS e o painel anunciam"),
    ("host", "repo", "Checkout no host", "onde o deploy.sh roda"),
    ("app", "site_name", "Nome do site", "título do painel"),
    ("app", "bind_addr", "Endereço do painel", "IP da LAN ou 127.0.0.1"),
    ("caminhos", "dados", "Raiz dos dados", "onde ficam os shares"),
    ("caminhos", "backup", "Raiz do backup", "nunca no mesmo disco dos dados"),
    ("rotas", "dominio", "Domínio das rotas", ".local, domínio próprio ou vazio"),
    ("rotas", "dns_modo", "Modo do DNS", "wildcard, nome ou nenhum"),
    ("rotas", "upstream", "Upstream do proxy", "lan, localhost ou nenhum"),
)


def _no(dados: dict, secao: str, chave: str, padrao=""):
    return (dados.get(secao) or {}).get(chave, padrao)


def aplicar(proposta: dict, respostas: dict[str, str]) -> dict:
    """Aplica `secao.chave -> valor` e acerta os caminhos derivados dos dados."""
    nova = {
        **{k: (dict(v) if isinstance(v, dict) else v) for k, v in proposta.items()}
    }
    dados_antigo = str(_no(proposta, "caminhos", "dados"))
    for chave, valor in respostas.items():
        if chave.startswith("feature."):
            nome = chave.split(".", 1)[1]
            nova.setdefault("features", {})[nome] = bool(valor)
            continue
        if "." not in chave:
            continue
        secao, campo = chave.split(".", 1)
        nova.setdefault(secao, {})[campo] = valor

    novo_dados = str(_no(nova, "caminhos", "dados")).rstrip("/") or dados_antigo
    if novo_dados != dados_antigo:
        nova["caminhos"]["snapshots"] = novo_dados + "/.snapshots"
        nova["caminhos"]["dados_app"] = novo_dados + "/apps/homelab-storage-admin/data"
        prefixos = list(_no(nova, "armazenamento", "prefixos_permitidos") or [])
        nova["armazenamento"]["prefixos_permitidos"] = [
            novo_dados if p == dados_antigo else p for p in prefixos
        ] or [novo_dados]

    slug = str(_no(nova, "host", "nome"))
    nova["rotas"]["apps"] = f"deploy/{slug}/apps.env"
    porta = _no(nova, "app", "bind_port", 8060)
    try:
        nova["app"]["bind_port"] = int(porta)
    except (TypeError, ValueError):
        nova["app"]["bind_port"] = 8060
    return nova


def validar(proposta: dict) -> list[str]:
    """Roda o mesmo `validar` do loader e devolve as mensagens (vazio = ok)."""
    texto = texto_toml(proposta)
    with tempfile.TemporaryDirectory() as diretorio:
        arquivo = Path(diretorio) / "host.toml"
        arquivo.write_text(texto, encoding="utf-8")
        try:
            carregar_arquivo(arquivo)
        except ConfigError as exc:
            return [str(exc).replace(str(arquivo), "host.toml")]
    return []


def caminho_do_host(slug: str, raiz: Path | None = None) -> Path:
    return (raiz or DIR_HOSTS) / slug / "host.toml"


def salvar(proposta: dict, raiz: Path | None = None, sobrescrever: bool = False) -> Path:
    """Grava o TOML. Recusa sobrescrever um host existente sem `sobrescrever`."""
    erros = validar(proposta)
    if erros:
        raise ConfigError("; ".join(erros))
    destino = caminho_do_host(str(_no(proposta, "host", "nome")), raiz)
    if destino.exists() and not sobrescrever:
        raise ConfigError(f"{destino} ja existe (use --sobrescrever para trocar)")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto_toml(proposta), encoding="utf-8")
    return destino


# --- fluxo interativo -----------------------------------------------------

def perguntas(proposta: dict) -> dict[str, str]:
    """`secao.chave -> valor atual`, que e o que a TUI e o prompt mostram."""
    return {
        f"{secao}.{chave}": str(_no(proposta, secao, chave, ""))
        for secao, chave, _rotulo, _dica in CAMPOS
    }


def sequencial(proposta: dict, perguntar=input) -> dict:
    """Fallback sem textual: uma pergunta por campo, Enter mantem o valor."""
    respostas: dict[str, str] = {}
    for secao, chave, rotulo, dica in CAMPOS:
        atual = str(_no(proposta, secao, chave, ""))
        resposta = perguntar(f"{rotulo} [{atual}] ({dica}): ").strip()
        if resposta:
            respostas[f"{secao}.{chave}"] = resposta
    resposta = perguntar("Manter as features detectadas? [S/n]: ").strip().lower()
    if resposta in ("n", "nao", "não"):
        for nome in list(proposta.get("features") or {}):
            respostas[f"feature.{nome}"] = "0"
    return respostas


def criar_app(proposta: dict):
    """Monta o App do textual (separado para o teste rodar headless)."""
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, Vertical
    from textual.widgets import (
        Button,
        Checkbox,
        Footer,
        Header,
        Input,
        Label,
        Static,
        TabbedContent,
        TabPane,
        TextArea,
    )

    class Wizard(App):
        CSS = """
        #form { padding: 1 2; }
        .campo { margin-bottom: 1; }
        #revisao { height: 1fr; }
        #erros { color: red; padding: 0 2; }
        """

        def __init__(self) -> None:
            super().__init__()
            self.resultado: dict | None = None
            self.base = proposta

        def compose(self) -> ComposeResult:
            yield Header()
            with TabbedContent():
                for secao, titulo in (
                    ("host", "Host"),
                    ("app", "Painel"),
                    ("caminhos", "Caminhos"),
                    ("rotas", "Rotas"),
                ):
                    with TabPane(titulo, id=f"aba-{secao}"):
                        with Vertical(id=f"form-{secao}"):
                            for s, chave, rotulo, dica in CAMPOS:
                                if s != secao:
                                    continue
                                yield Label(f"{rotulo}  [{dica}]", classes="campo")
                                yield Input(
                                    value=str(_no(self.base, s, chave, "")),
                                    id=f"campo-{s}-{chave}",
                                )
                with TabPane("Features", id="aba-features"):
                    with Vertical(id="form-features"):
                        yield Label("Recursos deste host")
                        for nome, ligado in (self.base.get("features") or {}).items():
                            yield Checkbox(nome, value=bool(ligado), id=f"feature-{nome}")
                with TabPane("Revisão", id="aba-revisao"):
                    yield TextArea("", read_only=True, id="revisao")
            yield Static("", id="erros")
            with Horizontal(id="botoes"):
                yield Button("Revisar", id="revisar")
                yield Button("Gravar", id="gravar", variant="primary")
                yield Button("Cancelar", id="cancelar")
            yield Footer()

        def _respostas(self) -> dict:
            respostas: dict = {}
            for campo in self.query(Input):
                secao, chave = campo.id.removeprefix("campo-").split("-", 1)
                respostas[f"{secao}.{chave}"] = campo.value.strip()
            for caixa in self.query(Checkbox):
                nome = caixa.id.removeprefix("feature-")
                respostas[f"feature.{nome}"] = caixa.value
            return respostas

        def _proposta(self) -> dict:
            return aplicar(self.base, self._respostas())

        def _revisar(self) -> None:
            nova = self._proposta()
            erros = validar(nova)
            self.query_one("#erros", Static).update("\n".join(erros))
            self.query_one("#revisao", TextArea).text = texto_toml(nova)

        def on_button_pressed(self, evento: Button.Pressed) -> None:
            if evento.button.id == "cancelar":
                self.resultado = None
                self.exit()
            elif evento.button.id == "revisar":
                self._revisar()
            elif evento.button.id == "gravar":
                if validar(self._proposta()):
                    self._revisar()
                    return
                self.resultado = self._respostas()
                self.exit()

    return Wizard()


def executar_tui(proposta: dict) -> dict | None:
    """Abre a TUI; devolve as respostas do usuario ou None se cancelar."""
    app = criar_app(proposta)
    app.run()
    return app.resultado


def executar(proposta: dict, tui=None, perguntar=input) -> dict | None:
    """TUI se der; senao o questionario. `tui` injetavel nos testes.

    Devolve as respostas de edicao (prontas para `aplicar`) ou None se o
    usuario cancelar.
    """
    if tui is not None:
        return tui(proposta)
    try:
        import textual  # noqa: F401
    except ImportError:
        return sequencial(proposta, perguntar=perguntar)
    return executar_tui(proposta)


def proposta_do_sistema(sistema: Sistema) -> dict:
    return propor(sistema)

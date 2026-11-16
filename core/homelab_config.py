"""Configuracao do host em TOML: ``hosts/<slug>/host.toml``.

O TOML e a fonte da verdade do que muda entre hosts. O deploy, o compose, o
agente e o ``apps-sync.sh`` continuam lendo ``host.env``, mas ele passa a ser
**gerado** daqui (``homelabctl render``), com o mesmo nome de chave de sempre.

Sem importar Django: o configurador roda num host que so tem python3.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_HOSTS = RAIZ / "hosts"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Nome -> descricao. O wizard usa a descricao; `validar` recusa nome fora daqui.
FEATURES = {
    "samba": "Shares Samba e usuários/grupos do host",
    "snapshots": "Snapshots de share e navegador de versões",
    "restic": "Jobs de backup restic e cópia fria",
    "copia_fria": "Cópia para disco USB com ejeção no fim",
    "ufw": "Firewall UFW pela UI",
    "terminal": "Terminal no navegador",
    "apt": "Atualizações apt e units systemd",
    "qbittorrent": "Torrents (qBittorrent)",
    "jellyfin": "Mídia do Jellyfin e downloads",
    "pihole": "Pi-hole: arquivo de DNS das rotas",
    "gitea": "Backup do Gitea",
    "portal": "Lista de atalhos do portal interno",
    "credenciais": "Login pelo Credenciais e backup local dele",
    "django_admins": "Superuser/password dos apps Django pelo agente",
}

# Defaults que o agente e o compose aplicam quando a chave nao existe. O
# render so precisa emitir o que difere, mas emitir explicito e mais legivel.
PADROES = {
    "FIREWALL_SAFE_PORTS": (
        "22/tcp,53/tcp,53/udp,80/tcp,443/tcp,8060/tcp,"
        "137/udp,138/udp,139/tcp,445/tcp"
    ),
    "SNAPSHOT_BACKEND": "auto",
}

SECOES = ("host", "app", "caminhos", "armazenamento", "rotas", "features")


class ConfigError(ValueError):
    """Configuracao invalida; a mensagem diz o campo e o que se esperava."""


@dataclass(frozen=True)
class HostConfig:
    slug: str
    origem: Path
    dados: dict

    def secao(self, nome: str) -> dict:
        return self.dados.get(nome) or {}

    def valor(self, secao: str, chave: str, padrao=None):
        return self.secao(secao).get(chave, padrao)

    @property
    def nome(self) -> str:
        return self.valor("host", "nome", self.slug)

    @property
    def features_ligadas(self) -> tuple[str, ...]:
        flags = self.secao("features")
        return tuple(nome for nome, ligado in flags.items() if ligado)

    def ligado(self, feature: str) -> bool:
        return bool(self.secao("features").get(feature))


def slugs() -> list[str]:
    if not DIR_HOSTS.is_dir():
        return []
    return sorted(
        p.parent.name
        for p in DIR_HOSTS.glob("*/host.toml")
        if SLUG_RE.match(p.parent.name)
    )


def caminho_do_host(slug: str) -> Path:
    return DIR_HOSTS / slug / "host.toml"


def carregar(slug: str) -> HostConfig:
    arquivo = caminho_do_host(slug)
    if not arquivo.is_file():
        disponiveis = ", ".join(slugs()) or "nenhum"
        raise ConfigError(
            f"host '{slug}' nao encontrado em {DIR_HOSTS} (disponiveis: {disponiveis})"
        )
    return carregar_arquivo(arquivo)


def carregar_arquivo(arquivo: Path) -> HostConfig:
    arquivo = Path(arquivo)
    try:
        dados = tomllib.loads(arquivo.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"arquivo ausente: {arquivo}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{arquivo}: TOML invalido: {exc}") from exc
    slug = dados.get("host", {}).get("nome") or arquivo.parent.name
    cfg = HostConfig(slug=slug, origem=arquivo, dados=dados)
    validar(cfg)
    return cfg


def _absoluto(cfg: HostConfig, secao: str, chave: str, permitir_vazio=False) -> None:
    valor = cfg.valor(secao, chave)
    if valor in (None, ""):
        if permitir_vazio:
            return
        raise ConfigError(f"{cfg.origem}: falta [{secao}] {chave}")
    if not str(valor).startswith("/"):
        raise ConfigError(
            f"{cfg.origem}: [{secao}] {chave} deve ser caminho absoluto: {valor!r}"
        )


def validar(cfg: HostConfig) -> None:
    dados = cfg.dados
    faltando = [s for s in SECOES if s not in dados]
    if faltando:
        raise ConfigError(
            f"{cfg.origem}: secoes obrigatorias ausentes: {', '.join(faltando)}"
        )
    if not SLUG_RE.match(cfg.slug):
        raise ConfigError(
            f"{cfg.origem}: nome do host deve ser slug (a-z, 0-9, -): {cfg.slug!r}"
        )
    for secao, chaves in (
        ("host", ("ssh", "lan_ip", "repo")),
        ("app", ("site_name", "bind_addr", "compose_overlay")),
        ("caminhos", ("dados", "snapshots", "backup", "dados_app", "stacks",
                      "quarentena", "estado", "sockets", "config")),
        ("armazenamento", ("proprietario", "snapshot_backend")),
        ("rotas", ("esquema", "apps", "dns_ip", "dns_modo", "dominio",
                   "dns_conf", "pihole_dir", "caddy", "upstream")),
    ):
        ausentes = [c for c in chaves if dados.get(secao, {}).get(c) in (None, "")]
        if ausentes:
            raise ConfigError(
                f"{cfg.origem}: falta em [{secao}]: {', '.join(ausentes)}"
            )

    for secao, chaves in (
        ("host", ("repo",)),
        ("caminhos", ("dados", "snapshots", "backup", "dados_app", "stacks",
                      "quarentena", "estado", "sockets", "config")),
    ):
        for chave in chaves:
            _absoluto(cfg, secao, chave)
    _absoluto(cfg, "rotas", "dns_conf")
    _absoluto(cfg, "rotas", "pihole_dir")

    port = cfg.valor("app", "bind_port")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ConfigError(f"{cfg.origem}: [app] bind_port invalido: {port!r}")
    if cfg.valor("rotas", "esquema") not in ("http", "https"):
        raise ConfigError(
            f"{cfg.origem}: [rotas] esquema deve ser http ou https: "
            f"{cfg.valor('rotas', 'esquema')!r}"
        )
    if cfg.valor("rotas", "dns_modo") not in ("wildcard", "nome", "nenhum"):
        raise ConfigError(
            f"{cfg.origem}: [rotas] dns_modo deve ser wildcard, nome ou nenhum"
        )
    apps = str(cfg.valor("rotas", "apps"))
    if not apps.endswith("apps.env") or apps.startswith("/"):
        raise ConfigError(
            f"{cfg.origem}: [rotas] apps deve ser relativo ao repo e terminar em "
            f"apps.env: {apps!r}"
        )
    caddy = cfg.valor("rotas", "caddy") or {}
    if not isinstance(caddy, dict) or not caddy.get("dir") or not caddy.get("container"):
        raise ConfigError(
            f"{cfg.origem}: [rotas] caddy precisa de dir e container (ou "
            "upstream sem proxy)"
        )

    flags = cfg.secao("features")
    desconhecidas = sorted(set(flags) - set(FEATURES))
    if desconhecidas:
        raise ConfigError(
            f"{cfg.origem}: features desconhecidas: {', '.join(desconhecidas)}"
        )
    nao_booleanas = [nome for nome, valor in flags.items() if not isinstance(valor, bool)]
    if nao_booleanas:
        raise ConfigError(
            f"{cfg.origem}: features devem ser true/false: {', '.join(nao_booleanas)}"
        )
    if cfg.ligado("jellyfin"):
        _absoluto(cfg, "caminhos", "jellyfin")
    if cfg.ligado("credenciais"):
        for chave in ("db", "env", "backup_dir", "container"):
            if not cfg.valor("credenciais", chave):
                raise ConfigError(
                    f"{cfg.origem}: feature credenciais exige [credenciais] {chave}"
                )

    discos = dados.get("discos") or []
    papeis = {"dados", "snapshot", "backup", "jellyfin"}
    for i, disco in enumerate(discos, 1):
        if not str(disco.get("device", "")).startswith("/dev/"):
            raise ConfigError(f"{cfg.origem}: disco {i} sem device /dev/...")
        invalidos = set(disco.get("papel") or ()) - papeis
        if invalidos:
            raise ConfigError(
                f"{cfg.origem}: disco {i} com papel invalido: {', '.join(sorted(invalidos))}"
            )


# --- render ---------------------------------------------------------------

def _lista(valor) -> str:
    if isinstance(valor, (list, tuple)):
        return ",".join(str(v) for v in valor)
    return str(valor or "")


def _shell(valor) -> str:
    """Valor seguro para `source` no bash (usado só no sync.env)."""
    texto = str(valor)
    if not texto:
        return "''"
    if re.fullmatch(r"[A-Za-z0-9_./:@,+-]+", texto):
        return texto
    return "'" + texto.replace("'", "'\\''") + "'"


def render_host_env(cfg: HostConfig) -> list[tuple[str, str]]:
    """Pares chave/valor do ``host.env``, na ordem em que saem no arquivo."""
    c, a, r = cfg.secao("caminhos"), cfg.secao("app"), cfg.secao("rotas")
    arm, cr = cfg.secao("armazenamento"), cfg.secao("credenciais")
    dados_app = str(c["dados_app"])
    pares: list[tuple[str, str]] = [
        ("SITE_NAME", cfg.valor("app", "site_name")),
        ("STORAGE_ROOT", c["dados"]),
        ("SNAPSHOT_ROOT", c["snapshots"]),
        ("ALLOWED_PATH_PREFIXES", _lista(arm.get("prefixos_permitidos"))),
        ("DF_MOUNTS", _lista(arm.get("mounts"))),
        ("SHARE_OWNER", arm.get("proprietario")),
        ("SNAPSHOT_DENYLIST", _lista(arm.get("snapshot_denylist"))),
        ("SNAPSHOT_BACKEND", arm.get("snapshot_backend", PADROES["SNAPSHOT_BACKEND"])),
        ("BACKUP_ROOT", c["backup"]),
        ("AGENT_SOCKET", str(c["sockets"]).rstrip("/") + "/agent.sock"),
        ("AGENT_SOCKET_DIR", c["sockets"]),
        ("BIND_ADDR", a["bind_addr"]),
        ("BIND_PORT", str(a["bind_port"])),
        ("COMPOSE_OVERLAY", a["compose_overlay"]),
        ("DATA_DIR", dados_app),
    ]
    if cfg.ligado("jellyfin"):
        pares.append(("JELLYFIN_ROOT", c["jellyfin"]))
    pares.append(("DOWNLOAD_DIR", dados_app.rstrip("/") + "/downloads"))
    if cfg.ligado("credenciais"):
        pares += [
            ("CREDENCIAIS_DB", cr["db"]),
            ("CREDENCIAIS_ENV", cr["env"]),
            ("CREDENCIAIS_BACKUP_DIR", cr["backup_dir"]),
            ("CREDENCIAIS_CONTAINER", cr["container"]),
            ("CREDENCIAIS_TIME", cr.get("time", "03:30")),
            ("CREDENCIAIS_RETENTION_DAYS", str(cr.get("retention_days", 30))),
        ]
    pares.append(("CREDENTIALS_MANAGE_USERS", "1" if cfg.ligado("credenciais") else "0"))
    if cfg.ligado("ufw"):
        pares.append(("FIREWALL_MANAGE", "1"))
        pares.append(
            ("FIREWALL_SAFE_PORTS", _lista(arm.get("firewall_safe_ports")
                                           or PADROES["FIREWALL_SAFE_PORTS"]))
        )
    if cfg.ligado("terminal"):
        pares.append(("TERMINAL_ENABLE", "1"))
    if cfg.ligado("django_admins"):
        pares.append(("DJANGO_ADMIN_MANAGE", "1"))
    pares.append(("HOST_PROFILE", cfg.slug))
    repo = str(cfg.valor("host", "repo")).rstrip("/")
    pares.append(("APPS_ENV_PATH", f"{repo}/{r['apps']}"))
    return pares


def render_sync_env(cfg: HostConfig) -> list[tuple[str, str]]:
    """Pares do ``sync.env``: o que o ``apps-sync.sh`` lia do `case $PERFIL`."""
    c, r = cfg.secao("caminhos"), cfg.secao("rotas")
    caddy = r["caddy"]
    caddy_dir = str(caddy["dir"]).rstrip("/")
    pihole_dir = str(r["pihole_dir"]).rstrip("/")
    upstream = r["upstream"]
    host_upstream = r["dns_ip"] if upstream == "lan" else "localhost"
    return [
        ("SCHEME", r["esquema"]),
        ("DATA_DIR", c["dados_app"]),
        ("STACKS_ROOT", c["stacks"]),
        ("CADDY_DIR", caddy_dir),
        ("CADDY_CONTAINER", caddy["container"]),
        ("CADDYFILE", caddy_dir + "/Caddyfile"),
        ("CADDY_APPS", caddy_dir + "/apps.caddy"),
        ("CADDY_TOKEN_FILE", caddy_dir + "/cloudflare.token"),
        ("CADDY_PORTA", caddy.get("porta", "")),
        ("CADDY_TLS", caddy.get("tls", "")),
        ("CADDY_PROXY", caddy.get("proxy", "")),
        ("PIHOLE_CONTAINER", r.get("pihole_container", "pihole")),
        ("PIHOLE_DIR", pihole_dir),
        ("DNS_CONF", r["dns_conf"]),
        ("DNS_IP", r["dns_ip"]),
        ("DNS_MODE", r["dns_modo"]),
        ("DOMAIN", r["dominio"]),
        ("UPSTREAM_HOST", host_upstream),
        ("QUARANTINE", c["quarentena"]),
        ("SCAN_ROOTS", " ".join(r.get("scan_roots") or [])),
        ("DIRS_PERMITIDOS", " ".join(r.get("dirs_permitidos") or [])),
        ("PORTAL_INI", r.get("portal_ini", "")),
        ("APPS_STATE", str(c["estado"]).rstrip("/") + "/apps.aplicados"),
        ("SERVICES_INI", str(c["dados_app"]).rstrip("/") + "/services.ini"),
    ]


def texto_env(pares, titulo: str) -> str:
    linhas = [
        f"# {titulo}",
        "# Gerado por homelabctl render a partir de hosts/<slug>/host.toml.",
        "# Editar aqui a mao se perde na proxima renderizacao.",
    ]
    linhas += [f"{chave}={valor}" for chave, valor in pares]
    return "\n".join(linhas) + "\n"


def texto_sync_env(cfg: HostConfig) -> str:
    pares = [(chave, _shell(valor)) for chave, valor in render_sync_env(cfg)]
    return texto_env(pares, f"Rotas do host {cfg.slug} (apps-sync.sh)")


def _host(valor) -> str:
    """Aspas so quando o valor tem espaco (systemd aceita, docker compose le)."""
    texto = str(valor)
    if re.fullmatch(r"[A-Za-z0-9_./:@,+-]*", texto):
        return texto
    return '"' + texto.replace('"', '\\"') + '"'


def texto_host_env(cfg: HostConfig) -> str:
    pares = [(chave, _host(valor)) for chave, valor in render_host_env(cfg)]
    return texto_env(pares, f"Perfil do host {cfg.slug}")

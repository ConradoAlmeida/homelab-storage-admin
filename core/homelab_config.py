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
    "discos": "Discos: montar, formatar, SMART e RAID",
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

BOOT_CHAVES = ("unit", "descricao")

# Versao do schema. Chave nova com default em `_padroes` nao quebra TOML
# antigo; subir a versao e so para mudanca que exige revisao do arquivo.
SCHEMA_ATUAL = 1

# Binarios que cada feature usa no host. O install-agent.sh checa os
# `obrigatorios` e so avisa sobre os `opcionais` (o app esconde a acao).
# `pacotes` e a dica de apt quando falta.
REQUISITOS = {
    "samba": {
        "obrigatorios": ("pdbedit", "smbpasswd", "smbcontrol", "testparm"),
        "pacotes": "samba samba-common-bin",
    },
    "discos": {
        "obrigatorios": ("parted", "mkfs.ext4", "lsblk", "blkid"),
        "opcionais": ("smartctl", "hdparm", "mdadm"),
        "pacotes": "parted e2fsprogs util-linux",
        "pacotes_opcionais": "smartmontools hdparm mdadm",
    },
    "snapshots": {
        "obrigatorios": ("rsync",),
        "opcionais": ("btrfs",),
        "pacotes": "rsync",
        "pacotes_opcionais": "btrfs-progs",
    },
    "restic": {"obrigatorios": ("restic",), "pacotes": "restic"},
    "ufw": {"obrigatorios": ("ufw",), "pacotes": "ufw"},
}


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


def _padroes(dados: dict) -> None:
    """Preenche o que tem valor obvio; o resto continua obrigatorio.

    Existe para o TOML crescer sem quebrar hosts existentes: chave nova entra
    aqui com o valor que o host ja teria, e o `homelabctl check` continua
    verde. Caminho que depende de decisao (``backup``, ``proprietario``,
    ``dns_conf`` com DNS ativo) fica de fora de proposito.
    """
    host = dados.setdefault("host", {})
    app = dados.setdefault("app", {})
    cam = dados.setdefault("caminhos", {})
    arm = dados.setdefault("armazenamento", {})
    rotas = dados.setdefault("rotas", {})

    app.setdefault("bind_port", 8060)
    app.setdefault("compose_overlay", "")
    arm.setdefault("snapshot_backend", PADROES["SNAPSHOT_BACKEND"])
    arm.setdefault("snapshot_denylist", "")
    arm.setdefault("mounts", ["/"])
    rotas.setdefault("esquema", "http")
    rotas.setdefault("dominio", "local")
    rotas.setdefault("dns_modo", "nenhum")
    rotas.setdefault("upstream", "nenhum")
    if not rotas.get("dns_ip"):
        rotas["dns_ip"] = host.get("lan_ip", "")

    cam.setdefault("stacks", "/opt")
    cam.setdefault("config", "/etc/homelab-storage-admin")
    cam.setdefault("estado", "/var/lib/homelab-storage-admin")
    cam.setdefault("sockets", "/run/homelab-storage-admin")
    dados_ = str(cam.get("dados") or "").rstrip("/")
    if dados_:
        cam.setdefault("snapshots", dados_ + "/.snapshots")
        cam.setdefault("dados_app", dados_ + "/apps/homelab-storage-admin/data")
        if not arm.get("prefixos_permitidos"):
            arm["prefixos_permitidos"] = [dados_]
    if not cam.get("quarentena"):
        cam["quarentena"] = str(cam["stacks"]).rstrip("/") + "/stacks/_removidos"
    if not rotas.get("pihole_dir"):
        rotas["pihole_dir"] = str(cam["stacks"]).rstrip("/") + "/stacks/pihole"


def carregar_arquivo(arquivo: Path) -> HostConfig:
    arquivo = Path(arquivo)
    try:
        dados = tomllib.loads(arquivo.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"arquivo ausente: {arquivo}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{arquivo}: TOML invalido: {exc}") from exc
    _padroes(dados)
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
    schema = dados.get("host", {}).get("schema", 1)
    if not isinstance(schema, int) or schema < 1:
        raise ConfigError(f"{cfg.origem}: [host] schema invalido: {schema!r}")
    if schema > SCHEMA_ATUAL:
        raise ConfigError(
            f"{cfg.origem}: schema {schema} e mais novo que este homelabctl "
            f"({SCHEMA_ATUAL}); atualize o repo antes de usar o host"
        )
    obrigatorias = [
        ("host", ("ssh", "lan_ip", "repo")),
        ("app", ("site_name", "bind_addr")),
        ("caminhos", ("dados", "backup")),
        ("armazenamento", ("proprietario",)),
        ("rotas", ("apps",)),
    ]
    if cfg.valor("rotas", "dns_modo") != "nenhum":
        obrigatorias.append(("rotas", ("dns_conf",)))
    for secao, chaves in obrigatorias:
        ausentes = [c for c in chaves if dados.get(secao, {}).get(c) in (None, "")]
        if ausentes:
            raise ConfigError(
                f"{cfg.origem}: falta em [{secao}]: {', '.join(ausentes)}"
            )

    for chave in ("dados", "snapshots", "backup", "dados_app", "stacks",
                  "quarentena", "estado", "sockets", "config"):
        _absoluto(cfg, "caminhos", chave)
    _absoluto(cfg, "host", "repo")
    if cfg.valor("rotas", "dns_modo") != "nenhum":
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
    upstream = cfg.valor("rotas", "upstream")
    if upstream not in ("lan", "localhost", "nenhum"):
        raise ConfigError(
            f"{cfg.origem}: [rotas] upstream deve ser lan, localhost ou nenhum"
        )
    caddy = cfg.valor("rotas", "caddy") or {}
    if upstream == "nenhum" and not caddy:
        pass  # host sem proxy reverso: as rotas ficam so no papel
    elif not isinstance(caddy, dict) or not caddy.get("dir") or not caddy.get("container"):
        raise ConfigError(
            f"{cfg.origem}: [rotas] caddy precisa de dir e container (ou "
            'upstream = "nenhum")'
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

    boot = dados.get("boot") or {}
    if boot:
        faltam = [c for c in BOOT_CHAVES if not boot.get(c)]
        if faltam:
            raise ConfigError(
                f"{cfg.origem}: falta em [boot]: {', '.join(faltam)}"
            )
        if not str(boot["unit"]).endswith(".service"):
            raise ConfigError(
                f"{cfg.origem}: [boot] unit deve terminar em .service: "
                f"{boot['unit']!r}"
            )
        for chave in ("esperar_mounts", "antes", "depois"):
            for caminho in boot.get(chave) or ():
                if not str(caminho).startswith("/"):
                    raise ConfigError(
                        f"{cfg.origem}: [boot] {chave} deve ser caminho absoluto: "
                        f"{caminho!r}"
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


# --- requisitos -----------------------------------------------------------

def requisitos(cfg: HostConfig) -> list[tuple[str, str, str]]:
    """``(tipo, binario, pacotes)`` das features ligadas, sem repetir binario.

    ``tipo`` e ``obrig`` (falta derruba a instalacao) ou ``opc`` (so aviso).
    """
    vistos: dict[str, tuple[str, str, str]] = {}
    for feature in cfg.features_ligadas:
        regra = REQUISITOS.get(feature)
        if not regra:
            continue
        for nome in regra.get("obrigatorios", ()):
            vistos.setdefault(nome, ("obrig", nome, regra.get("pacotes", "")))
        for nome in regra.get("opcionais", ()):
            vistos.setdefault(nome, ("opc", nome, regra.get("pacotes_opcionais", "")))
    return list(vistos.values())


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
        ("COMPOSE_OVERLAY", a.get("compose_overlay", "")),
        ("DATA_DIR", dados_app),
    ]
    if cfg.ligado("jellyfin"):
        pares.append(("JELLYFIN_ROOT", c["jellyfin"]))
    pares.append(("DOWNLOAD_DIR", dados_app.rstrip("/") + "/downloads"))
    # Default do deploy e 0: so o host com a feature precisa da chave.
    if cfg.ligado("qbittorrent"):
        pares.append(("QBITTORRENT_ENABLE", "1"))
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
    # Sempre explicito: o default do settings e 1, entao host que nao tem a
    # feature precisa dizer 0 em vez de herdar o comportamento do Pi.
    pares.append(("FIREWALL_MANAGE", "1" if cfg.ligado("ufw") else "0"))
    if cfg.ligado("ufw"):
        pares.append(
            ("FIREWALL_SAFE_PORTS", _lista(arm.get("firewall_safe_ports")
                                           or PADROES["FIREWALL_SAFE_PORTS"]))
        )
    pares.append(("TERMINAL_ENABLE", "1" if cfg.ligado("terminal") else "0"))
    pares.append(("DJANGO_ADMIN_MANAGE", "1" if cfg.ligado("django_admins") else "0"))
    pares.append(("HOST_PROFILE", cfg.slug))
    repo = str(cfg.valor("host", "repo")).rstrip("/")
    pares.append(("APPS_ENV_PATH", f"{repo}/{r['apps']}"))
    return pares


def render_sync_env(cfg: HostConfig) -> list[tuple[str, str]]:
    """Pares do ``sync.env``: o que o ``apps-sync.sh`` lia do `case $PERFIL`."""
    c, r = cfg.secao("caminhos"), cfg.secao("rotas")
    caddy = r.get("caddy") or {}
    caddy_dir = str(caddy.get("dir", "")).rstrip("/")
    pihole_dir = str(r["pihole_dir"]).rstrip("/")
    upstream = r["upstream"]
    host_upstream = {
        "lan": r["dns_ip"],
        "localhost": "localhost",
    }.get(upstream, "")
    return [
        ("SCHEME", r["esquema"]),
        ("DATA_DIR", c["dados_app"]),
        ("STACKS_ROOT", c["stacks"]),
        ("CADDY_DIR", caddy_dir),
        ("CADDY_CONTAINER", caddy.get("container", "")),
        ("CADDYFILE", caddy_dir + "/Caddyfile" if caddy_dir else ""),
        ("CADDY_APPS", caddy_dir + "/apps.caddy" if caddy_dir else ""),
        ("CADDY_TOKEN_FILE", caddy_dir + "/cloudflare.token" if caddy_dir else ""),
        ("CADDY_PORTA", caddy.get("porta", "")),
        ("CADDY_TLS", caddy.get("tls", "")),
        ("CADDY_PROXY", caddy.get("proxy", "")),
        ("PIHOLE_CONTAINER", r.get("pihole_container", "pihole")),
        ("PIHOLE_DIR", pihole_dir),
        ("DNS_CONF", r.get("dns_conf", "")),
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


def _unit_mount(ponto: str) -> str:
    """``/mnt/nas`` -> ``mnt-nas.mount`` (nome que o systemd usa)."""
    return str(ponto).strip("/").replace("/", "-") + ".mount"


def texto_unit(cfg: HostConfig) -> str:
    """Unit de boot do host, do ``[boot]`` do TOML.

    Host sem ``[boot]`` nao tem unit propria (o Compose sobe com restart); o
    Pi tem, e a unit inclui os stacks de terceiros na ordem certa.
    """
    boot = cfg.secao("boot")
    if not boot:
        raise ConfigError(f"{cfg.origem}: host '{cfg.slug}' nao tem [boot]")
    lan_ip = cfg.valor("host", "lan_ip")
    repo = str(cfg.valor("host", "repo")).rstrip("/")
    config = str(cfg.valor("caminhos", "config")).rstrip("/")
    mounts = " ".join(_unit_mount(m) for m in boot.get("esperar_mounts") or ())
    after = "docker.service network-online.target"
    if mounts:
        after += " " + mounts

    passos = []
    if boot.get("esperar_ip", True):
        passos.append(
            f'until ip -4 addr show | grep -q "inet {lan_ip}/"; do sleep 1; done'
        )
    for caminho in boot.get("antes") or ():
        passos.append(f"cd {caminho} && docker compose up -d")
    passos.append(
        f"cd {repo} && set -a && . {config}/host.env && set +a && "
        'docker compose -f docker-compose.yml -f "$COMPOSE_OVERLAY" '
        "up -d --force-recreate"
    )
    for caminho in boot.get("depois") or ():
        passos.append(f"cd {caminho} && docker compose up -d --force-recreate")
    return (
        "[Unit]\n"
        f"Description={boot['descricao']}\n"
        f"After={after}\n"
        "Requires=docker.service\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        "RemainAfterExit=yes\n"
        "TimeoutStartSec=300\n"
        f"ExecStart=/bin/sh -c '{'; '.join(passos)}'\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


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

"""Deteccao read-only do host para o `homelabctl detect` e o wizard.

Nada aqui escreve no sistema: os comandos sao de leitura (`lsblk`, `findmnt`,
`ip`, `systemctl`, `docker`) e o resultado vira uma **proposta** de
`hosts/<slug>/host.toml`. Quem decide e o dono, no `init`; o render/formatar
disco continua sendo acao explicita fora do wizard (regra 5).

O runner e injetavel para os testes (fixtures de saida real de cada comando).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REPO_PADRAO = "/opt/stacks/homelab-storage-admin"
PORTA_PADRAO = 8060

# Onde o wizard procura dados/backup quando o host nao tem nada montado.
RAIZES_DADOS = ("/srv", "/mnt", "/data", "/media")
RAIZES_BACKUP = ("/mnt", "/media", "/srv")


class DetectError(RuntimeError):
    """Nao foi possivel detectar o minimo para propor um host."""


def rodar(cmd: list[str]) -> str:
    """Runner padrao: comando de leitura, sem shell, sem sudo."""
    try:
        saida = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return saida.stdout if saida.returncode == 0 else ""


@dataclass(frozen=True)
class Disco:
    device: str
    tamanho: str
    modelo: str
    transporte: str
    rotacional: bool
    pontos: tuple[str, ...] = ()
    fstype: str = ""
    removivel: bool = False


@dataclass
class Sistema:
    hostname: str
    usuario: str
    lan_ip: str
    repo: str
    discos: list[Disco] = field(default_factory=list)
    montagens: list[tuple[str, str, str]] = field(default_factory=list)
    comandos: set[str] = field(default_factory=set)
    containers: list[str] = field(default_factory=list)
    hoje: str = field(default_factory=lambda: date.today().isoformat())

    def tem(self, comando: str) -> bool:
        return comando in self.comandos

    def container(self, prefixo: str) -> str:
        for nome in self.containers:
            if nome == prefixo or nome.endswith("-" + prefixo):
                return nome
        return ""


def _json(runner, cmd: list[str]) -> dict:
    texto = runner(cmd).strip()
    if not texto:
        return {}
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return {}


def _discos(saida_lsblk: dict) -> list[Disco]:
    discos: list[Disco] = []
    for bloco in saida_lsblk.get("blockdevices") or []:
        if bloco.get("type") != "disk":
            continue
        pontos: list[str] = []
        fstype = bloco.get("fstype") or ""
        for filho in bloco.get("children") or []:
            if filho.get("mountpoint"):
                pontos.append(filho["mountpoint"])
            fstype = fstype or (filho.get("fstype") or "")
        if bloco.get("mountpoint"):
            pontos.insert(0, bloco["mountpoint"])
        discos.append(
            Disco(
                device="/dev/" + str(bloco.get("name")),
                tamanho=str(bloco.get("size") or ""),
                modelo=str(bloco.get("model") or "").strip(),
                transporte=str(bloco.get("tran") or ""),
                rotacional=bool(bloco.get("rota")),
                pontos=tuple(pontos),
                fstype=fstype,
                removivel=bool(bloco.get("rm")),
            )
        )
    return discos


def detectar(runner=rodar) -> Sistema:
    hostname = os.environ.get("HOSTNAME") or ""
    if not hostname:
        hostname = Path("/etc/hostname").read_text(encoding="utf-8").strip()
        if not hostname:
            raise DetectError("nao consegui ler o hostname")
    usuario = os.environ.get("SUDO_USER") or os.environ.get("USER") or ""

    discos = _discos(_json(runner, ["lsblk", "-J", "-o", "NAME,SIZE,TYPE,MODEL,TRAN,ROTA,RM,FSTYPE,MOUNTPOINT"]))

    montagens: list[tuple[str, str, str]] = []
    for m in _json(runner, ["findmnt", "-J", "-o", "TARGET,SOURCE,FSTYPE"]).get(
        "filesystems"
    ) or []:
        montagens.append(
            (m.get("target", ""), m.get("source", ""), m.get("fstype", ""))
        )

    lan_ip = ""
    rota = _json(runner, ["ip", "-j", "route", "show", "default"])
    if isinstance(rota, list) and rota:
        lan_ip = rota[0].get("prefsrc", "")
    if not lan_ip:
        for entrada in _json(runner, ["ip", "-j", "addr"]).get("addr_info") or []:
            if entrada.get("family") == "inet" and entrada.get("scope") == "global":
                lan_ip = entrada.get("local", "")
                break
    if not lan_ip:
        raise DetectError("nao consegui descobrir o IP da LAN (ip route/addr)")

    repo = os.environ.get("HOMELAB_REPO", "")
    if not repo:
        candidato = str(RAIZ)
        repo = candidato if candidato.startswith("/opt/") else REPO_PADRAO

    comandos = set()
    for nome in (
        "pdbedit", "smbpasswd", "parted", "mkfs.ext4", "btrfs", "rsync",
        "restic", "smartctl", "ufw", "apt-get", "systemctl", "docker",
    ):
        if runner(["sh", "-c", f"command -v {nome}"]).strip():
            comandos.add(nome)

    containers = [
        linha.strip()
        for linha in runner(["docker", "ps", "-a", "--format", "{{.Names}}"]).splitlines()
        if linha.strip()
    ]

    return Sistema(
        hostname=hostname.split(".")[0],
        usuario=usuario,
        lan_ip=lan_ip,
        repo=repo,
        discos=discos,
        montagens=montagens,
        comandos=comandos,
        containers=containers,
    )


# --- proposta -------------------------------------------------------------

def _slug(hostname: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", hostname.lower()).strip("-")
    return slug or "host"


def _maior_montagem(sistema: Sistema, raizes: tuple[str, ...]) -> tuple[str, str]:
    """Primeiro `(ponto, fstype)` sob `raizes`, ignorando pseudo-filesystems."""
    pseudos = {"proc", "sysfs", "tmpfs", "devtmpfs", "overlay", "squashfs", "cgroup2"}
    for ponto, _origem, fstype in sistema.montagens:
        if fstype in pseudos or ponto == "/":
            continue
        if ponto.startswith(tuple(r + "/" for r in raizes)):
            return ponto, fstype
    return "", ""


def _papel_do_disco(disco: Disco, dados: str) -> list[str]:
    papeis: list[str] = []
    if dados and dados in disco.pontos:
        papeis.append("dados")
        if disco.fstype == "btrfs":
            papeis.append("snapshot")
    elif disco.removivel or disco.transporte == "usb":
        papeis.append("backup")
    return papeis


def propor(sistema: Sistema) -> dict:
    """Estrutura equivalente ao TOML (o texto sai de `texto_toml`)."""
    slug = _slug(sistema.hostname)
    dados, fstype_dados = _maior_montagem(sistema, RAIZES_DADOS)
    backup, _ = _maior_montagem(sistema, RAIZES_BACKUP)
    if backup in ("", dados):
        backup = "/mnt/backup"

    discos = []
    for disco in sistema.discos:
        papeis = _papel_do_disco(disco, dados)
        discos.append(
            {
                "device": disco.device,
                "tamanho": disco.tamanho,
                "modelo": disco.modelo,
                "removivel": disco.removivel,
                "fstype": disco.fstype,
                "papel": papeis,
            }
        )

    caddy = sistema.container("caddy")
    pihole = sistema.container("pihole")
    upstream = "nenhum"
    if caddy:
        upstream = "localhost"

    montagens = [ponto for ponto, _o, _f in sistema.montagens if ponto != "/"]
    mounts = ["/"] + [m for m in montagens if m and not m.startswith("/run")]

    features = {
        "samba": sistema.tem("pdbedit") or bool(sistema.container("samba")),
        "discos": sistema.tem("parted") and sistema.tem("mkfs.ext4"),
        "snapshots": sistema.tem("btrfs") or sistema.tem("rsync"),
        "restic": sistema.tem("restic"),
        "copia_fria": sistema.tem("restic") or sistema.tem("rsync"),
        "ufw": sistema.tem("ufw"),
        "terminal": sistema.tem("systemctl"),
        "apt": sistema.tem("apt-get"),
        "qbittorrent": bool(sistema.container("qbittorrent")),
        "jellyfin": bool(sistema.container("jellyfin")),
        "pihole": bool(pihole),
        "gitea": bool(sistema.container("gitea")),
        "portal": False,
        "credenciais": False,
        "django_admins": False,
    }

    return {
        "host": {
            "nome": slug,
            "descricao": f"{sistema.hostname} (detectado em {sistema.hoje})",
            "ssh": f"{sistema.usuario}@{sistema.hostname}" if sistema.usuario else "",
            "lan_ip": sistema.lan_ip,
            "repo": sistema.repo,
        },
        "app": {
            "site_name": f"{sistema.hostname} Storage",
            "bind_addr": sistema.lan_ip,
            "bind_port": PORTA_PADRAO,
            "compose_overlay": "",
        },
        "caminhos": {
            "dados": dados or "/srv/dados",
            "snapshots": (dados or "/srv/dados").rstrip("/") + "/.snapshots",
            "backup": backup,
            "dados_app": (dados or "/srv/dados").rstrip("/")
            + "/apps/homelab-storage-admin/data",
            "stacks": "/opt",
            "quarentena": "/opt/stacks/_removidos",
            "estado": "/var/lib/homelab-storage-admin",
            "sockets": "/run/homelab-storage-admin",
            "config": "/etc/homelab-storage-admin",
        },
        "armazenamento": {
            "proprietario": sistema.usuario or "root",
            "snapshot_backend": "auto" if fstype_dados == "btrfs" else "rsync",
            "snapshot_denylist": "",
            "prefixos_permitidos": [dados or "/srv/dados"],
            "mounts": mounts or ["/"],
            "firewall_safe_ports": [
                "22/tcp", "80/tcp", "443/tcp", f"{PORTA_PADRAO}/tcp", "445/tcp",
            ],
        },
        "rotas": {
            "esquema": "http",
            "apps": f"deploy/{slug}/apps.env",
            "dominio": "local",
            "dns_ip": sistema.lan_ip,
            "dns_modo": "nome" if pihole else "nenhum",
            "dns_conf": f"/opt/stacks/pihole/etc-dnsmasq.d/10-{slug}-local.conf",
            "pihole_dir": "/opt/stacks/pihole",
            "pihole_container": pihole or "pihole",
            "upstream": upstream,
            "dirs_permitidos": ["/opt/stacks", "/opt"],
            "scan_roots": ["/opt"],
            "caddy": {
                "dir": "/opt/stacks/caddy",
                "container": caddy or "",
                "porta": "",
                "tls": "",
                "proxy": "reverse_proxy",
            }
            if caddy
            else {},
        },
        "discos": discos,
        "features": features,
    }


def _esc(valor: str) -> str:
    return '"' + str(valor).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _lista(valores) -> str:
    return "[" + ", ".join(_esc(v) for v in valores) + "]"


SECOES_TOML = (
    "host", "app", "caminhos", "armazenamento", "rotas", "features",
)


def texto_toml(proposta: dict) -> str:
    """TOML com comentarios onde o dono precisa revisar antes de confiar."""
    host, app = proposta["host"], proposta["app"]
    caminhos = proposta["caminhos"]
    arm = proposta["armazenamento"]
    rotas = proposta["rotas"]
    linhas = [
        f"# Proposta de hosts/{host['nome']}/host.toml gerada por `homelabctl detect`.",
        "# Leitura apenas: revise caminhos, IP e papeis dos discos antes de",
        "# confiar no arquivo (o wizard `homelabctl init` faz isso passo a passo).",
        "# Segredos NAO entram aqui: ficam em .env (container) e no ambiente do agente.",
        "",
        "[host]",
        f"nome = {_esc(host['nome'])}",
        f"descricao = {_esc(host['descricao'])}",
        f"ssh = {_esc(host['ssh'])}",
        f"lan_ip = {_esc(host['lan_ip'])}",
        f"repo = {_esc(host['repo'])}",
        "",
        "[app]",
        f"site_name = {_esc(app['site_name'])}",
        f"bind_addr = {_esc(app['bind_addr'])}",
        f"bind_port = {app['bind_port']}",
        "# Vazio usa so o docker-compose.yml, sem overlay.",
        f"compose_overlay = {_esc(app['compose_overlay'])}",
        "",
        "[caminhos]",
    ]
    for chave in (
        "dados", "snapshots", "backup", "dados_app", "stacks",
        "quarentena", "estado", "sockets", "config",
    ):
        linhas.append(f"{chave} = {_esc(caminhos[chave])}")
    linhas += [
        "",
        "[armazenamento]",
        f"proprietario = {_esc(arm['proprietario'])}",
        f"snapshot_backend = {_esc(arm['snapshot_backend'])}",
        f"snapshot_denylist = {_esc(arm['snapshot_denylist'])}",
        f"prefixos_permitidos = {_lista(arm['prefixos_permitidos'])}",
        f"mounts = {_lista(arm['mounts'])}",
        f"firewall_safe_ports = {_lista(arm['firewall_safe_ports'])}",
        "",
        "[rotas]",
        f"esquema = {_esc(rotas['esquema'])}",
        f"apps = {_esc(rotas['apps'])}",
        f"dominio = {_esc(rotas['dominio'])}",
        f"dns_ip = {_esc(rotas['dns_ip'])}",
        f"# wildcard, nome ou nenhum. Sem Pi-hole detectado, fica nenhum.",
        f"dns_modo = {_esc(rotas['dns_modo'])}",
        f"dns_conf = {_esc(rotas['dns_conf'])}",
        f"pihole_dir = {_esc(rotas['pihole_dir'])}",
        f"pihole_container = {_esc(rotas['pihole_container'])}",
        f"# lan (Caddy fala com o IP), localhost (compose em 127.0.0.1) ou nenhum.",
        f"upstream = {_esc(rotas['upstream'])}",
        f"dirs_permitidos = {_lista(rotas['dirs_permitidos'])}",
        f"scan_roots = {_lista(rotas['scan_roots'])}",
    ]
    caddy = rotas.get("caddy") or {}
    if caddy:
        linhas += [
            "",
            "[rotas.caddy]",
            f"dir = {_esc(caddy['dir'])}",
            f"container = {_esc(caddy['container'])}",
            f"porta = {_esc(caddy['porta'])}",
            f"tls = {_esc(caddy['tls'])}",
            f"proxy = {_esc(caddy['proxy'])}",
        ]
    if proposta["discos"]:
        linhas += ["", "# Papeis vazios = disco fora do app (nao sera montado nem formatado)."]
        for disco in proposta["discos"]:
            linhas += [
                "",
                "[[discos]]",
                f"device = {_esc(disco['device'])}",
                f"tamanho = {_esc(disco['tamanho'])}",
                f"modelo = {_esc(disco['modelo'])}",
                f"removivel = {'true' if disco['removivel'] else 'false'}",
                f"papel = {_lista(disco['papel'])}",
            ]
    linhas += ["", "[features]"]
    for nome, ligado in proposta["features"].items():
        linhas.append(f"{nome} = {'true' if ligado else 'false'}")
    return "\n".join(linhas) + "\n"

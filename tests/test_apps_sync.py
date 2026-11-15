"""Testes do reconciler de apps (scripts/stacks/apps-sync.sh).

Rodam num sandbox: STACKS_ROOT/estado/Caddyfile apontam para tmp_path e
docker/dig sao stubs no PATH. Nada toca o host de verdade.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "stacks" / "apps-sync.sh"

CADDYFILE = """\
(cf) {
\ttls {
\t\tdns cloudflare {env.CLOUDFLARE_API_TOKEN}
\t}
}

(proxy) {
\treverse_proxy {args[0]} {
\t\theader_up Host {host}
\t}
}

http://homelab.lan, http://dockge.lan {
\trespond "Nome .lan removido" 410
}

homelab.conradhub.com {
\timport cf
\timport proxy 192.168.0.150:8060
}

dockge.conradhub.com {
\timport cf
\timport proxy 192.168.0.150:5001
}

jellyfin.conradhub.com {
\timport cf
\t@bloqueio {
\t\tclient_ip 100.64.0.0/10
\t}
\thandle @bloqueio {
\t\trespond "Playback fora da LAN" 403
\t}
\timport proxy 192.168.0.150:8096
}
"""

APPS_ENV = """\
# teste
homelab|homelab.conradhub.com|192.168.0.150:8060|/opt/stacks/homelab-storage-admin|
dockge|dockge.conradhub.com|192.168.0.150:5001|/opt/dockge|
jellyfin|jellyfin.conradhub.com|192.168.0.150:8096|/opt/stacks/jellyfin|manual
"""

DOCKER_STUB = """\
#!/usr/bin/env bash
echo "docker $*" >> "$STUB_LOG"
case "$1" in
  ps)
    projeto=""
    dir=""
    formato=""
    anterior=""
    for a in "$@"; do
      [[ "$anterior" == "--format" ]] && formato=$a
      anterior=$a
      case "$a" in
        label=com.docker.compose.project.working_dir=*) dir=${a##*=} ;;
        label=com.docker.compose.project=*) projeto=${a##*=} ;;
      esac
    done
    if [[ -z "$dir" && -z "$projeto" && "$formato" == *Label* ]]; then
      while IFS='|' read -r d p; do
        printf 'container-%s	%s	%s
' "$p" "$p" "$d"
      done <"${STUB_DIR_PROJETOS:-/dev/null}"
      exit 0
    fi
    if [[ -n "$dir" ]]; then
      projeto=$(awk -F'|' -v d="$dir" '$1 == d { print $2 }' \\
        "${STUB_DIR_PROJETOS:-/dev/null}" 2>/dev/null)
      [[ -n "$projeto" ]] || projeto=${dir##*/}
    fi
    if [[ -n "$projeto" ]] && grep -qx "$projeto" "$STUB_PROJETOS" 2>/dev/null; then
      if [[ "$formato" == *Label* ]]; then
        echo "$projeto"
      else
        echo "container-$projeto"
      fi
    fi
    exit 0
    ;;
  exec)
    if [[ "$*" == *"pihole.toml"* ]]; then
      [[ -n "${STUB_PIHOLE_HOSTS:-}" ]] && printf "%s\n" "$STUB_PIHOLE_HOSTS"
      exit 0
    fi
    if [[ "$*" == *"test -f /etc/caddy/apps.caddy"* && "${STUB_SEM_MOUNT:-0}" == "1" ]]; then
      exit 1
    fi
    if [[ "$*" == *"misc.etc_dnsmasq_d true"* ]]; then
      echo true >"$STUB_DNSMASQ_D"
      echo true
      exit 0
    fi
    if [[ "$*" == *"misc.etc_dnsmasq_d"* ]]; then
      cat "$STUB_DNSMASQ_D" 2>/dev/null || echo true
      exit 0
    fi
    exit 0
    ;;
  port)
    if [[ -n "${STUB_PORTAS:-}" ]]; then
      tr ',' '\n' <<<"$STUB_PORTAS" | sed 's/^/x\/tcp -> 0.0.0.0:/'
    else
      echo "8080/tcp -> 0.0.0.0:8080"
    fi
    exit 0
    ;;
  compose)
    projeto=""
    anterior=""
    for a in "$@"; do
      [[ "$anterior" == "-p" ]] && projeto=$a
      anterior=$a
    done
    if [[ -n "$projeto" ]]; then
      grep -vx "$projeto" "$STUB_PROJETOS" >"$STUB_PROJETOS.tmp" 2>/dev/null || true
      mv "$STUB_PROJETOS.tmp" "$STUB_PROJETOS"
    fi
    exit 0
    ;;
esac
exit 0
"""

DIG_STUB = """\
#!/usr/bin/env bash
echo "dig $*" >> "$STUB_LOG"
echo "${STUB_DIG_RESULT:-192.168.0.150}"
"""


class Sandbox:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.root = tmp_path / "root"
        self.stacks = self.root / "opt"
        self.caddy_dir = self.stacks / "stacks" / "caddy"
        self.caddyfile = self.caddy_dir / "Caddyfile"
        self.apps_caddy = self.caddy_dir / "apps.caddy"
        self.dns_conf = (
            self.stacks / "stacks" / "pihole" / "etc-dnsmasq.d"
            / "10-conradhub.com-wildcard.conf"
        )
        self.state = tmp_path / "var" / "apps.aplicados"
        self.env_file = tmp_path / "apps.env"
        self.quarantine = self.stacks / "stacks" / "_removidos"
        self.log = tmp_path / "chamadas.log"
        self.projetos = tmp_path / "projetos"
        self.dir_projetos = tmp_path / "dir_projetos"
        self.dnsmasq_flag = tmp_path / "dnsmasq_d"
        self.bin = tmp_path / "bin"
        self.dir_homelab = self.stacks / "stacks" / "homelab-storage-admin"
        self.dir_dockge = self.stacks / "dockge"
        self.dir_jellyfin = self.stacks / "stacks" / "jellyfin"
        self.dir_pihole = self.stacks / "stacks" / "pihole"
        self.services_ini = tmp_path / "data" / "services.ini"
        self.portal_ini = tmp_path / "state" / "apps-portal.ini"

        for caminho in (
            self.caddy_dir,
            self.stacks / "stacks" / "pihole" / "etc-dnsmasq.d",
            self.dir_homelab,
            self.dir_dockge,
            self.dir_jellyfin,
            (tmp_path / "var"),
            self.services_ini.parent,
            self.portal_ini.parent,
            self.bin,
        ):
            caminho.mkdir(parents=True, exist_ok=True)

        self.caddyfile.write_text(CADDYFILE, encoding="utf-8")
        self.env_file.write_text(self.env_text(), encoding="utf-8")
        self.projetos.write_text("homelab-storage-admin\ndockge\njellyfin\n", encoding="utf-8")
        self.dir_projetos.write_text("", encoding="utf-8")
        self.dnsmasq_flag.write_text("true\n", encoding="utf-8")
        (self.caddy_dir / "cloudflare.token").write_text("token\n", encoding="utf-8")

        docker = self.bin / "docker"
        docker.write_text(DOCKER_STUB, encoding="utf-8")
        docker.chmod(0o755)
        dig = self.bin / "dig"
        dig.write_text(DIG_STUB, encoding="utf-8")
        dig.chmod(0o755)

    def env_text(self, extra: str = "") -> str:
        return APPS_ENV.replace("/opt", str(self.stacks)) + extra

    def escreve_env(self, extra: str = "") -> None:
        self.env_file.write_text(self.env_text(extra), encoding="utf-8")

    def run(
        self, *args: str, env_file: Path | None = None, env_extra: dict | None = None
    ) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "TEST_MODE": "1",
            "APPS_ENV": str(env_file or self.env_file),
            "APPS_STATE": str(self.state),
            "STACKS_ROOT": str(self.stacks),
            "CADDYFILE": str(self.caddyfile),
            "CADDY_APPS": str(self.apps_caddy),
            "DNS_CONF": str(self.dns_conf),
            "QUARANTINE": str(self.quarantine),
            "SERVICES_INI": str(self.services_ini),
            "PORTAL_INI": "",
            "STUB_LOG": str(self.log),
            "STUB_PROJETOS": str(self.projetos),
            "STUB_DIR_PROJETOS": str(self.dir_projetos),
            "STUB_DNSMASQ_D": str(self.dnsmasq_flag),
            "STUB_DIG_RESULT": "192.168.0.150",
            "STUB_SEM_MOUNT": os.environ.get("STUB_SEM_MOUNT", "0"),
            **(env_extra or {}),
        }
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def chamadas(self) -> str:
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""


def test_help_nao_toca_nada(tmp_path):
    sandbox = Sandbox(tmp_path)
    resultado = sandbox.run("--help")
    assert resultado.returncode == 0
    assert "apps-sync.sh" in resultado.stdout
    assert not sandbox.apps_caddy.exists()


def test_dry_run_nao_escreve(tmp_path):
    sandbox = Sandbox(tmp_path)
    resultado = sandbox.run()
    assert resultado.returncode == 0, resultado.stderr
    assert "plano (dry-run" in resultado.stdout
    assert "rota: homelab.conradhub.com -> 192.168.0.150:8060" in resultado.stdout
    assert not sandbox.apps_caddy.exists()
    assert not sandbox.state.exists()
    assert not sandbox.dns_conf.exists()
    assert sandbox.caddyfile.read_text(encoding="utf-8") == CADDYFILE


def test_apply_gera_caddy_dns_e_estado(tmp_path):
    sandbox = Sandbox(tmp_path)
    resultado = sandbox.run("--apply")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    apps = sandbox.apps_caddy.read_text(encoding="utf-8")
    assert "homelab.conradhub.com {\n\timport cf\n\timport proxy 192.168.0.150:8060\n}" in apps
    assert "dockge.conradhub.com {\n\timport cf\n\timport proxy 192.168.0.150:5001\n}" in apps
    assert "jellyfin" not in apps  # manual fica no Caddyfile

    caddyfile = sandbox.caddyfile.read_text(encoding="utf-8")
    assert caddyfile.count("import apps.caddy") == 1
    assert "homelab.conradhub.com {" not in caddyfile
    assert "dockge.conradhub.com {" not in caddyfile
    assert "jellyfin.conradhub.com {" in caddyfile
    assert "respond \"Nome .lan removido\" 410" in caddyfile

    assert sandbox.dns_conf.read_text(encoding="utf-8").splitlines()[-1] == (
        "address=/conradhub.com/192.168.0.150"
    )

    estado = sandbox.state.read_text(encoding="utf-8")
    assert (
        f"homelab|homelab.conradhub.com|192.168.0.150:8060|{sandbox.dir_homelab}|" in estado
    )
    assert (
        f"jellyfin|jellyfin.conradhub.com|192.168.0.150:8096|{sandbox.dir_jellyfin}|manual"
        in estado
    )

    chamadas = sandbox.chamadas()
    assert "caddy validate --config /etc/caddy/Caddyfile" in chamadas
    assert "caddy reload --config /etc/caddy/Caddyfile" in chamadas


def test_apply_e_idempotente(tmp_path):
    sandbox = Sandbox(tmp_path)
    assert sandbox.run("--apply").returncode == 0
    antes = sandbox.caddyfile.read_text(encoding="utf-8")
    apps_antes = sandbox.apps_caddy.read_text(encoding="utf-8")

    resultado = sandbox.run("--apply")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "apps.caddy sem mudanca" in resultado.stdout
    assert "Caddy ja estava com a configuracao do env" in resultado.stdout
    assert sandbox.caddyfile.read_text(encoding="utf-8") == antes
    assert sandbox.apps_caddy.read_text(encoding="utf-8") == apps_antes
    assert sandbox.caddyfile.read_text(encoding="utf-8").count("import apps.caddy") == 1


def test_env_invalido_falha_sem_escrever(tmp_path):
    sandbox = Sandbox(tmp_path)
    invalido = tmp_path / "invalido.env"
    invalido.write_text(
        "homelab|homelab.example.com|192.168.0.150:8060|/opt/stacks/homelab-storage-admin|\n"
        "outro|outro.conradhub.com|sem-porta|/etc/passwd|\n"
        "com-flag|flag.conradhub.com|127.0.0.1:80|/opt/stacks/com-flag|foo\n",
        encoding="utf-8",
    )
    resultado = sandbox.run("--apply", env_file=invalido)
    assert resultado.returncode == 2
    assert "fora de .conradhub.com" in resultado.stderr
    assert "upstream" in resultado.stderr
    assert "fora de" in resultado.stderr
    assert "flag desconhecida" in resultado.stderr
    assert not sandbox.apps_caddy.exists()
    assert sandbox.caddyfile.read_text(encoding="utf-8") == CADDYFILE


def test_conflito_com_bloco_complexo_aborta(tmp_path):
    sandbox = Sandbox(tmp_path)
    sandbox.caddyfile.write_text(
        CADDYFILE.replace(
            "dockge.conradhub.com {\n\timport cf\n\timport proxy 192.168.0.150:5001\n}",
            "dockge.conradhub.com {\n\t@x path /a\n\thandle @x {\n\t\trespond 200\n\t}\n}",
        ),
        encoding="utf-8",
    )
    antes = sandbox.caddyfile.read_text(encoding="utf-8")
    resultado = sandbox.run("--apply")
    assert resultado.returncode == 2
    assert "conflito" in resultado.stdout + resultado.stderr
    assert sandbox.caddyfile.read_text(encoding="utf-8") == antes


def test_prune_move_pasta_para_quarentena(tmp_path):
    sandbox = Sandbox(tmp_path)
    assert sandbox.run("--apply").returncode == 0

    velho = sandbox.stacks / "stacks" / "velho"
    velho.mkdir()
    (velho / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    with sandbox.state.open("a", encoding="utf-8") as arquivo:
        arquivo.write(f"velho|velho.conradhub.com|127.0.0.1:9999|{velho}|\n")
    sandbox.projetos.write_text(
        sandbox.projetos.read_text(encoding="utf-8") + "velho\n", encoding="utf-8"
    )

    resultado = sandbox.run("--apply", "--prune-containers", "--prune-data", "--yes")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert not velho.exists()
    destino = list(sandbox.quarantine.glob("velho-*"))
    assert len(destino) == 1
    assert (destino[0] / "compose.yaml").exists()
    assert "compose -p velho down" in sandbox.chamadas()
    estado = sandbox.state.read_text(encoding="utf-8")
    assert "velho|" not in estado


def test_sem_estado_nao_poda_nada(tmp_path):
    sandbox = Sandbox(tmp_path)
    orfa = sandbox.stacks / "stacks" / "orfa"
    orfa.mkdir()
    (orfa / "compose.yaml").write_text("services: {}\n", encoding="utf-8")

    resultado = sandbox.run("--apply", "--prune-containers", "--prune-data", "--yes")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert orfa.exists()
    assert "compose -p orfa down" not in sandbox.chamadas()


def test_infra_nao_vai_para_quarentena(tmp_path):
    sandbox = Sandbox(tmp_path)
    sandbox.escreve_env()
    assert sandbox.run("--apply").returncode == 0

    # pihole estava declarada no estado e sai do env agora.
    sandbox.escreve_env(
        "pihole|pihole.conradhub.com|127.0.0.1:8080|" + str(sandbox.dir_pihole) + "|\n"
    )
    assert sandbox.run("--apply").returncode == 0
    sandbox.escreve_env()
    resultado = sandbox.run("--apply", "--prune-containers", "--prune-data", "--yes")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert (sandbox.stacks / "stacks" / "pihole").exists()
    assert "acao manual" in resultado.stderr


def test_prune_data_exige_prune_containers(tmp_path):
    sandbox = Sandbox(tmp_path)
    resultado = sandbox.run("--apply", "--prune-data", "--yes")
    assert resultado.returncode == 2
    assert "--prune-containers" in resultado.stderr


def test_prune_sem_apply_nao_roda(tmp_path):
    sandbox = Sandbox(tmp_path)
    resultado = sandbox.run("--prune-containers")
    assert resultado.returncode == 2
    assert "--apply" in resultado.stderr


def test_apply_sem_root_recusa(tmp_path):
    sandbox = Sandbox(tmp_path)
    env = {
        **os.environ,
        "PATH": f"{sandbox.bin}:{os.environ['PATH']}",
        "APPS_ENV": str(sandbox.env_file),
        "APPS_STATE": str(sandbox.state),
        "STACKS_ROOT": str(sandbox.stacks),
        "CADDYFILE": str(sandbox.caddyfile),
        "CADDY_APPS": str(sandbox.apps_caddy),
        "DNS_CONF": str(sandbox.dns_conf),
    }
    resultado = subprocess.run(
        ["bash", str(SCRIPT), "--apply"], capture_output=True, text=True, env=env, check=False
    )
    if os.geteuid() == 0:
        assert resultado.returncode == 0
    else:
        assert resultado.returncode == 2
        assert "root" in resultado.stderr


def test_sem_mount_do_apps_caddy_aborta_antes_do_caddyfile(tmp_path):
    sandbox = Sandbox(tmp_path)
    os.environ["STUB_SEM_MOUNT"] = "1"
    try:
        resultado = sandbox.run("--apply")
    finally:
        os.environ.pop("STUB_SEM_MOUNT", None)
    assert resultado.returncode == 2
    assert "apps.caddy" in resultado.stderr
    assert "./:/etc/caddy:ro" in resultado.stderr
    assert sandbox.caddyfile.read_text(encoding="utf-8") == CADDYFILE


def test_avisa_entrada_exata_do_pihole_fora_do_env(tmp_path):
    sandbox = Sandbox(tmp_path)
    sandbox.env_file.write_text(
        "homelab|homelab.conradhub.com|192.168.0.150:8060|"
        f"{sandbox.dir_homelab}|\n",
        encoding="utf-8",
    )
    resultado = sandbox.run(
        env_extra={
            "STUB_PIHOLE_HOSTS": (
                '"192.168.0.150 homelab.conradhub.com"\n'
                '"192.168.0.150 velho.conradhub.com"'
            )
        }
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "entrada exata para velho.conradhub.com" in resultado.stdout
    assert "entrada exata para homelab.conradhub.com" not in resultado.stdout


CADDYFILE_MOYA = """\
moya-git.local:80 {
\treverse_proxy localhost:3000
}

moya-pihole.local:80 {
\tredir / /admin
\treverse_proxy localhost:8888
}

moya-weather.local:80 {
\treverse_proxy 10.72.60.202:80
}
"""

APPS_ENV_MOYA = """\
# teste moya
moya-git|moya-git.local|localhost:3000|<git>|
moya-pihole|moya-pihole.local|localhost:8888|-|redir=/admin
moya-weather|moya-weather.local|10.72.60.202:80|-|
"""


class SandboxMoya:
    """Perfil moya: Caddy inline, DNS por nome em .local, dir `-`."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.root = tmp_path / "root"
        self.fake_home = tmp_path / "home" / "conrado"
        self.caddy_dir = self.fake_home / "caddy"
        self.caddyfile = self.caddy_dir / "Caddyfile"
        self.apps_caddy = self.caddy_dir / "apps.caddy"
        self.pihole_dir = self.fake_home / "pihole"
        self.dns_dir = self.pihole_dir / "etc-dnsmasq.d"
        self.dns_conf = self.dns_dir / "10-apps-local.conf"
        self.state = tmp_path / "var" / "apps.aplicados"
        self.env_file = tmp_path / "apps.env"
        self.quarantine = self.fake_home / "_removidos"
        self.log = tmp_path / "chamadas.log"
        self.projetos = tmp_path / "projetos"
        self.dir_projetos = tmp_path / "dir_projetos"
        self.dnsmasq_flag = tmp_path / "dnsmasq_d"
        self.bin = tmp_path / "bin"
        self.dir_git = self.root / "data" / "compose" / "3"
        self.dir_portainer = self.fake_home / "portainer"
        self.services_ini = tmp_path / "data" / "services.ini"
        self.portal_ini = tmp_path / "state" / "apps-portal.ini"

        for caminho in (
            self.caddy_dir,
            self.dns_dir,
            self.dir_git,
            self.dir_portainer,
            (tmp_path / "var"),
            self.services_ini.parent,
            self.portal_ini.parent,
            self.bin,
        ):
            caminho.mkdir(parents=True, exist_ok=True)

        self.caddyfile.write_text(CADDYFILE_MOYA, encoding="utf-8")
        self.env_file.write_text(self.env_text(), encoding="utf-8")
        self.projetos.write_text("moya-gitea\nportainer\n", encoding="utf-8")
        self.dir_projetos.write_text(f"{self.dir_git}|moya-gitea\n", encoding="utf-8")
        self.dnsmasq_flag.write_text("false\n", encoding="utf-8")

        docker = self.bin / "docker"
        docker.write_text(DOCKER_STUB, encoding="utf-8")
        docker.chmod(0o755)
        dig = self.bin / "dig"
        dig.write_text(DIG_STUB, encoding="utf-8")
        dig.chmod(0o755)

    def env_text(self, extra: str = "") -> str:
        return APPS_ENV_MOYA.replace("<git>", str(self.dir_git)) + extra

    def escreve_env(self, extra: str = "") -> None:
        self.env_file.write_text(self.env_text(extra), encoding="utf-8")

    def run(
        self, *args: str, env_file: Path | None = None, env_extra: dict | None = None
    ) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "TEST_MODE": "1",
            "APPS_ENV": str(env_file or self.env_file),
            "APPS_STATE": str(self.state),
            "STACKS_ROOT": str(self.root / "opt"),
            "CADDY_DIR": str(self.caddy_dir),
            "CADDYFILE": str(self.caddyfile),
            "CADDY_APPS": str(self.apps_caddy),
            "DNS_CONF": str(self.dns_conf),
            "PIHOLE_DIR": str(self.pihole_dir),
            "QUARANTINE": str(self.quarantine),
            "SERVICES_INI": str(self.services_ini),
            "PORTAL_INI": str(self.portal_ini),
            "DIRS_PERMITIDOS": (
                f"{self.root}/opt/stacks {self.root}/opt {self.fake_home} "
                f"{self.root}/data/compose"
            ),
            "SCAN_ROOTS": str(self.root),
            "STUB_LOG": str(self.log),
            "STUB_PROJETOS": str(self.projetos),
            "STUB_DIR_PROJETOS": str(self.dir_projetos),
            "STUB_DNSMASQ_D": str(self.dnsmasq_flag),
            "STUB_DIG_RESULT": "192.168.0.10",
            **(env_extra or {}),
        }
        return subprocess.run(
            ["bash", str(SCRIPT), "--perfil", "moya", *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def chamadas(self) -> str:
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""


def test_moya_dry_run_sem_escrever(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    resultado = sandbox.run()
    assert resultado.returncode == 0, resultado.stderr
    assert "rota: moya-git.local:80 -> localhost:3000" in resultado.stdout
    assert "rota: moya-pihole.local:80 -> localhost:8888" in resultado.stdout
    assert "rota: moya-weather.local:80 -> 10.72.60.202:80" in resultado.stdout
    assert "manual:" not in resultado.stdout
    # O projeto compose vem do rotulo (dir do gitea -> moya-gitea).
    assert "container ok: moya-git -> container-moya-gitea" in resultado.stdout
    assert "pasta ausente: -" not in resultado.stdout
    assert not sandbox.dns_conf.exists()
    assert not sandbox.state.exists()
    assert sandbox.caddyfile.read_text(encoding="utf-8") == CADDYFILE_MOYA


def test_moya_apply_gera_apps_caddy_e_dns_por_nome(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    resultado = sandbox.run("--apply")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    apps = sandbox.apps_caddy.read_text(encoding="utf-8")
    assert "moya-git.local:80 {\n\treverse_proxy localhost:3000\n}" in apps
    assert (
        "moya-pihole.local:80 {\n\tredir / /admin 302\n"
        "\treverse_proxy localhost:8888\n}" in apps
    )
    assert "moya-weather.local:80 {\n\treverse_proxy 10.72.60.202:80\n}" in apps
    assert "import cf" not in apps
    assert "\ttls" not in apps

    caddyfile = sandbox.caddyfile.read_text(encoding="utf-8")
    assert caddyfile.count("import apps.caddy") == 1
    assert "moya-git.local:80 {" not in caddyfile
    assert "moya-pihole.local:80 {" not in caddyfile
    assert "redir / /admin" not in caddyfile  # agora vem de apps.caddy
    assert "\n\n\n" not in caddyfile  # bloco removido nao deixa vazio

    conf = sandbox.dns_conf.read_text(encoding="utf-8")
    enderecos = [l for l in conf.splitlines() if l.startswith("address=")]
    assert enderecos == [
        "address=/moya-git.local/192.168.0.10",
        "address=/moya-pihole.local/192.168.0.10",
        "address=/moya-weather.local/192.168.0.10",
    ]
    assert "address=/local/" not in conf

    estado = sandbox.state.read_text(encoding="utf-8")
    assert "moya-pihole|moya-pihole.local|localhost:8888|-|redir=/admin" in estado
    assert f"moya-git|moya-git.local|localhost:3000|{sandbox.dir_git}|" in estado

    chamadas = sandbox.chamadas()
    assert "exec moya-caddy caddy validate" in chamadas
    assert "exec moya-caddy caddy reload" in chamadas
    assert "misc.etc_dnsmasq_d true" in chamadas
    assert "restart pihole" in chamadas
    assert sandbox.dnsmasq_flag.read_text(encoding="utf-8").strip() == "true"


def test_moya_apply_e_idempotente(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    assert sandbox.run("--apply").returncode == 0
    antes = sandbox.caddyfile.read_text(encoding="utf-8")
    apps_antes = sandbox.apps_caddy.read_text(encoding="utf-8")
    conf_antes = sandbox.dns_conf.read_text(encoding="utf-8")
    sandbox.log.unlink()

    resultado = sandbox.run("--apply")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "apps.caddy sem mudanca" in resultado.stdout
    assert "Caddy ja estava com a configuracao do env" in resultado.stdout
    assert "DNS sem mudanca" in resultado.stdout
    assert "Pi-hole reiniciado" not in resultado.stdout
    assert sandbox.caddyfile.read_text(encoding="utf-8") == antes
    assert sandbox.apps_caddy.read_text(encoding="utf-8") == apps_antes
    assert sandbox.dns_conf.read_text(encoding="utf-8") == conf_antes


def test_moya_dir_sem_stack_gera_rota(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    env = tmp_path / "sem-stack.env"
    env.write_text(
        "remota|remota.local|10.0.0.9:80|-|\n", encoding="utf-8"
    )
    plano = sandbox.run(env_file=env)
    assert "rota: remota.local:80 -> 10.0.0.9:80" in plano.stdout
    resultado = sandbox.run("--apply", env_file=env)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert (
        "remota.local:80 {\n\treverse_proxy 10.0.0.9:80\n}"
        in sandbox.apps_caddy.read_text(encoding="utf-8")
    )


def test_moya_bloco_aninhado_no_caddyfile_aborta(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    sandbox.caddyfile.write_text(
        "moya-git.local:80 {\n\thandle {\n\t\trespond 200\n\t}\n}\n",
        encoding="utf-8",
    )
    resultado = sandbox.run("--apply")
    assert resultado.returncode == 2
    assert "chaves aninhadas" in resultado.stdout
    assert "handle {" in sandbox.caddyfile.read_text(encoding="utf-8")


def test_env_do_pi_valida(tmp_path):
    sandbox = Sandbox(tmp_path)
    env = ROOT / "deploy" / "pi" / "apps.env"
    resultado = sandbox.run(
        env_file=env, env_extra={"DIRS_PERMITIDOS": "/opt/stacks /opt"}
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "apps: 4 declaradas, 4 geradas, 0 manuais" in resultado.stdout
    assert "atalhos: 3 no painel (este perfil nao tem portal)" in resultado.stdout
    # O snippet versionado existe ao lado do env e e o unico bloco especial.
    assert (ROOT / "deploy" / "pi" / "snippets" / "jellyfin.caddy").is_file()


def test_env_do_moya_valida(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    env = ROOT / "deploy" / "moya" / "apps.env"
    resultado = sandbox.run(
        env_file=env,
        env_extra={"DIRS_PERMITIDOS": "/opt/stacks /opt /home/conrado"},
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "apps: 12 declaradas, 12 geradas, 0 manuais" in resultado.stdout
    assert "atalhos: 2 no painel, 11 no portal" in resultado.stdout


def test_redir_com_origem_e_codigo(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    env = tmp_path / "redir.env"
    env.write_text(
        "velho|velho.local|localhost:81|-|redir=/antigo->/novo/path@301\n",
        encoding="utf-8",
    )
    resultado = sandbox.run("--apply", env_file=env)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    apps = sandbox.apps_caddy.read_text(encoding="utf-8")
    assert "redir /antigo /novo/path 301" in apps


def test_snippet_embutido_antes_do_proxy(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    snippets = tmp_path / "snippets"
    snippets.mkdir()
    (snippets / "bloqueio.caddy").write_text(
        "@fora {\n\tpath /admin*\n}\nhandle @fora {\n\trespond 403\n}\n",
        encoding="utf-8",
    )
    env = tmp_path / "snippet.env"
    env.write_text(
        "app|app.local|localhost:8081|-|snippet=bloqueio\n", encoding="utf-8"
    )
    resultado = sandbox.run("--apply", env_file=env)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    apps = sandbox.apps_caddy.read_text(encoding="utf-8")
    assert "\t@fora {" in apps
    assert '\t\trespond 403' in apps
    assert apps.index("@fora") < apps.index("reverse_proxy localhost:8081")


def test_snippet_ausente_aborta_sem_escrever(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    env = tmp_path / "sem-snippet.env"
    env.write_text(
        "app|app.local|localhost:8081|-|snippet=nao-existe\n", encoding="utf-8"
    )
    resultado = sandbox.run("--apply", env_file=env)
    assert resultado.returncode == 2
    assert "snippet 'nao-existe' nao encontrado" in resultado.stderr
    assert sandbox.caddyfile.read_text(encoding="utf-8") == CADDYFILE_MOYA


def test_redir_invalido_aborta(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    env = tmp_path / "redir-ruim.env"
    env.write_text(
        "app|app.local|localhost:8081|-|redir=/ok->sem-barra\n", encoding="utf-8"
    )
    resultado = sandbox.run(env_file=env)
    assert resultado.returncode == 2
    assert "precisa de origem e destino comecando com /" in resultado.stderr


def test_manual_com_redir_aborta(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    env = tmp_path / "conflito.env"
    env.write_text(
        "app|app.local|localhost:8081|-|manual,redir=/admin\n", encoding="utf-8"
    )
    resultado = sandbox.run(env_file=env)
    assert resultado.returncode == 2
    assert "'manual' nao combina com outra flag" in resultado.stderr


def test_doctor_limpo_e_aponta_desvio(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    env = tmp_path / "doctor.env"
    env.write_text(
        f"app|app.local|localhost:8080|{sandbox.dir_portainer}|\n",
        encoding="utf-8",
    )
    assert sandbox.run("--apply", env_file=env).returncode == 0
    limpo = sandbox.run("--doctor", env_file=env)
    assert limpo.returncode == 0, limpo.stdout
    assert "apps.caddy igual ao renderizado" in limpo.stdout
    assert "DNS responde" in limpo.stdout
    assert "nada foi alterado" not in limpo.stdout

    sandbox.apps_caddy.write_text("# fora do renderizado\n", encoding="utf-8")
    desvio = sandbox.run("--doctor", env_file=env)
    assert desvio.returncode == 1
    assert "apps.caddy diferente do renderizado (rode --apply)" in desvio.stdout
    assert "nada foi alterado" in desvio.stdout
    # O doctor nao conserta: o arquivo continua como foi deixado.
    assert sandbox.apps_caddy.read_text(encoding="utf-8") == "# fora do renderizado\n"


def test_doctor_avisa_manual_sem_bloco(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    env = tmp_path / "manual.env"
    env.write_text(
        "so-manual|so-manual.local|localhost:8081|-|manual\n", encoding="utf-8"
    )
    resultado = sandbox.run("--doctor", env_file=env)
    assert resultado.returncode == 1
    assert "e manual mas nao tem bloco" in resultado.stdout


def test_descobrir_sugere_stack_fora_do_env(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    sandbox.dir_projetos.write_text(
        f"{sandbox.dir_git}|moya-gitea\n{sandbox.dir_portainer}|portainer\n",
        encoding="utf-8",
    )
    env = tmp_path / "so-git.env"
    env.write_text(
        f"moya-git|moya-git.local|localhost:3000|{sandbox.dir_git}|\n",
        encoding="utf-8",
    )
    resultado = sandbox.run("--descobrir", env_file=env)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    # Moya: upstream no localhost (os compose publicam em 127.0.0.1), card no
    # portal, icone derivado da key e grupo no default.
    esperado = (
        f"portainer|portainer.local|localhost:8080|{sandbox.dir_portainer}|"
        "atalho=portal,nome=Portainer,icone=portainer,grupo=services"
    )
    assert esperado in resultado.stdout
    assert "atalho=painel|portal|painel+portal|nao" in resultado.stdout
    assert "nada foi escrito" in resultado.stdout
    # Nao escreve no env nem no Caddy.
    assert env.read_text(encoding="utf-8") == (
        f"moya-git|moya-git.local|localhost:3000|{sandbox.dir_git}|\n"
    )
    assert sandbox.caddyfile.read_text(encoding="utf-8") == CADDYFILE_MOYA


def test_descobrir_no_pi_sugere_painel_e_upstream_da_lan(tmp_path):
    sandbox = Sandbox(tmp_path)
    novo = sandbox.stacks / "stacks" / "portainer"
    novo.mkdir()
    sandbox.dir_projetos.write_text(f"{novo}|portainer\n", encoding="utf-8")
    sandbox.projetos.write_text(
        sandbox.projetos.read_text(encoding="utf-8") + "portainer\n", encoding="utf-8"
    )
    resultado = sandbox.run("--descobrir")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    esperado = (
        f"portainer|portainer.conradhub.com|192.168.0.150:8080|{novo}|"
        "atalho=painel,nome=Portainer"
    )
    assert esperado in resultado.stdout
    # Sem portal no perfil, nada de grupo/icone na sugestao.
    assert "grupo=" not in resultado.stdout


def test_atalho_painel_gera_services_ini(tmp_path):
    sandbox = Sandbox(tmp_path)
    env = tmp_path / "atalho.env"
    env.write_text(
        "app|app.conradhub.com|192.168.0.150:8097|"
        f"{sandbox.dir_dockge}|atalho=painel,nome=Minha App,"
        "descricao=Teste local,cor=#123456,icone=app\n"
        "sem-atalho|sem-atalho.conradhub.com|192.168.0.150:8098|"
        f"{sandbox.dir_homelab}|\n",
        encoding="utf-8",
    )
    resultado = sandbox.run("--apply", env_file=env)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    ini = sandbox.services_ini.read_text(encoding="utf-8")
    assert ini.startswith("# Gerado por scripts/stacks/apps-sync.sh")
    assert "[app]" in ini
    assert "name = Minha App" in ini
    assert "description = Teste local" in ini
    assert "url = https://app.conradhub.com" in ini
    assert "icon = app" in ini
    assert "color = #123456" in ini
    assert "order = 10" in ini
    assert "[sem-atalho]" not in ini  # sem atalho: rota e DNS, sem card

    # O painel le o arquivo com o parser de sempre (core/services.py).
    from core.services import load_services

    servicos = load_services(sandbox.services_ini)
    assert [(s.key, s.name, s.url) for s in servicos] == [
        ("app", "Minha App", "https://app.conradhub.com")
    ]


def test_atalho_sem_nome_deriva_do_fqdn(tmp_path):
    sandbox = Sandbox(tmp_path)
    env = tmp_path / "atalho.env"
    env.write_text(
        "minha-app|minha-app.conradhub.com|192.168.0.150:8097|"
        f"{sandbox.dir_dockge}|atalho=painel\n",
        encoding="utf-8",
    )
    resultado = sandbox.run("--apply", env_file=env)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    ini = sandbox.services_ini.read_text(encoding="utf-8")
    assert "name = Minha app" in ini
    assert "description" not in ini
    assert "icon = generic" in ini
    assert "color = #38bdf8" in ini


def test_portal_so_no_perfil_moya(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    env = tmp_path / "atalho.env"
    env.write_text(
        f"moya-git|moya-git.local|localhost:3000|{sandbox.dir_git}|"
        "atalho=portal,nome=Gitea,cor=#4a9eff\n"
        "moya-weather|moya-weather.local|10.72.60.202:80|-|atalho=portal\n"
        "moya-versoes|moya-versoes.local|localhost:8070|-|"
        "atalho=painel+portal,nome=SharePoint\n"
        "moya-portal|moya-portal.local|localhost:8020|-|\n",
        encoding="utf-8",
    )
    assert not sandbox.portal_ini.exists()  # nada gerado antes do --apply
    resultado = sandbox.run("--apply", env_file=env)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    ini = sandbox.portal_ini.read_text(encoding="utf-8")
    assert "[moya-git]" in ini
    assert "url = http://moya-git.local" in ini
    assert "[moya-weather]" in ini
    assert "[moya-versoes]" in ini
    # O portal nao aponta para si mesmo.
    assert "[moya-portal]" not in ini

    painel = sandbox.services_ini.read_text(encoding="utf-8")
    assert "[moya-versoes]" in painel
    assert "[moya-git]" not in painel


def test_atalho_painel_no_perfil_pi_nao_cria_portal(tmp_path):
    sandbox = Sandbox(tmp_path)
    env = tmp_path / "atalho.env"
    env.write_text(
        "app|app.conradhub.com|192.168.0.150:8097|"
        f"{sandbox.dir_dockge}|atalho=painel+portal\n",
        encoding="utf-8",
    )
    resultado = sandbox.run("--apply", env_file=env)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "[app]" in sandbox.services_ini.read_text(encoding="utf-8")
    assert not sandbox.portal_ini.exists()


def test_atalho_preserva_arquivo_manual_com_backup(tmp_path):
    sandbox = Sandbox(tmp_path)
    antigo = "[meu]\nname = Antigo\nurl = https://antigo.conradhub.com\n"
    sandbox.services_ini.write_text(antigo, encoding="utf-8")

    env = tmp_path / "atalho.env"
    env.write_text(
        "app|app.conradhub.com|192.168.0.150:8097|"
        f"{sandbox.dir_dockge}|atalho=painel,nome=App\n",
        encoding="utf-8",
    )
    resultado = sandbox.run("--apply", env_file=env)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "nao era gerado" in resultado.stderr

    backups = list(sandbox.services_ini.parent.glob("services.ini.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == antigo
    assert "[app]" in sandbox.services_ini.read_text(encoding="utf-8")


def test_atalho_idempotente(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    assert sandbox.run("--apply").returncode == 0
    resultado = sandbox.run("--apply")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "atalhos (portal) sem mudanca" in resultado.stdout


def test_doctor_acusa_atalhos_editados_a_mao(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    assert sandbox.run("--apply").returncode == 0
    limpo = sandbox.run("--doctor")
    assert "atalhos (portal) iguais ao renderizado" in limpo.stdout

    with sandbox.portal_ini.open("a", encoding="utf-8") as arquivo:
        arquivo.write("\n[manual]\nname = Manual\nurl = http://x.local\n")
    sujo = sandbox.run("--doctor")
    assert sujo.returncode == 1
    assert "atalhos (portal) diferente do renderizado" in sujo.stdout
    # O doctor nao conserta.
    assert "[manual]" in sandbox.portal_ini.read_text(encoding="utf-8")


def test_atalho_invalido_aborta(tmp_path):
    sandbox = Sandbox(tmp_path)
    env = tmp_path / "atalho.env"
    env.write_text(
        "app|app.conradhub.com|192.168.0.150:8097|"
        f"{sandbox.dir_dockge}|atalho=menu\n",
        encoding="utf-8",
    )
    resultado = sandbox.run(env_file=env)
    assert resultado.returncode == 2
    assert "atalho 'menu' invalido" in resultado.stderr


def test_cor_invalida_aborta(tmp_path):
    sandbox = Sandbox(tmp_path)
    env = tmp_path / "atalho.env"
    env.write_text(
        "app|app.conradhub.com|192.168.0.150:8097|"
        f"{sandbox.dir_dockge}|atalho=painel,cor=azul\n",
        encoding="utf-8",
    )
    resultado = sandbox.run(env_file=env)
    assert resultado.returncode == 2
    assert "cor 'azul' invalida" in resultado.stderr


def test_flag_repetida_aborta(tmp_path):
    sandbox = Sandbox(tmp_path)
    env = tmp_path / "atalho.env"
    env.write_text(
        "app|app.conradhub.com|192.168.0.150:8097|"
        f"{sandbox.dir_dockge}|atalho=painel,atalho=portal\n",
        encoding="utf-8",
    )
    resultado = sandbox.run(env_file=env)
    assert resultado.returncode == 2
    assert "flag 'atalho' repetida" in resultado.stderr


def test_env_do_pi_gera_os_atalhos_do_painel(tmp_path):
    sandbox = Sandbox(tmp_path)
    # Host ja migrado: o Jellyfin deixou de ser bloco manual no Caddyfile.
    sandbox.caddyfile.write_text(CADDYFILE.split("jellyfin.conradhub.com {")[0],
                                 encoding="utf-8")
    env = ROOT / "deploy" / "pi" / "apps.env"
    resultado = sandbox.run(
        "--apply", env_file=env, env_extra={"DIRS_PERMITIDOS": "/opt/stacks /opt"}
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    secoes = [
        linha
        for linha in sandbox.services_ini.read_text(encoding="utf-8").splitlines()
        if linha.startswith("[")
    ]
    assert secoes == ["[dockge]", "[pihole]", "[jellyfin]"]
    assert not sandbox.portal_ini.exists()


def test_env_do_moya_gera_painel_e_portal(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    env = ROOT / "deploy" / "moya" / "apps.env"
    resultado = sandbox.run(
        "--apply",
        env_file=env,
        env_extra={"DIRS_PERMITIDOS": "/opt/stacks /opt /home/conrado"},
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    painel = sandbox.services_ini.read_text(encoding="utf-8")
    assert [l for l in painel.splitlines() if l.startswith("[")] == [
        "[moya-versoes]",
        "[moya-credenciais]",
    ]
    portal = sandbox.portal_ini.read_text(encoding="utf-8")
    secoes = [l for l in portal.splitlines() if l.startswith("[")]
    assert len(secoes) == 11
    assert "[moya-portal]" not in secoes
    assert "group = infrastructure" in portal
    assert "group = tools" in portal


def test_descobrir_prefere_porta_web_entre_varias(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    sandbox.dir_projetos.write_text(f"{sandbox.dir_portainer}|portainer\n", encoding="utf-8")
    resultado = sandbox.run("--descobrir", env_extra={"STUB_PORTAS": "53,8888,22"})
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    # 53 (DNS) e 22 (SSH) nao sao a web da app.
    assert (
        f"portainer|portainer.local|localhost:8888|{sandbox.dir_portainer}|" in resultado.stdout
    )
    assert "55" not in resultado.stdout  # nada de somar portas
    assert "sugeri 8888" in resultado.stdout


def test_descobrir_nao_duplica_app_ja_exposta(tmp_path):
    sandbox = SandboxMoya(tmp_path)
    # A pasta `pihole` ja esta no ar como `moya-pihole` (dir `-`, sem stack).
    pasta = sandbox.fake_home / "pihole"
    pasta.mkdir(exist_ok=True)
    sandbox.dir_projetos.write_text(f"{pasta}|pihole\n", encoding="utf-8")
    resultado = sandbox.run("--descobrir")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert f"pihole: ja exposta como moya-pihole; troque o `-` por {pasta}" in resultado.stdout
    # Nao sugere criar `pihole|pihole.local|...` por cima da app existente.
    assert "pihole|pihole.local" not in resultado.stdout

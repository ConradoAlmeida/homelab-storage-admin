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
    for a in "$@"; do
      case "$a" in
        label=com.docker.compose.project=*)
          projeto=${a#label=com.docker.compose.project=}
          if grep -qx "$projeto" "$STUB_PROJETOS" 2>/dev/null; then
            echo "container-$projeto"
          fi
          ;;
      esac
    done
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
      echo true
      exit 0
    fi
    if [[ "$*" == *"misc.etc_dnsmasq_d"* ]]; then
      cat "$STUB_DNSMASQ_D" 2>/dev/null || echo true
      exit 0
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
        self.dnsmasq_flag = tmp_path / "dnsmasq_d"
        self.bin = tmp_path / "bin"
        self.dir_homelab = self.stacks / "stacks" / "homelab-storage-admin"
        self.dir_dockge = self.stacks / "dockge"
        self.dir_jellyfin = self.stacks / "stacks" / "jellyfin"
        self.dir_pihole = self.stacks / "stacks" / "pihole"

        for caminho in (
            self.caddy_dir,
            self.stacks / "stacks" / "pihole" / "etc-dnsmasq.d",
            self.dir_homelab,
            self.dir_dockge,
            self.dir_jellyfin,
            (tmp_path / "var"),
            self.bin,
        ):
            caminho.mkdir(parents=True, exist_ok=True)

        self.caddyfile.write_text(CADDYFILE, encoding="utf-8")
        self.env_file.write_text(self.env_text(), encoding="utf-8")
        self.projetos.write_text("homelab-storage-admin\ndockge\njellyfin\n", encoding="utf-8")
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
            "STUB_LOG": str(self.log),
            "STUB_PROJETOS": str(self.projetos),
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

#!/usr/bin/env bash
# Atualiza o Homelab Storage Admin no rpi5 a partir do GitHub.
# Uso (no Pi): ./deploy.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if [[ ! -d .git ]]; then
  echo "ERRO: este diretorio nao e um clone git." >&2
  exit 1
fi

echo "==> git pull --ff-only origin main"
git pull --ff-only origin main

HOST_ENV=/etc/homelab-storage-admin/host.env
if [[ ! -f "$HOST_ENV" ]]; then
  echo "ERRO: $HOST_ENV nao existe. Rode antes: sudo ./install-agent.sh" >&2
  exit 1
fi
# shellcheck disable=SC1090
set -a
. "$HOST_ENV"
set +a

COMPOSE_FILES=(-f docker-compose.yml)
if [[ -n "${COMPOSE_OVERLAY:-}" ]]; then
  if [[ ! -f "$COMPOSE_OVERLAY" ]]; then
    echo "ERRO: COMPOSE_OVERLAY nao encontrado: $COMPOSE_OVERLAY" >&2
    exit 1
  fi
  COMPOSE_FILES+=(-f "$COMPOSE_OVERLAY")
fi

chmod +x install-agent.sh entrypoint.sh deploy.sh

NEED_AGENT=0
if [[ ! -f /usr/local/sbin/homelab-storage-agent ]] || ! cmp -s agent/homelab-storage-agent.py /usr/local/sbin/homelab-storage-agent; then
  NEED_AGENT=1
fi
if [[ ! -f /usr/local/sbin/homelab-storage-snapshot ]] || ! cmp -s agent/homelab-storage-snapshot.py /usr/local/sbin/homelab-storage-snapshot; then
  NEED_AGENT=1
fi
if [[ ! -f /etc/systemd/system/homelab-storage-agent.service ]] || ! cmp -s agent/homelab-storage-agent.service /etc/systemd/system/homelab-storage-agent.service; then
  NEED_AGENT=1
fi
# O timer de snapshots e dinamico: o agente reescreve OnCalendar conforme a
# agenda salva (1 a 24 copias por dia), entao nao serve para comparar aqui.
if [[ ! -f /etc/systemd/system/homelab-storage-snapshot.service ]] || ! cmp -s agent/homelab-storage-snapshot.service /etc/systemd/system/homelab-storage-snapshot.service; then
  NEED_AGENT=1
fi

if [[ "${COMPOSE_OVERLAY:-}" == *homelab* ]]; then
  qbit_conf="/mnt/nas/apps/qbittorrent/config/qBittorrent/qBittorrent.conf"
  if [[ ! -f "$qbit_conf" ]]; then
    mkdir -p "$(dirname "$qbit_conf")" "${JELLYFIN_ROOT:-/mnt/jellyfin}/.incomplete"
    cp "$HERE/deploy/pi/qbittorrent.conf" "$qbit_conf"
    echo "==> Configuracao inicial do qBittorrent"
  fi
fi

echo "==> docker compose up -d --build"
docker compose "${COMPOSE_FILES[@]}" up -d --build

if [[ "${COMPOSE_OVERLAY:-}" == *homelab* ]]; then
  echo "==> firewall do qBittorrent e UPnP"
  docker exec -i homelab-storage-admin python - << 'PY'
import json
import socket
import time

SOCKET = "/run/homelab-storage-admin/agent.sock"
REGRAS = (
    ("6881", "tcp", "", "6881/tcp", "Anywhere"),
    ("6881", "udp", "", "6881/udp", "Anywhere"),
    ("8090", "tcp", "172.16.0.0/12", "8090/tcp", "172.16.0.0/12"),
)


def agente(payload: dict) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(30)
        sock.connect(SOCKET)
        sock.sendall(json.dumps(payload).encode() + b"\n")
        partes = []
        while True:
            bloco = sock.recv(65536)
            if not bloco:
                break
            partes.append(bloco)
            if bloco.endswith(b"\n"):
                break
    resposta = json.loads(b"".join(partes).decode())
    if not resposta.get("ok"):
        raise SystemExit(resposta.get("error") or "agente recusou a operacao")
    return resposta.get("data") or {}


visao = agente({"op": "firewall_overview"})
if visao.get("installed") and visao.get("active"):
    for porta, proto, origem, destino, fonte in REGRAS:
        existe = any(
            regra.get("action") == "allow"
            and regra.get("to") == destino
            and regra.get("from") == fonte
            for regra in visao.get("rules") or []
        )
        if existe:
            continue
        visao = agente(
            {
                "op": "firewall_add_rule",
                "action": "allow",
                "port": porta,
                "proto": proto,
                "source": origem,
            }
        )
        print(f"allow {destino} from {fonte}")
else:
    print("ufw inativo; portas do qBittorrent nao foram alteradas")

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from core import qbittorrent as qbit

ultimo = ""
for _ in range(40):
    try:
        if qbit.QBIT_PASSWORD:
            qbit._login()
        codigo, _corpo = qbit._abrir(
            "POST",
            "/api/v2/app/setPreferences",
            {"json": json.dumps({"upnp": True, "listen_port": 6881})},
        )
        if codigo == 200:
            print("upnp ligado")
            break
        ultimo = f"http {codigo}"
    except Exception as exc:
        ultimo = str(exc)
    time.sleep(1)
else:
    raise SystemExit(f"qBittorrent nao aceitou o UPnP: {ultimo}")
PY
fi

echo "==> status"
docker compose "${COMPOSE_FILES[@]}" ps

if [[ "$NEED_AGENT" -eq 1 ]]; then
  echo
  echo "ATENCAO: o agente no host esta ausente ou diferente do repositorio."
  echo "Rode: sudo ./install-agent.sh"
fi

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

if [[ ! -f .env ]]; then
  echo "ERRO: .env ausente. Copie de .env.example e ajuste o SECRET_KEY e o ALLOWED_HOSTS antes do deploy." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERRO: Docker indisponivel para este usuario (daemon parado ou fora do grupo docker)." >&2
  echo "Ajuste com: sudo systemctl enable --now docker && sudo usermod -aG docker \"$USER\" e abra uma sessao nova." >&2
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
# Compara tudo o que o install-agent.sh instala: os quatro binarios e as units.
# O timer de snapshots fica de fora porque e dinamico (o agente reescreve o
# OnCalendar conforme a agenda salva, de 1 a 24 copias por dia).
for origem in agent/homelab-storage-agent.py agent/homelab-storage-snapshot.py \
  agent/homelab-restic-backup.py agent/homelab-cold-copy.py; do
  destino="/usr/local/sbin/$(basename "${origem%.py}")"
  if [[ ! -f "$destino" ]] || ! cmp -s "$origem" "$destino"; then
    NEED_AGENT=1
  fi
done
for origem in agent/*.service agent/*.timer; do
  nome="$(basename "$origem")"
  if [[ "$nome" == "homelab-storage-snapshot.timer" ]]; then
    continue
  fi
  destino="/etc/systemd/system/$nome"
  if [[ ! -f "$destino" ]] || ! cmp -s "$origem" "$destino"; then
    NEED_AGENT=1
  fi
done

if [[ "$NEED_AGENT" -eq 1 ]]; then
  echo
  echo "ATENCAO: o agente no host esta ausente ou diferente do repositorio."
  echo "Rode: sudo ./install-agent.sh"
  echo
fi

# O apps.env vale no host depois do --apply: um pull que muda o arquivo nao
# mexe em rota, DNS nem atalho. A data e o sinal (o --apply grava o estado
# depois; git nao reescreve arquivo que nao mudou).
APPS_ENV_LOCAL="${APPS_ENV_PATH:-}"
APPS_ESTADO="${APPS_STATE:-/var/lib/homelab-storage-admin/apps.aplicados}"
if [[ -n "$APPS_ENV_LOCAL" && -f "$APPS_ENV_LOCAL" ]] &&
  { [[ ! -f "$APPS_ESTADO" ]] || [[ "$APPS_ENV_LOCAL" -nt "$APPS_ESTADO" ]]; }; then
  # O apps-sync assume o perfil `pi`; so o moya precisa do flag.
  APPS_PERFIL=""
  case "$(basename "$(dirname "$APPS_ENV_LOCAL")")" in
    moya) APPS_PERFIL=" --perfil moya" ;;
  esac
  echo
  echo "ATENCAO: $APPS_ENV_LOCAL mudou depois do ultimo --apply."
  echo "Rotas, DNS e atalhos continuam os antigos. Rode:"
  echo "  sudo bash scripts/stacks/apps-sync.sh$APPS_PERFIL --apply"
  echo
fi

if [[ "${COMPOSE_OVERLAY:-}" == *homelab* ]]; then
  qbit_conf="/mnt/nas/apps/qbittorrent/config/qBittorrent/qBittorrent.conf"
  if [[ ! -f "$qbit_conf" ]]; then
    # Aviso, nao falha: o diretorio pode ser de root e o deploy roda como
    # usuario comum. Sem o arquivo o qBittorrent sobe com a config padrao.
    if mkdir -p "$(dirname "$qbit_conf")" "${JELLYFIN_ROOT:-/mnt/jellyfin}/.incomplete" 2>/dev/null \
      && cp "$HERE/deploy/pi/qbittorrent.conf" "$qbit_conf" 2>/dev/null; then
      echo "==> Configuracao inicial do qBittorrent"
    else
      echo "AVISO: nao foi possivel criar $qbit_conf; rode uma vez com sudo para copiar a configuracao do qBittorrent." >&2
    fi
  fi
fi

echo "==> docker compose up -d --build"
docker compose "${COMPOSE_FILES[@]}" up -d --build

if [[ "${COMPOSE_OVERLAY:-}" == *homelab* ]]; then
  echo "==> firewall do qBittorrent e UPnP"
  # Aviso, nao falha: o app ja esta no ar e o UPnP pode ser reaplicado depois.
  if ! docker exec -i homelab-storage-admin python - << 'PY'
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
  then
    echo "AVISO: o qBittorrent nao confirmou o UPnP; confira a pagina Torrents." >&2
  fi
fi

echo "==> status"
docker compose "${COMPOSE_FILES[@]}" ps

# Deploy verde = app respondendo. O entrypoint roda migracoes antes de subir o
# servidor, entao os primeiros segundos valem 000/502; espera ate 90 s.
APP_URL="http://${BIND_ADDR:-127.0.0.1}:${BIND_PORT:-8060}/login/"
APP_CODE=""
for _ in $(seq 1 45); do
  APP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "$APP_URL" 2>/dev/null || true)
  [[ "$APP_CODE" == "200" || "$APP_CODE" == "302" ]] && break
  sleep 2
done
if [[ "$APP_CODE" != "200" && "$APP_CODE" != "302" ]]; then
  echo "ERRO: $APP_URL respondeu '${APP_CODE:-sem resposta}'." >&2
  echo "Veja os logs:" >&2
  echo "  docker compose ${COMPOSE_FILES[*]} logs --tail=80 web" >&2
  exit 1
fi
echo "OK: $APP_URL -> $APP_CODE"

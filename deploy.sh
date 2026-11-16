#!/usr/bin/env bash
# Atualiza o Homelab Storage Admin no host a partir do GitHub.
# Uso (no host): ./deploy.sh
# Termina conferindo /login/ e rodando o apps-sync --doctor. Se o proprio
# deploy.sh mudar no pull, reexecuta uma vez para nao rodar o tail antigo.
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
# Segredo com modo largo ou chave de exemplo vaza/invalida a sessao: barra
# antes do build, nao depois do app no ar.
ENV_MODO="$(stat -c '%a' .env)"
if [[ "$ENV_MODO" != "600" ]]; then
  echo "ERRO: .env com modo $ENV_MODO (tem segredo). Ajuste: chmod 600 .env" >&2
  exit 1
fi
if ! grep -qE '^DJANGO_SECRET_KEY=.+' .env ||
  grep -qE '^DJANGO_SECRET_KEY=(troque-por-uma-chave-aleatoria-longa|changeme|secret)$' .env; then
  echo "ERRO: DJANGO_SECRET_KEY ausente ou de exemplo no .env." >&2
  echo "Gere uma: openssl rand -hex 32" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "ERRO: Docker indisponivel para este usuario (daemon parado ou fora do grupo docker)." >&2
  echo "Ajuste com: sudo systemctl enable --now docker && sudo usermod -aG docker \"$USER\" e abra uma sessao nova." >&2
  exit 1
fi

echo "==> git pull --ff-only origin main"
# Bash le o script por offset: se o pull troca o deploy.sh no meio, o resto da
# execucao pode sair do lugar. Reexecuta uma vez com a versao recem-baixada.
DEPLOY_ANTES="$(cksum <"$0")"
git pull --ff-only origin main
if [[ "$(cksum <"$0")" != "$DEPLOY_ANTES" && "${DEPLOY_REEXECUTADO:-}" != "1" ]]; then
  echo "==> deploy.sh mudou no pull; reiniciando com a versao nova"
  DEPLOY_REEXECUTADO=1 exec "$0" "$@"
fi

HOST_ENV=/etc/homelab-storage-admin/host.env
if [[ ! -f "$HOST_ENV" ]]; then
  echo "ERRO: $HOST_ENV nao existe. Rode antes: sudo ./install-agent.sh" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
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
# O apps-sync le o HOST_PROFILE do host.env: nenhum flag por host aqui.
if [[ -n "$APPS_ENV_LOCAL" && -f "$APPS_ENV_LOCAL" ]] &&
  { [[ ! -f "$APPS_ESTADO" ]] || [[ "$APPS_ENV_LOCAL" -nt "$APPS_ESTADO" ]]; }; then
  echo
  echo "ATENCAO: $APPS_ENV_LOCAL mudou depois do ultimo --apply."
  echo "Rotas, DNS e atalhos continuam os antigos. Rode:"
  echo "  sudo bash scripts/stacks/apps-sync.sh --apply"
  echo
fi

# A feature do host.toml decide, nao o nome do overlay: host com qBittorrent
# recebe a config inicial e o firewall; host sem ele nao passa por aqui.
if [[ "${QBITTORRENT_ENABLE:-0}" == "1" && -n "${STORAGE_ROOT:-}" ]]; then
  qbit_conf="$STORAGE_ROOT/apps/qbittorrent/config/qBittorrent/qBittorrent.conf"
  incompleto="${JELLYFIN_ROOT:+$JELLYFIN_ROOT/.incomplete}"
  if [[ ! -f "$qbit_conf" ]]; then
    # Aviso, nao falha: o diretorio pode ser de root e o deploy roda como
    # usuario comum. Sem o arquivo o qBittorrent sobe com a config padrao.
    if mkdir -p "$(dirname "$qbit_conf")" ${incompleto:+"$incompleto"} 2>/dev/null \
      && cp "$HERE/deploy/${HOST_PROFILE:-}/qbittorrent.conf" "$qbit_conf" 2>/dev/null; then
      echo "==> Configuracao inicial do qBittorrent"
    else
      echo "AVISO: nao foi possivel criar $qbit_conf; rode uma vez com sudo para copiar a configuracao do qBittorrent." >&2
    fi
  fi
fi

echo "==> docker compose up -d --build"
docker compose "${COMPOSE_FILES[@]}" up -d --build

if [[ "${QBITTORRENT_ENABLE:-0}" == "1" ]]; then
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

# O --doctor so le e roda sem sudo (root so melhora a validacao do TLS); o
# resumo entra no deploy para ninguem descobrir desvio de rota/DNS so depois.
if [[ -f scripts/stacks/apps-sync.sh && -n "$APPS_ENV_LOCAL" && -f "$APPS_ENV_LOCAL" ]]; then
  echo "==> rotas, DNS e atalhos (--doctor)"
  set +e
  DOUTOR_SAIDA="$(bash scripts/stacks/apps-sync.sh --doctor 2>&1)"
  DOUTOR_RC=$?
  set -e
  # So os erros: no Pi o aviso do token da Cloudflare apareceria em todo deploy.
  printf '%s\n' "$DOUTOR_SAIDA" | grep -E '^ +erro:' || true
  printf '%s\n' "$DOUTOR_SAIDA" | sed -n '/==> resumo/,$p' | grep -v '^==> resumo' || true
  if [[ $DOUTOR_RC -ne 0 ]]; then
    # Erro de rota/DNS/atalho e deploy falho: o app esta no ar, mas o host nao
    # esta no estado que o env declara. Aviso (ex.: token sem sudo) nao conta.
    echo "ERRO: rota, DNS ou atalho divergente do env (o app esta no ar)." >&2
    echo "Detalhe: bash scripts/stacks/apps-sync.sh --doctor" >&2
    exit 1
  fi
fi

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
if [[ ! -f /etc/systemd/system/homelab-storage-snapshot.timer ]] || ! cmp -s agent/homelab-storage-snapshot.timer /etc/systemd/system/homelab-storage-snapshot.timer; then
  NEED_AGENT=1
fi
if [[ ! -f /etc/systemd/system/homelab-storage-snapshot.service ]] || ! cmp -s agent/homelab-storage-snapshot.service /etc/systemd/system/homelab-storage-snapshot.service; then
  NEED_AGENT=1
fi

echo "==> docker compose up -d --build"
docker compose up -d --build

echo "==> status"
docker compose ps

if [[ "$NEED_AGENT" -eq 1 ]]; then
  echo
  echo "ATENCAO: o agente no host esta ausente ou diferente do repositorio."
  echo "Rode: sudo ./install-agent.sh"
fi

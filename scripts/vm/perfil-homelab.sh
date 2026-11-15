#!/usr/bin/env bash
# Aplica o perfil homelab (Pi) na bancada de VM.
#
# Uso (root, dentro da VM, no clone do repo):
#   sudo bash scripts/vm/perfil-homelab.sh
#
# Cria os paths que o Pi tem montados (/mnt/nas, /mnt/jellyfin, /mnt/backup),
# gera /etc/homelab-storage-admin/host.env a partir do host.env.example com os
# ajustes da VM, instala o agente e sincroniza as dependencias. Idempotente:
# rodar de novo regenera o perfil do zero.
#
# O overlay real (docker-compose.homelab.yml) fica de fora: ele espera o
# qBittorrent e o Jellyfin do Pi. A VM usa um overlay gerado, com o mesmo nome
# de pagina, para exercitar os caminhos do deploy.sh.
set -euo pipefail

MARKER=/etc/homelab-vm-bench
MANIFEST_DIR=/var/lib/homelab-vm-bench
MANIFEST="$MANIFEST_DIR/criado"
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
DONO=${SUDO_USER:-conrado}

if [[ $EUID -ne 0 ]]; then
  echo "ERRO: execute com sudo." >&2
  exit 1
fi
if [[ ! -f "$MARKER" ]]; then
  echo "ERRO: $MARKER nao existe; esta maquina nao e bancada." >&2
  exit 1
fi
if [[ ! -f "$REPO/host.env.example" ]]; then
  echo "ERRO: rode dentro do clone do homelab-storage-admin ($REPO)." >&2
  exit 1
fi

mkdir -p "$MANIFEST_DIR"
chmod 0700 "$MANIFEST_DIR"

registra() {
  local caminho=$1
  [[ -d "$caminho" || -f "$caminho" ]] || return 0
  grep -qxF "$caminho" "$MANIFEST" 2>/dev/null || echo "$caminho" >>"$MANIFEST"
}

echo "==> paths do homelab"
for caminho in /mnt/nas /mnt/jellyfin /mnt/backup; do
  if mountpoint -q "$caminho" 2>/dev/null; then
    echo "    ja montado, preservado: $caminho"
    continue
  fi
  if [[ -d "$caminho" ]]; then
    # Veio da base: nao entra no manifesto, senao o clean.sh apaga.
    echo "    ja existe, preservado: $caminho"
  else
    mkdir -p "$caminho"
    registra "$caminho"
    echo "    diretorio: $caminho"
  fi
done
mkdir -p /mnt/nas/apps /mnt/jellyfin/.incomplete
chown -R "$DONO:$DONO" /mnt/nas /mnt/jellyfin /mnt/backup

echo "==> host.env (perfil Pi)"
install -d -m 0755 /etc/homelab-storage-admin
install -m 0644 "$REPO/host.env.example" /etc/homelab-storage-admin/host.env
cat >>/etc/homelab-storage-admin/host.env <<EOF

# ---- ajustes da bancada de VM (gerados por perfil-homelab.sh) ----
# A VM nao tem os IPs do Pi: ela escuta em todas as interfaces e guarda os
# dados dentro do clone (o data/ e descartado pelo revert do snapshot).
BIND_ADDR=0.0.0.0
DATA_DIR=$REPO/data
DOWNLOAD_DIR=$REPO/data/downloads
COMPOSE_OVERLAY=/etc/homelab-storage-admin/overlay-homelab-vm.yml
JELLYFIN_ROOT=/mnt/jellyfin
BACKUP_ROOT=/mnt/backup
EOF

echo "==> overlay da VM"
cat >/etc/homelab-storage-admin/overlay-homelab-vm.yml <<'YML'
# Gerado por scripts/vm/perfil-homelab.sh. Nao versionar.
services:
  web:
    environment:
      QBITTORRENT_URL: http://qbittorrent:8090
    volumes:
      - /mnt/jellyfin:/mnt/jellyfin:ro
YML

echo "==> .env do clone"
if [[ ! -f "$REPO/.env" ]]; then
  install -m 0600 "$REPO/.env.example" "$REPO/.env"
  # A VM pega IP por DHCP: aceitar qualquer Host evita 400 quando o lease
  # muda, sem tocar no .env do Pi.
  sed -i "s|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=*|" "$REPO/.env"
  sed -i "s|^DJANGO_CSRF_TRUSTED_ORIGINS=.*|DJANGO_CSRF_TRUSTED_ORIGINS=http://$(hostname -I | awk '{print $1}'):8060,http://127.0.0.1:8060,http://localhost:8060|" "$REPO/.env"
  chown "$DONO:$DONO" "$REPO/.env"
  echo "    criado a partir do .env.example"
else
  echo "    mantido"
fi

echo "==> acesso ao docker"
if command -v docker >/dev/null 2>&1; then
  if id -nG "$DONO" | tr ' ' '\n' | grep -qx docker; then
    echo "    $DONO ja esta no grupo docker"
  else
    usermod -aG docker "$DONO"
    echo "    $DONO adicionado ao grupo docker (vale no proximo login)"
  fi
else
  echo "    AVISO: docker ausente; rode setup-ubuntu-2604.sh com INSTALL_DOCKER=1" >&2
fi

echo "==> agente e units"
(cd "$REPO" && HOST_ENV_PROFILE=pi ./install-agent.sh >/dev/null)
echo "    homelab-storage-agent: $(systemctl is-active homelab-storage-agent)"

echo "==> dependencias"
(cd "$REPO" && runuser -u "$DONO" -- uv sync --dev --frozen >/dev/null)
echo "    uv sync ok"

echo
echo "==> perfil homelab pronto em $REPO"
echo "    app:  sudo docker compose -f docker-compose.yml -f /etc/homelab-storage-admin/overlay-homelab-vm.yml up -d --build"
echo "    ou:   ./deploy.sh  (le COMPOSE_OVERLAY do host.env)"

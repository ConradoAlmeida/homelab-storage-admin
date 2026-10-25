#!/usr/bin/env bash
# Instala o agente privilegiado do Homelab Storage Admin (rodar com sudo).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERRO: execute com sudo: sudo ./install-agent.sh" >&2
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Checando dependencias"
for cmd in btrfs pdbedit smbpasswd smbcontrol testparm; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERRO: '$cmd' nao encontrado. Instale: sudo apt install samba samba-common-bin btrfs-progs" >&2
    exit 1
  fi
done

if ! mountpoint -q /mnt/nas; then
  echo "AVISO: /mnt/nas nao esta montado. Monte o Btrfs antes de usar shares/snapshots." >&2
fi

echo "==> Instalando binarios"
install -m 0755 "$HERE/agent/homelab-storage-agent.py" /usr/local/sbin/homelab-storage-agent
install -m 0755 "$HERE/agent/homelab-storage-snapshot.py" /usr/local/sbin/homelab-storage-snapshot

echo "==> Instalando unidades systemd"
install -m 0644 "$HERE/agent/homelab-storage-agent.service" /etc/systemd/system/homelab-storage-agent.service
install -m 0644 "$HERE/agent/homelab-storage-snapshot.service" /etc/systemd/system/homelab-storage-snapshot.service
install -m 0644 "$HERE/agent/homelab-storage-snapshot.timer" /etc/systemd/system/homelab-storage-snapshot.timer

echo "==> Configuracao"
mkdir -p /etc/homelab-storage-agent
chmod 0755 /etc/homelab-storage-agent

systemctl daemon-reload
systemctl enable homelab-storage-agent
systemctl restart homelab-storage-agent
systemctl enable --now homelab-storage-snapshot.timer
sleep 1

echo "==> Status"
systemctl --no-pager --lines=5 status homelab-storage-agent || true
systemctl --no-pager --lines=3 status homelab-storage-snapshot.timer || true
ls -l /run/homelab-storage-admin/agent.sock

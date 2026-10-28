#!/usr/bin/env bash
# Instala o agente privilegiado do Homelab Storage Admin (rodar com sudo).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERRO: execute com sudo: sudo ./install-agent.sh" >&2
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOST_ENV=/etc/homelab-storage-admin/host.env
HOST_ENV_PROFILE="${HOST_ENV_PROFILE:-pi}"
case "$HOST_ENV_PROFILE" in
  pi) HOST_ENV_EXAMPLE="$HERE/host.env.example" ;;
  moya) HOST_ENV_EXAMPLE="$HERE/host.env.moya.example" ;;
  *)
    echo "ERRO: HOST_ENV_PROFILE invalido: $HOST_ENV_PROFILE (use pi ou moya)" >&2
    exit 1
    ;;
esac
mkdir -p /etc/homelab-storage-admin
if [[ ! -f "$HOST_ENV" ]]; then
  install -m 0644 "$HOST_ENV_EXAMPLE" "$HOST_ENV"
  echo "==> Criado $HOST_ENV a partir do perfil '$HOST_ENV_PROFILE'."
else
  echo "==> Mantendo $HOST_ENV existente (perfil '$HOST_ENV_PROFILE' nao sobrescrito)."
fi

# Samba e ferramentas de disco sao obrigatorios; o resto e detectado pelo app.
echo "==> Checando dependencias obrigatorias"
for cmd in pdbedit smbpasswd smbcontrol testparm parted mkfs.ext4; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERRO: '$cmd' nao encontrado. Instale: sudo apt install samba samba-common-bin parted e2fsprogs" >&2
    exit 1
  fi
done

echo "==> Dependencias opcionais"
for cmd in btrfs restic smartctl hdparm mdadm; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "AVISO: '$cmd' ausente; o recurso correspondente sera escondido no app." >&2
  fi
done

# shellcheck disable=SC1090
if [[ -f "$HOST_ENV" ]]; then
  set -a
  . "$HOST_ENV"
  set +a
fi
STORAGE_ROOT="${STORAGE_ROOT:-/mnt/nas}"
if ! mountpoint -q "$STORAGE_ROOT"; then
  echo "AVISO: $STORAGE_ROOT nao esta montado. Shares/snapshots Btrfs ficam limitados." >&2
fi

echo "==> Instalando binarios"
install -m 0755 "$HERE/agent/homelab-storage-agent.py" /usr/local/sbin/homelab-storage-agent
install -m 0755 "$HERE/agent/homelab-storage-snapshot.py" /usr/local/sbin/homelab-storage-snapshot
install -m 0755 "$HERE/agent/homelab-restic-backup.py" /usr/local/sbin/homelab-restic-backup
install -m 0755 "$HERE/agent/homelab-cold-copy.py" /usr/local/sbin/homelab-cold-copy

echo "==> Instalando unidades systemd"
install -m 0644 "$HERE/agent/homelab-storage-agent.service" /etc/systemd/system/homelab-storage-agent.service
install -m 0644 "$HERE/agent/homelab-storage-snapshot.service" /etc/systemd/system/homelab-storage-snapshot.service
install -m 0644 "$HERE/agent/homelab-storage-snapshot.timer" /etc/systemd/system/homelab-storage-snapshot.timer
install -m 0644 "$HERE/agent/homelab-storage-metrics.service" /etc/systemd/system/homelab-storage-metrics.service
install -m 0644 "$HERE/agent/homelab-storage-metrics.timer" /etc/systemd/system/homelab-storage-metrics.timer
install -m 0644 "$HERE/agent/homelab-restic-backup@.service" /etc/systemd/system/homelab-restic-backup@.service
install -m 0644 "$HERE/agent/homelab-cold-copy.service" /etc/systemd/system/homelab-cold-copy.service
install -m 0644 "$HERE/agent/homelab-restic-check.service" /etc/systemd/system/homelab-restic-check.service
install -m 0644 "$HERE/agent/homelab-restic-check.timer" /etc/systemd/system/homelab-restic-check.timer
install -m 0644 "$HERE/agent/homelab-arquivos-backup@.service" /etc/systemd/system/homelab-arquivos-backup@.service

echo "==> Configuracao"
mkdir -p /etc/homelab-storage-agent /etc/homelab-backup/status /etc/homelab-backup/secrets /etc/homelab-backup/health /var/log/homelab-restic
mkdir -p "${CREDENCIAIS_BACKUP_DIR:-/var/backups/moya-credenciais}"
chmod 0755 /etc/homelab-storage-agent
chmod 0700 /etc/homelab-backup /etc/homelab-backup/status /etc/homelab-backup/secrets
chmod 0750 /var/log/homelab-restic
chmod 0700 "${CREDENCIAIS_BACKUP_DIR:-/var/backups/moya-credenciais}"

systemctl daemon-reload
systemctl enable homelab-storage-agent
systemctl restart homelab-storage-agent
systemctl enable --now homelab-storage-snapshot.timer
systemctl enable --now homelab-storage-metrics.timer
systemctl enable --now homelab-restic-check.timer
if [[ -f "${CREDENCIAIS_DB:-/home/conrado/moya_credenciais_app/data/db.sqlite3}" ]]; then
  systemctl disable --now homelab-credenciais-backup.timer 2>/dev/null || true
  /usr/local/sbin/homelab-storage-agent --apply-timer || true
fi
sleep 1

echo "==> Status"
systemctl --no-pager --lines=5 status homelab-storage-agent || true
systemctl --no-pager --lines=3 status homelab-storage-snapshot.timer || true
ls -l /run/homelab-storage-admin/agent.sock

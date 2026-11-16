#!/usr/bin/env bash
# Instala o agente privilegiado do Homelab Storage Admin (rodar com sudo).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "ERRO: execute com sudo: sudo ./install-agent.sh" >&2
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CONFIG_DIR=/etc/homelab-storage-admin
HOST_ENV="$CONFIG_DIR/host.env"
mkdir -p "$CONFIG_DIR"

# O perfil vem de HOST_ENV_PROFILE ou do host.env ja instalado (HOST_PROFILE).
# Sem os dois nao ha host: o script nao tem preset embutido.
HOST_ENV_PROFILE="${HOST_ENV_PROFILE:-}"
if [[ -z "$HOST_ENV_PROFILE" && -f "$HOST_ENV" ]]; then
  HOST_ENV_PROFILE=$(sed -n 's/^HOST_PROFILE=//p' "$HOST_ENV" | tail -n1 | tr -d "\"'")
fi
if [[ -z "$HOST_ENV_PROFILE" ]]; then
  echo "ERRO: defina HOST_ENV_PROFILE com o slug de hosts/<slug>/host.toml." >&2
  echo "      Ex.: sudo HOST_ENV_PROFILE=<slug> ./install-agent.sh" >&2
  echo "      (ou rode: python3 scripts/homelabctl.py render <slug> --write --ambos)" >&2
  exit 1
fi
if [[ ! "$HOST_ENV_PROFILE" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "ERRO: HOST_ENV_PROFILE invalido: $HOST_ENV_PROFILE (use o slug de hosts/)" >&2
  exit 1
fi

# O TOML versionado e a unica fonte da configuracao: sem ele (ou sem python3)
# nao ha o que instalar.
TOML="$HERE/hosts/$HOST_ENV_PROFILE/host.toml"
if [[ ! -f "$TOML" ]] || ! command -v python3 >/dev/null 2>&1; then
  echo "ERRO: falta $TOML (ou python3) para o perfil '$HOST_ENV_PROFILE'." >&2
  echo "      Crie o host: python3 scripts/homelabctl.py init (veja docs/PRESETS.md)" >&2
  exit 1
fi

# Renderiza a partir do TOML versionado, sem sobrescrever o que ja existe:
# mudar a configuracao e `homelabctl render <slug> --write --ambos`.
for arquivo in host.env sync.env; do
  if [[ -f "$CONFIG_DIR/$arquivo" ]]; then
    echo "==> Mantendo $CONFIG_DIR/$arquivo existente."
    continue
  fi
  flag=()
  [[ "$arquivo" == "sync.env" ]] && flag=(--sync)
  python3 "$HERE/scripts/homelabctl.py" render "$HOST_ENV_PROFILE" "${flag[@]}" \
    --write --destino "$CONFIG_DIR"
done

# Dependencia segue a feature ligada: host sem Samba nao precisa de smbd, e o
# que falta vira aviso em vez de erro quando a feature e opcional.
echo "==> Checando dependencias do perfil '$HOST_ENV_PROFILE'"
while IFS='|' read -r tipo cmd pacotes; do
  [[ -n "$cmd" ]] || continue
  command -v "$cmd" >/dev/null 2>&1 && continue
  if [[ "$tipo" == "obrig" ]]; then
    echo "ERRO: '$cmd' nao encontrado (feature ligada em hosts/$HOST_ENV_PROFILE/host.toml)." >&2
    echo "      Instale: sudo apt install $pacotes" >&2
    exit 1
  fi
  echo "AVISO: '$cmd' ausente; o recurso correspondente sera escondido no app." >&2
done < <(python3 "$HERE/scripts/homelabctl.py" requisitos "$HOST_ENV_PROFILE")

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
install -m 0644 "$HERE/agent/homelab-gitea-backup@.service" /etc/systemd/system/homelab-gitea-backup@.service
install -m 0644 "$HERE/agent/homelab-arquivos-backup@.service" /etc/systemd/system/homelab-arquivos-backup@.service
install -m 0644 "$HERE/agent/homelab-task@.service" /etc/systemd/system/homelab-task@.service

echo "==> Configuracao"
mkdir -p /etc/homelab-storage-agent /etc/homelab-backup/status /etc/homelab-backup/secrets /etc/homelab-backup/health /var/log/homelab-restic
chmod 0755 /etc/homelab-storage-agent
chmod 0700 /etc/homelab-backup /etc/homelab-backup/status /etc/homelab-backup/secrets
chmod 0750 /var/log/homelab-restic
# Gitea tem caminho padrao no agente; Credenciais so entra se o host.env
# rendido trouxe CREDENCIAIS_BACKUP_DIR (host com a feature ligada).
mkdir -p "${GITEA_BACKUP_DIR:-/var/backups/gitea}" "${GITEA_USB_ROOT:-/mnt/gitea-usb}"
chmod 0700 "${GITEA_BACKUP_DIR:-/var/backups/gitea}" "${GITEA_USB_ROOT:-/mnt/gitea-usb}"
if [[ -n "${CREDENCIAIS_BACKUP_DIR:-}" ]]; then
  mkdir -p "$CREDENCIAIS_BACKUP_DIR"
  chmod 0700 "$CREDENCIAIS_BACKUP_DIR"
fi

systemctl daemon-reload
systemctl enable homelab-storage-agent
systemctl restart homelab-storage-agent
systemctl enable --now homelab-storage-snapshot.timer
systemctl enable --now homelab-storage-metrics.timer
systemctl enable --now homelab-restic-check.timer
if [[ -n "${CREDENCIAIS_DB:-}" && -f "$CREDENCIAIS_DB" ]]; then
  systemctl disable --now homelab-credenciais-backup.timer 2>/dev/null || true
  /usr/local/sbin/homelab-storage-agent --apply-timer || true
fi
sleep 1

echo "==> Status"
systemctl --no-pager --lines=5 status homelab-storage-agent || true
systemctl --no-pager --lines=3 status homelab-storage-snapshot.timer || true
ls -l /run/homelab-storage-admin/agent.sock

#!/usr/bin/env bash
# Prepara uma VM Ubuntu Server 26.04 para os testes de integracao da Moya.
# Rode como root, dentro da VM:
#   sudo INSTALL_DOCKER=1 bash scripts/vm/setup-ubuntu-2604.sh
#
# O script NAO ativa o UFW e NAO instala os repositorios das aplicacoes.
# Ele deixa o host pronto: Samba, grupos, share e2e, Mailpit, uv e ferramentas.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "ERRO: rode com sudo." >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
HOST_USER="${HOST_USER:-conrado}"
INSTALL_DOCKER="${INSTALL_DOCKER:-0}"

echo "==> Pacotes base"
apt-get update
apt-get install -y \
    ca-certificates curl git jq less nano netcat-openbsd openssh-server \
    python3 python3-venv python3-pip \
    samba samba-common-bin smbclient \
    parted e2fsprogs sqlite3 rsync \
    ufw restic smartmontools mdadm btrfs-progs \
    qemu-guest-agent

echo "==> Usuario ${HOST_USER}"
if ! id "$HOST_USER" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "$HOST_USER"
fi
cat >"/etc/sudoers.d/${HOST_USER}" <<EOF
${HOST_USER} ALL=(ALL) NOPASSWD:ALL
EOF
chmod 0440 "/etc/sudoers.d/${HOST_USER}"

echo "==> Grupos e diretorios do agente"
for grupo in drawings cnc kicad veronte impressao3d; do
    getent group "$grupo" >/dev/null || groupadd "$grupo"
done
mkdir -p \
    /srv/samba/e2e \
    /srv/samba/print_files \
    /srv/samba/cnc_files \
    /srv/samba/kicad_lib \
    /mnt/data/Veronte_Images \
    /mnt/data/Production_Files
chown -R "${HOST_USER}:${HOST_USER}" /srv/samba /mnt/data
chgrp drawings /srv/samba/e2e
chmod 2770 /srv/samba/e2e

echo "==> Share Samba de teste"
if ! grep -q '^\[e2e\]' /etc/samba/smb.conf; then
    cat >>/etc/samba/smb.conf <<'EOF'

[e2e]
   comment = Moya E2E
   path = /srv/samba/e2e
   browseable = yes
   read only = no
   valid users = @drawings
   create mask = 0660
   directory mask = 2770
EOF
fi
testparm -s >/dev/null
systemctl enable --now smbd
smbcontrol smbd reload-config 2>/dev/null || true

echo "==> Mailpit"
if ! command -v mailpit >/dev/null 2>&1; then
    case "$(uname -m)" in
        x86_64) MAILPIT_ARCH=amd64 ;;
        aarch64|arm64) MAILPIT_ARCH=arm64 ;;
        *) echo "ERRO: arquitetura sem Mailpit pre-compilado." >&2; exit 1 ;;
    esac
    tmp="$(mktemp -d)"
    curl -fsSL \
        "https://github.com/axllent/mailpit/releases/latest/download/mailpit-linux-${MAILPIT_ARCH}.tar.gz" \
        -o "${tmp}/mailpit.tar.gz"
    tar -xzf "${tmp}/mailpit.tar.gz" -C /usr/local/bin mailpit
    rm -rf "$tmp"
fi
cat >/etc/systemd/system/mailpit.service <<'EOF'
[Unit]
Description=Mailpit (SMTP de teste)
After=network.target

[Service]
ExecStart=/usr/local/bin/mailpit --smtp 127.0.0.1:1025 --listen 127.0.0.1:8025
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now mailpit

echo "==> uv"
if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
fi

echo "==> Docker (opcional)"
if [[ "$INSTALL_DOCKER" == "1" ]]; then
    apt-get install -y docker.io docker-compose-v2
    systemctl enable --now docker
    usermod -aG docker "$HOST_USER"
fi

echo "==> UFW (instalado, NAO ativado)"
ufw status || true

echo
echo "==> Pronto."
echo "Samba:   systemctl status smbd"
echo "Mailpit: systemctl status mailpit  (SMTP 127.0.0.1:1025, UI 127.0.0.1:8025)"
echo "UV:      $(command -v uv || echo 'nao encontrado')"
echo
echo "Proximos passos:"
echo "  1. copie moya_credenciais_app e homelab-storage-admin para /home/${HOST_USER}"
echo "  2. siga docs/VM_TESTES.md"

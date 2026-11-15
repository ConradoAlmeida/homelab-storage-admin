#!/usr/bin/env bash
# Aplica o perfil moyaserver na bancada de VM.
#
# Uso (root, dentro da VM, no clone do repo):
#   sudo bash scripts/vm/perfil-moya.sh
#
# Cria os paths que o moyaserver usa (/srv/samba, /mnt/data), a rede externa
# `moya` do overlay, gera /etc/homelab-storage-admin/host.env a partir do
# host.env.moya.example com os ajustes da VM, instala o agente e sincroniza as
# dependencias. Idempotente.
#
# Login pelo Credenciais nao entra aqui: este perfil deixa CREDENTIALS_URL
# vazio (login local/break-glass) porque o stack do Credenciais e do outro
# repo. O E2E de identidade continua em moya_credenciais_app/docs/E2E_VM.md.
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
if [[ ! -f "$REPO/host.env.moya.example" ]]; then
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

echo "==> paths do moyaserver"
for caminho in /srv/samba /mnt/data; do
  if mountpoint -q "$caminho" 2>/dev/null; then
    echo "    ja montado, preservado: $caminho"
    continue
  fi
  mkdir -p "$caminho"
  registra "$caminho"
  echo "    diretorio: $caminho"
done
mkdir -p /mnt/data/backups /var/backups/moya-credenciais
registra /var/backups/moya-credenciais
chown -R "$DONO:$DONO" /mnt/data
chmod 0700 /var/backups/moya-credenciais

echo "==> rede docker do Credenciais"
if docker network inspect moya >/dev/null 2>&1; then
  echo "    rede moya ja existe"
else
  docker network create moya >/dev/null
  echo "    rede moya criada (stub sem o Credenciais)"
fi

echo "==> host.env (perfil moyaserver)"
install -d -m 0755 /etc/homelab-storage-admin
install -m 0644 "$REPO/host.env.moya.example" /etc/homelab-storage-admin/host.env
cat >>/etc/homelab-storage-admin/host.env <<EOF

# ---- ajustes da bancada de VM (gerados por perfil-moya.sh) ----
DATA_DIR=$REPO/data
# Sem o stack do Credenciais nesta bancada: login local, sem desvio de IdP.
CREDENTIALS_URL=
EOF

echo "==> .env do clone"
if [[ ! -f "$REPO/.env" ]]; then
  install -m 0600 "$REPO/.env.example" "$REPO/.env"
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
(cd "$REPO" && HOST_ENV_PROFILE=moya ./install-agent.sh >/dev/null)
echo "    homelab-storage-agent: $(systemctl is-active homelab-storage-agent)"

echo "==> dependencias"
(cd "$REPO" && runuser -u "$DONO" -- uv sync --dev --frozen >/dev/null)
echo "    uv sync ok"

echo "==> mailpit"
if systemctl is-active --quiet mailpit; then
  echo "    ativo (smtp 127.0.0.1:1025, ui 127.0.0.1:8025)"
else
  echo "    AVISO: mailpit inativo; rode sudo bash scripts/vm/setup-ubuntu-2604.sh" >&2
fi

echo
echo "==> perfil moya pronto em $REPO"
echo "    app:  sudo docker compose -f docker-compose.yml -f docker-compose.moya.yml up -d --build"
echo "    testes: bash scripts/vm/run-unit-tests.sh"

#!/usr/bin/env bash
# Aplica o perfil `generico` na bancada de VM: um host que nao e Pi nem moya.
#
# Uso (root, dentro da VM, no clone do repo):
#   sudo bash scripts/vm/perfil-generico.sh
#
# O host nasce do wizard (`homelabctl init`), nao de um exemplo à mão: e o teste
# de que um Ubuntu Server generico roda so com o host.toml. Sem Samba, sem
# Caddy, sem Pi-hole, sem restic — as features ausentes nao podem gerar erro.
# Idempotente.
set -euo pipefail

MARKER=/etc/homelab-vm-bench
MANIFEST_DIR=/var/lib/homelab-vm-bench
MANIFEST="$MANIFEST_DIR/criado"
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
DONO=${SUDO_USER:-conrado}
TOML="$REPO/hosts/generico/host.toml"

if [[ $EUID -ne 0 ]]; then
  echo "ERRO: execute com sudo." >&2
  exit 1
fi
if [[ ! -f "$MARKER" ]]; then
  echo "ERRO: $MARKER nao existe; esta maquina nao e bancada." >&2
  exit 1
fi
if [[ ! -f "$REPO/scripts/homelabctl.py" ]]; then
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

echo "==> paths do host generico"
for caminho in /srv/dados /mnt/backup; do
  if [[ -d "$caminho" ]]; then
    echo "    ja existe, preservado: $caminho"
  else
    mkdir -p "$caminho"
    registra "$caminho"
    echo "    diretorio: $caminho"
  fi
done
chown -R "$DONO:$DONO" /srv/dados

echo "==> host.toml pelo wizard (detect + init)"
if [[ -f "$TOML" ]]; then
  echo "    ja existe, mantido: $TOML"
else
  cd "$REPO"
  HOMELAB_REPO="$REPO" python3 scripts/homelabctl.py init generico --sim --escrever >/dev/null
  echo "    criado: $TOML"
fi

# Ajustes da bancada: o TOML do wizard vem do lsblk/ip da VM; o resto (slugs,
# caminhos e features minimas) e o que este perfil quer provar.
python3 - "$TOML" "$REPO" <<'PY'
import sys
from pathlib import Path

repo = Path(sys.argv[2])
sys.path.insert(0, str(repo))
from core.homelab_config import carregar_arquivo  # noqa: E402
from core.homelab_detect import texto_toml  # noqa: E402

arquivo = Path(sys.argv[1])
dados = carregar_arquivo(arquivo).dados
dados["host"]["descricao"] = "Ubuntu Server generico (bancada de VM)"
dados["host"]["repo"] = str(repo)
dados["app"]["site_name"] = "Generico Storage"
dados["app"]["bind_addr"] = "0.0.0.0"
dados["caminhos"].update(
    {
        "dados": "/srv/dados",
        "snapshots": "/srv/dados/.snapshots",
        "backup": "/mnt/backup",
        "dados_app": str(repo / "data"),
    }
)
dados["armazenamento"].update(
    {
        "snapshot_backend": "rsync",
        "prefixos_permitidos": ["/srv/dados"],
        "mounts": ["/", "/srv/dados"],
    }
)
dados["features"] = {
    "samba": False,
    "discos": True,
    "snapshots": True,
    "restic": False,
    "copia_fria": False,
    "ufw": False,
    "terminal": False,
    "apt": True,
    "qbittorrent": False,
    "jellyfin": False,
    "pihole": False,
    "gitea": False,
    "portal": False,
    "credenciais": False,
    "django_admins": False,
}
arquivo.write_text(texto_toml(dados), encoding="utf-8")
PY
chown "$DONO:$DONO" "$TOML"
echo "    features minimas: discos, snapshots e apt"

echo "==> host.env e sync.env (render do TOML)"
cd "$REPO"
python3 scripts/homelabctl.py render generico --write --ambos

echo "==> .env do clone"
if [[ ! -f "$REPO/.env" ]]; then
  install -m 0600 "$REPO/.env.example" "$REPO/.env"
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
(cd "$REPO" && ./install-agent.sh >/dev/null)
echo "    homelab-storage-agent: $(systemctl is-active homelab-storage-agent)"

echo "==> dependencias"
(cd "$REPO" && runuser -u "$DONO" -- uv sync --dev --frozen >/dev/null)
echo "    uv sync ok"

echo "==> deploy/generico/apps.env"
mkdir -p "$REPO/deploy/generico"
if [[ ! -f "$REPO/deploy/generico/apps.env" ]]; then
  cat >"$REPO/deploy/generico/apps.env" <<EOF
# Apps do host generico: uma linha por app (ver docs/ROTINAS.md).
# Este host nao tem Caddy nem DNS; o atalho e o que importa.
painel|painel.generico.local|127.0.0.1:8060|-|atalho=painel,nome=Painel
EOF
  chown -R "$DONO:$DONO" "$REPO/deploy/generico"
  echo "    criado com a rota do painel"
else
  echo "    ja existe, mantido"
fi

echo "==> apps-sync sem Caddy nem DNS"
(cd "$REPO" && bash scripts/stacks/apps-sync.sh --apply)
echo "    estado e atalhos gerados; caddy/dns pulados"

mkdir -p "$REPO/data"
chown "$DONO:$DONO" "$REPO/data"

echo
echo "==> perfil generico pronto em $REPO"
echo "    app: ./deploy.sh (sem overlay)"
echo "    doctor: sudo scripts/stacks/apps-sync.sh --doctor"

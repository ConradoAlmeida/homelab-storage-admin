#!/usr/bin/env bash
# Limpa o estado que o Homelab Storage Admin deixa na bancada de VM.
#
# Uso (root, dentro da VM):
#   sudo bash scripts/vm/clean.sh              # mostra o que faria
#   sudo bash scripts/vm/clean.sh --apply      # executa e verifica
#
# So roda em bancada descartavel: exige /etc/homelab-vm-bench, criado pelo
# setup-ubuntu-2604.sh. Nunca use no Pi nem no moyaserver.
#
# Remove apenas o que o projeto instala (allowlist) e o que os perfis
# registraram em /var/lib/homelab-vm-bench/criado. Nao mexe em repositorios,
# containers de outras bancadas, nem em paths fora da lista.
set -euo pipefail

MARKER=/etc/homelab-vm-bench
MANIFEST_DIR=/var/lib/homelab-vm-bench
MANIFEST="$MANIFEST_DIR/criado"

APLICAR=0
for arg in "$@"; do
  case "$arg" in
    --apply) APLICAR=1 ;;
    --dry-run) APLICAR=0 ;;
    -h|--help)
      sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "ERRO: opcao desconhecida: $arg" >&2
      exit 2
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "ERRO: execute com sudo." >&2
  exit 1
fi

if [[ ! -f "$MARKER" ]]; then
  echo "ERRO: $MARKER nao existe." >&2
  echo "Esta maquina nao e uma bancada descartavel; o clean.sh nao roda aqui." >&2
  exit 1
fi

passo() { echo "==> $*"; }
executa() {
  if [[ "$APLICAR" -eq 1 ]]; then
    # Um passo que falha nao interrompe a limpeza no meio: avisa e deixa a
    # verificacao final apontar o residuo.
    "$@" || echo "    AVISO: falhou: $*" >&2
  else
    # stderr: varios chamadores redirecionam o stdout do comando.
    printf '[dry-run] %s\n' "$*" >&2
  fi
}

# ---------------------------------------------------------------- containers

PROJETOS=()
containers_do_projeto() {
  command -v docker >/dev/null 2>&1 || return 0
  docker ps -a --format '{{.ID}}|{{.Names}}|{{.Label "com.docker.compose.project.working_dir"}}' 2>/dev/null \
    | awk -F'|' '
        $3 ~ /homelab-storage-admin/ {print $1; print $3 > "/tmp/.clean-proj"; next}
        $2 == "homelab-storage-admin" || $2 == "qbittorrent" {print $1}
      ' || true
}

passo "containers do projeto"
rm -f /tmp/.clean-proj
IDS=$(containers_do_projeto)
if [[ -z "$IDS" ]]; then
  echo "    nenhum"
else
  for id in $IDS; do
    nome=$(docker inspect -f '{{.Name}}' "$id" 2>/dev/null | sed 's|^/||')
    imagem=$(docker inspect -f '{{.Config.Image}}' "$id" 2>/dev/null || true)
    echo "    container: ${nome:-$id}"
    executa docker rm -f "$id" >/dev/null
    if [[ -n "$imagem" ]]; then
      echo "    imagem do container: $imagem"
      executa docker rmi -f "$imagem" >/dev/null
    fi
  done
fi
if [[ -s /tmp/.clean-proj ]]; then
  while IFS= read -r wd; do
    proj=$(basename "$wd" | tr '[:upper:]' '[:lower:]')
    PROJETOS+=("$proj")
  done </tmp/.clean-proj
  rm -f /tmp/.clean-proj
fi
for proj in "${PROJETOS[@]:-}"; do
  [[ -n "$proj" ]] || continue
  if docker network inspect "${proj}_default" >/dev/null 2>&1; then
    echo "    rede: ${proj}_default"
    executa docker network rm "${proj}_default" >/dev/null
  fi
  for img in "${proj}-web" "${proj}_web"; do
    if docker image inspect "$img" >/dev/null 2>&1; then
      echo "    imagem: $img"
      executa docker rmi -f "$img" >/dev/null
    fi
  done
done

# ------------------------------------------------------------------ systemd

UNITS=(
  homelab-storage-agent.service
  homelab-storage-snapshot.service
  homelab-storage-snapshot.timer
  homelab-storage-metrics.service
  homelab-storage-metrics.timer
  homelab-restic-backup@.service
  homelab-cold-copy.service
  homelab-restic-check.service
  homelab-restic-check.timer
  homelab-gitea-backup@.service
  homelab-arquivos-backup@.service
  homelab-task@.service
)

passo "units e servicos"
for unit in "${UNITS[@]}"; do
  if [[ -f "/etc/systemd/system/$unit" ]]; then
    echo "    unit: $unit"
    executa systemctl disable --now "$unit" >/dev/null 2>&1
    executa rm -f "/etc/systemd/system/$unit"
  fi
done
if [[ "$APLICAR" -eq 1 ]]; then
  systemctl daemon-reload
  systemctl reset-failed >/dev/null 2>&1 || true
fi

# ------------------------------------------------------------------ arquivos

passo "binarios e diretorios"
for arq in \
  /usr/local/sbin/homelab-storage-agent \
  /usr/local/sbin/homelab-storage-snapshot \
  /usr/local/sbin/homelab-restic-backup \
  /usr/local/sbin/homelab-cold-copy \
  /etc/cron.d/samba-snapshots; do
  if [[ -e "$arq" ]]; then
    echo "    arquivo: $arq"
    executa rm -f "$arq"
  fi
done

for dir in \
  /etc/homelab-storage-admin \
  /etc/homelab-storage-agent \
  /etc/homelab-backup \
  /var/log/homelab-restic \
  /run/homelab-storage-admin; do
  if [[ -e "$dir" ]]; then
    echo "    diretorio: $dir"
    executa rm -rf "$dir"
  fi
done

# Paths que os perfis criaram (manifesto), nunca por inferencia.
if [[ -s "$MANIFEST" ]]; then
  passo "paths criados pelos perfis"
  while IFS= read -r caminho; do
    [[ -n "$caminho" ]] || continue
    if [[ ! -e "$caminho" ]]; then
      continue
    fi
    if mountpoint -q "$caminho" 2>/dev/null; then
      echo "    PULANDO (ponto de montagem): $caminho" >&2
      continue
    fi
    echo "    caminho: $caminho"
    executa rm -rf "$caminho"
  done <"$MANIFEST"
else
  passo "paths criados pelos perfis"
  echo "    manifesto ausente ou vazio: nada a remover por manifesto"
fi

# ------------------------------------------------------------------- samba

passo "samba"
if [[ -f "$MANIFEST_DIR/smb.conf.bench" ]]; then
  echo "    restaurando /etc/samba/smb.conf do baseline"
  executa cp "$MANIFEST_DIR/smb.conf.bench" /etc/samba/smb.conf
else
  echo "    baseline do smb.conf ausente: configuracao atual preservada"
fi
if command -v pdbedit >/dev/null 2>&1; then
  for usuario in $(pdbedit -L 2>/dev/null | awk -F: '{print $1}' | grep -E '^lab(user|grp)' || true); do
    echo "    usuario samba: $usuario"
    executa pdbedit -x -u "$usuario" >/dev/null
  done
fi
for grupo in $(getent group | awk -F: '{print $1}' | grep -E '^labgrp' || true); do
  echo "    grupo: $grupo"
  executa groupdel "$grupo"
done

# --------------------------------------------------------------------- ufw

passo "firewall"
if command -v ufw >/dev/null 2>&1; then
  echo "    reset das regras (bancada)"
  executa ufw --force reset >/dev/null
else
  echo "    ufw ausente"
fi

# ---------------------------------------------------------- verificacao final

if [[ "$APLICAR" -eq 0 ]]; then
  echo
  echo "==> dry-run: nada foi alterado. Use --apply para executar."
  exit 0
fi

rm -f "$MANIFEST"

passo "verificacao"
RESIDUO=0
checa() {
  local descricao=$1
  shift
  if "$@" >/dev/null 2>&1; then
    echo "    OK   $descricao"
  else
    echo "    FALHA $descricao" >&2
    RESIDUO=1
  fi
}
checa "sem units homelab-*" bash -c '! ls /etc/systemd/system/homelab-* >/dev/null 2>&1'
checa "sem binarios homelab-*" bash -c '! ls /usr/local/sbin/homelab-* >/dev/null 2>&1'
# O marker /etc/homelab-vm-bench e esperado e nao conta como residuo.
checa "sem /etc/homelab-*" bash -c '! ls -d /etc/homelab-storage-admin /etc/homelab-storage-agent /etc/homelab-backup >/dev/null 2>&1'
checa "sem sockets do agente" bash -c '! ls /run/homelab-storage-admin/*.sock >/dev/null 2>&1'
checa "sem containers do projeto" bash -c '! docker ps -a --format "{{.Names}}" | grep -qx "homelab-storage-admin"'

if [[ "$RESIDUO" -eq 1 ]]; then
  echo
  echo "ATENCAO: sobrou residuo; revise a lista acima antes de criar o snapshot." >&2
  exit 1
fi
echo
echo "CLEAN_OK"

#!/usr/bin/env bash
# Reconciler do Caddy e do DNS a partir do apps.env.
#
# O apps.env e a fonte da verdade: cada linha declara uma app exposta pelo
# Caddy. O script compara o declarado com o que esta aplicado (estado em
# /var/lib/homelab-storage-admin/apps.aplicados), gera as rotas, garante o
# DNS no Pi-hole e aponta o drift de containers e pastas.
#
#   scripts/stacks/apps-sync.sh                      # dry-run: mostra o plano
#   sudo scripts/stacks/apps-sync.sh --apply         # gera Caddy + DNS
#   sudo scripts/stacks/apps-sync.sh --perfil moya --apply
#   sudo scripts/stacks/apps-sync.sh --apply --prune-containers
#   sudo scripts/stacks/apps-sync.sh --apply --prune-containers --prune-data
#   scripts/stacks/apps-sync.sh --doctor             # so le: o que diverge?
#   scripts/stacks/apps-sync.sh --descobrir          # so le: sugerir apps
#
# Perfis:
#   pi (default)  *.conradhub.com com TLS (DNS-01), Caddy em arquivo separado
#                 (apps.caddy importado pelo Caddyfile) e wildcard no Pi-hole.
#   moya          *.local em HTTP:80, Caddy em arquivo separado (apps.caddy,
#                 importado pelo Caddyfile) e DNS por nome: `.local` e mDNS,
#                 entao nao ha wildcard.
#
# `--prune-containers` roda `docker compose down` (sem -v) so para quem saiu do
# env. `--prune-data` move a pasta para a quarentena, nunca apaga. Sem estado
# anterior nada e removido, so avisado.
set -euo pipefail

PERFIL=""
APLICAR=0
PODAR_CONTAINERS=0
PODAR_DADOS=0
YES=0
DOUTOR=0
DESCOBRIR=0
ERROS_DOUTOR=0
AVISOS_DOUTOR=0
DNS_EXATOS=0

uso() {
  cat <<'TXT'
Uso: scripts/stacks/apps-sync.sh [--perfil pi|moya] [--apply]
                                 [--prune-containers] [--prune-data] [--yes]
       scripts/stacks/apps-sync.sh [--perfil pi|moya] --doctor
       scripts/stacks/apps-sync.sh [--perfil pi|moya] --descobrir

Sem --apply e dry-run: mostra o plano e nao escreve nada.
  --perfil            pi (default) ou moya: muda caminhos, dominio e DNS
  --apply             gera as rotas, recarrega o Caddy e garante o DNS
  --prune-containers  `docker compose down` (sem -v) nas apps que sairam do env
  --prune-data        move a pasta das apps removidas para a quarentena
  --yes               nao pergunta antes de cada operacao destrutiva
  --doctor            so le: compara env, Caddy, DNS, containers e pastas
  --descobrir         so le: sugere linhas para stacks que ficaram fora do env

Os prunes exigem --apply e comparam com o estado da execucao anterior
(/var/lib/homelab-storage-admin/apps.aplicados). Sem esse arquivo, nada e
removido: o script so avisa o que saiu do env.

Formato do apps.env:
  key|fqdn|upstream|dir|flags
`dir` pode ser `-` (sem stack local). Flags: `manual` (bloco a mao no
Caddyfile), `redir=<destino>` ou `redir=<origem>-><destino>[@codigo]` e
`snippet=<nome>` (fragmento em <pasta do env>/snippets/<nome>.caddy).
Atalhos (opcionais, separados por virgula, sem virgula no texto):
  atalho=painel|portal|painel+portal|nao   (ausente = sem atalho)
  nome=, descricao=, cor=#rrggbb, icone=<slug>, grupo=<secao do portal>
O painel do Storage Admin e o portal do moya leem a INI gerada daqui:
nada de editar services.ini ou HTML do portal.
TXT
}

erro() {
  echo "ERRO: $*" >&2
  exit 2
}

aviso() {
  echo "AVISO: $*" >&2
}

secao() {
  echo
  echo "==> $*"
}

item() {
  echo "    $*"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APLICAR=1 ;;
    --prune-containers) PODAR_CONTAINERS=1 ;;
    --prune-data) PODAR_DADOS=1 ;;
    --yes) YES=1 ;;
    --doctor) DOUTOR=1 ;;
    --descobrir) DESCOBRIR=1 ;;
    --perfil)
      [[ $# -ge 2 ]] || erro "--perfil exige um valor: pi ou moya"
      PERFIL=$2
      shift
      ;;
    -h|--help) uso; exit 0 ;;
    *) erro "argumento desconhecido: $1 (veja --help)" ;;
  esac
  shift
done

# --- perfil do host -------------------------------------------------------
# O perfil muda so o que difere entre os hosts; variavel ja no ambiente vence.
case "${PERFIL:-pi}" in
  pi)
    PERFIL=pi
    SCHEME=${SCHEME:-https}
    DATA_DIR=${DATA_DIR:-/mnt/nas/apps/homelab-storage-admin/data}
    ;;
  moya)
    PERFIL=moya
    SCHEME=${SCHEME:-http}
    DATA_DIR=${DATA_DIR:-/opt/stacks/homelab-storage-admin/data}
    CADDY_DIR=${CADDY_DIR:-/opt/stacks/caddy}
    CADDY_CONTAINER=${CADDY_CONTAINER:-moya-caddy}
    PIHOLE_CONTAINER=${PIHOLE_CONTAINER:-pihole}
    DOMAIN=${DOMAIN:-local}
    DNS_IP=${DNS_IP:-192.168.0.10}
    DNS_MODE=${DNS_MODE:-nome}
    CADDY_PORTA=${CADDY_PORTA-:80}
    CADDY_TLS=${CADDY_TLS-}
    CADDY_PROXY=${CADDY_PROXY:-reverse_proxy}
    DIRS_PERMITIDOS=${DIRS_PERMITIDOS:-/opt/stacks /opt /home/conrado /data/compose}
    PIHOLE_DIR=${PIHOLE_DIR:-/home/conrado/pihole}
    QUARANTINE=${QUARANTINE:-/home/conrado/_removidos}
    DNS_CONF=${DNS_CONF:-/home/conrado/pihole/etc-dnsmasq.d/10-apps-local.conf}
    SCAN_ROOTS=${SCAN_ROOTS:-/opt /home/conrado}
    PORTAL_INI=${PORTAL_INI-/var/lib/homelab-storage-admin/apps-portal.ini}
    ;;
  *) erro "--perfil invalido: $PERFIL (use pi ou moya)" ;;
esac

# --- padroes comuns -------------------------------------------------------
# O env vive no repo, ao lado deste script: a fonte da verdade e versionada e
# o deploy.sh (git pull) a mantem no mesmo commit do codigo.
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
APPS_ENV=${APPS_ENV:-$REPO_ROOT/deploy/$PERFIL/apps.env}
APPS_STATE=${APPS_STATE:-/var/lib/homelab-storage-admin/apps.aplicados}
# Fragmentos de Caddyfile versionados: ficam ao lado do apps.env, no repo.
SNIPPETS_DIR=${SNIPPETS_DIR:-$(dirname "$APPS_ENV")/snippets}
STACKS_ROOT=${STACKS_ROOT:-/opt}
CADDY_CONTAINER=${CADDY_CONTAINER:-caddy}
PIHOLE_CONTAINER=${PIHOLE_CONTAINER:-pihole}
DOMAIN=${DOMAIN:-conradhub.com}
DNS_IP=${DNS_IP:-192.168.0.150}
DNS_MODE=${DNS_MODE:-wildcard}
DNS_QUERY_HOST=${DNS_QUERY_HOST:-127.0.0.1}
CADDY_PORTA=${CADDY_PORTA-}
CADDY_TLS=${CADDY_TLS-import cf}
CADDY_PROXY=${CADDY_PROXY:-import proxy}
DIRS_PERMITIDOS=${DIRS_PERMITIDOS:-$STACKS_ROOT/stacks $STACKS_ROOT}
SCAN_ROOTS=${SCAN_ROOTS:-$STACKS_ROOT}

CADDY_DIR=${CADDY_DIR:-$STACKS_ROOT/stacks/caddy}
CADDYFILE=${CADDYFILE:-$CADDY_DIR/Caddyfile}
CADDY_APPS=${CADDY_APPS:-$CADDY_DIR/apps.caddy}
CADDY_TOKEN_FILE=${CADDY_TOKEN_FILE:-$CADDY_DIR/cloudflare.token}
PIHOLE_DIR=${PIHOLE_DIR:-$STACKS_ROOT/stacks/pihole}
DNS_CONF=${DNS_CONF:-$PIHOLE_DIR/etc-dnsmasq.d/10-$DOMAIN-wildcard.conf}
QUARANTINE=${QUARANTINE:-$STACKS_ROOT/stacks/_removidos}
TEST_MODE=${TEST_MODE:-0}

# Atalhos gerados a partir do env. O painel le INI do DATA_DIR (settings
# SERVICES_FILE) e o portal do moya le a mesma INI de uma pasta montada
# read-only. Vazio desliga a geracao.
SERVICES_INI=${SERVICES_INI-${DATA_DIR:+$DATA_DIR/services.ini}}
PORTAL_INI=${PORTAL_INI-}

# Pastas que o reconciler nunca move: derrubar o proxy ou o DNS no meio da
# operacao deixaria a casa sem rede.
PROTEGIDOS=("$CADDY_DIR" "$PIHOLE_DIR")

case "$DNS_MODE" in
  wildcard|nome) ;;
  *) erro "DNS_MODE invalido: $DNS_MODE (use wildcard ou nome)" ;;
esac

declare -A FQDN=() UPSTREAM=() DIR=() FLAGS=()
declare -A ANT_FQDN=() ANT_UPSTREAM=() ANT_DIR=() ANT_FLAGS=()
KEYS=()
ANT_KEYS=()

# `read -a` come o campo vazio no fim da linha; o env usa `...|` para "sem
# flags", entao o contador de delimitadores define quantos campos repor.
split_linha() {
  local linha=$1 delims=${1//[^|]/}
  IFS='|' read -r -a CAMPOS <<<"$linha"
  while [[ ${#CAMPOS[@]} -lt $(( ${#delims} + 1 )) ]]; do
    CAMPOS+=("")
  done
}

dir_valido() {
  local d=$1 raiz base
  [[ "$d" == /* ]] || return 1
  [[ "$d" != *..* ]] || return 1
  for raiz in $DIRS_PERMITIDOS; do
    [[ "$d" == "$raiz"/* ]] || continue
    base=${d##*/}
    [[ "$base" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] && return 0
  done
  return 1
}

# `redir=<destino>` (raiz do site) ou `redir=<origem>-><destino>[@codigo]`.
# A origem padrao e `/` e o codigo padrao e 302 (temporario).
valida_redir() {
  local linha=$1 valor=$2 origem destino codigo
  if [[ -z "$valor" || "$valor" == *" "* ]]; then
    aviso "$APPS_ENV:$linha: redir vazio ou com espaco ('$valor')"
    return 1
  fi
  if [[ "$valor" == *"->"* ]]; then
    origem=${valor%%->*}
    destino=${valor#*->}
  else
    origem=/
    destino=$valor
  fi
  codigo=302
  if [[ "$destino" == *"@"* ]]; then
    codigo=${destino##*@}
    destino=${destino%@*}
  fi
  if [[ "$origem" != /* || "$destino" != /* ]]; then
    aviso "$APPS_ENV:$linha: redir '$valor' precisa de origem e destino comecando com /"
    return 1
  fi
  if [[ ! "$codigo" =~ ^3[0-9]{2}$ ]]; then
    aviso "$APPS_ENV:$linha: redir '$valor' com codigo invalido '$codigo' (use 3xx)"
    return 1
  fi
  return 0
}

caminho_snippet() {
  echo "$SNIPPETS_DIR/$1.caddy"
}

valida_snippet() {
  local linha=$1 nome=$2 arquivo
  if [[ ! "$nome" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    aviso "$APPS_ENV:$linha: snippet '$nome' invalido (use [a-z0-9-])"
    return 1
  fi
  arquivo=$(caminho_snippet "$nome")
  if [[ ! -s "$arquivo" ]]; then
    aviso "$APPS_ENV:$linha: snippet '$nome' nao encontrado ou vazio: $arquivo"
    return 1
  fi
  return 0
}

valida() {
  local linhas=0
  local erros=0
  local linha key fqdn upstream dir flags campo nome flag_nome
  local -a campos
  local -A vistos=()

  [[ -r "$APPS_ENV" ]] || erro "nao consigo ler $APPS_ENV (esperado deploy/$PERFIL/apps.env no checkout)"
  [[ "$DOMAIN" =~ ^[a-z0-9.-]+$ ]] || erro "dominio invalido: $DOMAIN"

  while IFS= read -r linha || [[ -n "$linha" ]]; do
    linhas=$((linhas + 1))
    linha=${linha%$'\r'}
    [[ -z "${linha// /}" ]] && continue
    [[ "$linha" =~ ^[[:space:]]*# ]] && continue

    split_linha "$linha"
    campos=("${CAMPOS[@]}")
    if [[ ${#campos[@]} -ne 5 ]]; then
      aviso "$APPS_ENV:$linhas: esperava 5 campos (key|fqdn|upstream|dir|flags), achei ${#campos[@]}"
      erros=$((erros + 1))
      continue
    fi
    key=${campos[0]} fqdn=${campos[1]} upstream=${campos[2]} dir=${campos[3]} flags=${campos[4]}
    key=${key// /} fqdn=${fqdn// /} upstream=${upstream// /} dir=${dir// /}
    # As flags carregam texto (nome=, descricao=) com espaco: so as bordas saem.
    flags=$(trim "$flags")

    if [[ ! "$key" =~ ^[a-z0-9][a-z0-9-]*$ || ${#key} -gt 40 ]]; then
      aviso "$APPS_ENV:$linhas: key invalida '$key' (use [a-z0-9-], ate 40)"
      erros=$((erros + 1))
    fi
    if [[ ! "$fqdn" =~ ^[a-z0-9][a-z0-9.-]*\.$DOMAIN$ ]]; then
      aviso "$APPS_ENV:$linhas: fqdn '$fqdn' fora de .$DOMAIN"
      erros=$((erros + 1))
    fi
    if [[ ! "$upstream" =~ ^[A-Za-z0-9._-]+:[0-9]{1,5}$ ]]; then
      aviso "$APPS_ENV:$linhas: upstream '$upstream' invalido (host:porta)"
      erros=$((erros + 1))
    fi
    if [[ "$dir" == "-" ]]; then
      # Sem stack local: nao ha container para conferir, a rota e o DNS valem.
      :
    elif ! dir_valido "$dir"; then
      aviso "$APPS_ENV:$linhas: dir '$dir' fora de: $DIRS_PERMITIDOS"
      erros=$((erros + 1))
    fi
    if [[ -n "$flags" ]]; then
      if [[ ",$flags," == *",manual,"* && "$flags" != "manual" ]]; then
        aviso "$APPS_ENV:$linhas: 'manual' nao combina com outra flag ('$flags')"
        erros=$((erros + 1))
      fi
      IFS=',' read -r -a campos <<<"$flags"
      vistos=()
      for campo in "${campos[@]}"; do
        campo=$(trim "$campo")
        [[ -n "$campo" ]] || { aviso "$APPS_ENV:$linhas: flag vazia em '$flags'"; erros=$((erros + 1)); continue; }
        flag_nome=${campo%%=*}
        if [[ -n "${vistos[$flag_nome]:-}" ]]; then
          aviso "$APPS_ENV:$linhas: flag '$flag_nome' repetida"
          erros=$((erros + 1))
        fi
        vistos[$flag_nome]=1
        case "$campo" in
          manual) ;;
          redir=*)
            valida_redir "$linhas" "${campo#redir=}" || erros=$((erros + 1))
            ;;
          snippet=*)
            valida_snippet "$linhas" "${campo#snippet=}" || erros=$((erros + 1))
            ;;
          atalho=*)
            case "${campo#atalho=}" in
              painel|portal|painel+portal|nao) ;;
              *)
                aviso "$APPS_ENV:$linhas: atalho '${campo#atalho=}' invalido (painel, portal, painel+portal, nao)"
                erros=$((erros + 1))
                ;;
            esac
            ;;
          nome=*)
            [[ -n "$(trim "${campo#nome=}")" ]] ||
              { aviso "$APPS_ENV:$linhas: nome= vazio"; erros=$((erros + 1)); }
            ;;
          descricao=*) ;;
          cor=*)
            [[ "${campo#cor=}" =~ ^#[0-9a-fA-F]{6}$ ]] ||
              { aviso "$APPS_ENV:$linhas: cor '${campo#cor=}' invalida (use #rrggbb)"; erros=$((erros + 1)); }
            ;;
          icone=*)
            [[ "${campo#icone=}" =~ ^[a-z0-9][a-z0-9-]*$ ]] ||
              { aviso "$APPS_ENV:$linhas: icone '${campo#icone=}' invalido (use [a-z0-9-])"; erros=$((erros + 1)); }
            ;;
          grupo=*)
            [[ "${campo#grupo=}" =~ ^[a-z][a-z0-9-]*$ ]] ||
              { aviso "$APPS_ENV:$linhas: grupo '${campo#grupo=}' invalido (use [a-z0-9-])"; erros=$((erros + 1)); }
            ;;
          *)
            aviso "$APPS_ENV:$linhas: flag desconhecida '$campo' (manual, redir=, snippet=, atalho=, nome=, descricao=, cor=, icone=, grupo=)"
            erros=$((erros + 1))
            ;;
        esac
      done
    fi
    for nome in "${KEYS[@]:-}"; do
      [[ "$nome" == "$key" ]] && { aviso "$APPS_ENV:$linhas: key repetida '$key'"; erros=$((erros + 1)); }
    done
    for nome in "${KEYS[@]:-}"; do
      [[ -n "$nome" && "${FQDN[$nome]:-}" == "$fqdn" ]] && { aviso "$APPS_ENV:$linhas: fqdn repetido '$fqdn'"; erros=$((erros + 1)); }
    done
    for nome in "${KEYS[@]:-}"; do
      # `-` significa "sem stack local": varias apps manuais sem pasta podem
      # conviver, mas duas apps na mesma pasta nao.
      [[ "$dir" != "-" && -n "$nome" && "${DIR[$nome]:-}" == "$dir" ]] &&
        { aviso "$APPS_ENV:$linhas: dir repetido '$dir'"; erros=$((erros + 1)); }
    done

    KEYS+=("$key")
    FQDN[$key]=$fqdn UPSTREAM[$key]=$upstream DIR[$key]=$dir FLAGS[$key]=$flags
  done <"$APPS_ENV"

  [[ $erros -eq 0 ]] || erro "$erros linha(s) invalida(s) em $APPS_ENV; nada foi alterado"
  [[ ${#KEYS[@]} -gt 0 ]] || erro "$APPS_ENV nao declara nenhuma app"
}

le_estado() {
  local linha key fqdn upstream dir flags
  local -a campos
  [[ -e "$APPS_STATE" ]] || return 0
  if [[ ! -r "$APPS_STATE" ]]; then
    aviso "$APPS_STATE existe mas nao esta legivel; sem sudo o plano nao ve o estado"
    return 0
  fi
  while IFS= read -r linha || [[ -n "$linha" ]]; do
    linha=${linha%$'\r'}
    [[ -z "${linha// /}" ]] && continue
    [[ "$linha" =~ ^[[:space:]]*# ]] && continue
    split_linha "$linha"
    campos=("${CAMPOS[@]}")
    [[ ${#campos[@]} -eq 5 ]] || continue
    key=${campos[0]} fqdn=${campos[1]} upstream=${campos[2]} dir=${campos[3]} flags=${campos[4]}
    ANT_KEYS+=("$key")
    ANT_FQDN[$key]=$fqdn ANT_UPSTREAM[$key]=$upstream ANT_DIR[$key]=$dir ANT_FLAGS[$key]=$flags
  done <"$APPS_STATE"
}

declarada() {
  local k
  for k in "${KEYS[@]}"; do
    [[ "$k" == "$1" ]] && return 0
  done
  return 1
}

declarado_fqdn() {
  local k
  for k in "${KEYS[@]}"; do
    [[ "${FQDN[$k]}" == "$1" ]] && return 0
  done
  return 1
}

e_manual() {
  [[ ",${FLAGS[$1]:-}," == *",manual,"* ]]
}

# Valor de um flag `nome=valor` da app (vazio quando ausente). Os flags sao
# separados por virgula, entao o valor nao pode ter virgula.
flag_da_app() {
  local k=$1 alvo=$2 campo
  local -a campos=()
  IFS=',' read -r -a campos <<<"${FLAGS[$k]:-}"
  for campo in "${campos[@]}"; do
    [[ "$campo" == "$alvo="* ]] && printf '%s' "${campo#"$alvo="}"
  done
  return 0
}

# "origem destino codigo" do flag redir, ou vazio.
redir_da_app() {
  local valor origem destino codigo
  valor=$(flag_da_app "$1" redir)
  [[ -n "$valor" ]] || return 0
  if [[ "$valor" == *"->"* ]]; then
    origem=${valor%%->*}
    destino=${valor#*->}
  else
    origem=/
    destino=$valor
  fi
  codigo=302
  if [[ "$destino" == *"@"* ]]; then
    codigo=${destino##*@}
    destino=${destino%@*}
  fi
  printf '%s %s %s' "$origem" "$destino" "$codigo"
}

snippet_da_app() {
  flag_da_app "$1" snippet
}

# --- Atalhos (painel e portal) --------------------------------------------
# O env declara a apresentacao; o script gera a INI que o painel ja sabe ler.
# Sem `atalho=` a app tem rota e DNS, mas nao aparece em lugar nenhum.

trim() {
  local v=$1
  v=${v#"${v%%[![:space:]]*}"}
  v=${v%"${v##*[![:space:]]}"}
  printf '%s' "$v"
}

# atalho=painel | portal | painel+portal | nao (ausente = nenhum)
atalho_inclui() {
  local valor
  valor=$(flag_da_app "$1" atalho)
  case "$2:${valor:-nao}" in
    painel:painel|painel:painel+portal|portal:portal|portal:painel+portal) return 0 ;;
    *) return 1 ;;
  esac
}

nome_da_app() {
  local n
  n=$(flag_da_app "$1" nome)
  if [[ -z "$n" ]]; then
    n=${FQDN[$1]%%.*}
    n=${n//-/ }
    n="${n^}"
  fi
  printf '%s' "$n"
}

descricao_da_app() { flag_da_app "$1" descricao; }
cor_da_app() { local c; c=$(flag_da_app "$1" cor); printf '%s' "${c:-#38bdf8}"; }
icone_da_app() { local i; i=$(flag_da_app "$1" icone); printf '%s' "${i:-generic}"; }
# Secao do portal (services, infrastructure, tools ...); o painel ignora.
grupo_da_app() { local g; g=$(flag_da_app "$1" grupo); printf '%s' "${g:-services}"; }
url_da_app() { printf '%s://%s' "$SCHEME" "${FQDN[$1]}"; }

render_atalhos() {
  local tipo=$1 k ordem=10 nome descricao
  printf '# Gerado por scripts/stacks/apps-sync.sh a partir de %s.\n' "$(basename "$APPS_ENV")"
  printf '# Nao edite: a proxima execucao sobrescreve. A fonte da verdade e o apps.env.\n'
  for k in "${KEYS[@]}"; do
    atalho_inclui "$k" "$tipo" || continue
    nome=$(nome_da_app "$k")
    descricao=$(descricao_da_app "$k")
    printf '\n[%s]\n' "$k"
    printf 'name = %s\n' "$nome"
    [[ -z "$descricao" ]] || printf 'description = %s\n' "$descricao"
    printf 'url = %s\nicon = %s\ncolor = %s\norder = %s\ngroup = %s\n' \
      "$(url_da_app "$k")" "$(icone_da_app "$k")" "$(cor_da_app "$k")" "$ordem" \
      "$(grupo_da_app "$k")"
    ordem=$((ordem + 10))
  done
}

escreve_atalhos() {
  local tipo=$1 destino=$2 tmp backup pasta
  [[ -n "$destino" ]] || return 0
  pasta=$(dirname "$destino")
  if [[ ! -d "$pasta" ]]; then
    aviso "atalhos ($tipo): $pasta nao existe; $destino nao gerado"
    return 0
  fi
  tmp=$(mktemp "$pasta/.atalhos.XXXXXX")
  render_atalhos "$tipo" >"$tmp"
  if [[ -f "$destino" ]] && cmp -s "$tmp" "$destino"; then
    rm -f "$tmp"
    item "atalhos ($tipo) sem mudanca: $destino"
    return 0
  fi
  if [[ -e "$destino" && ! -f "$destino" ]]; then
    rm -f "$tmp"
    aviso "atalhos ($tipo): $destino existe e nao e arquivo; nada foi escrito"
    return 0
  fi
  if [[ -f "$destino" ]] &&
    ! head -1 "$destino" | grep -qF 'Gerado por scripts/stacks/apps-sync.sh'; then
    # Arquivo escrito a mao: guarda antes de assumir; a curadoria agora e flag.
    backup="$destino.bak-$(date +%Y%m%d-%H%M%S)"
    cp -p "$destino" "$backup"
    aviso "atalhos ($tipo): $destino nao era gerado; copia em $backup"
  fi
  preserva_dono "$tmp" "$destino"
  mv -f "$tmp" "$destino"
  item "atalhos ($tipo) atualizados: $destino"
}

aplica_atalhos() {
  escreve_atalhos painel "$SERVICES_INI"
  escreve_atalhos portal "$PORTAL_INI"
}

endereco_site() {
  echo "${FQDN[$1]}$CADDY_PORTA"
}

projeto() {
  basename "$1"
}

tem_docker() {
  command -v docker >/dev/null 2>&1
}

# O nome do projeto compose nem sempre e o da pasta (Portainer, stacks com
# maiuscula): o rotulo guarda o diretorio real. A pasta declara o dono, o
# rotulo confirma.
containers_do_dir() {
  docker ps -a \
    --filter "label=com.docker.compose.project.working_dir=$1" \
    --format '{{.Names}}' 2>/dev/null || true
}

projeto_do_dir() {
  local projeto
  projeto=$(docker ps -a \
    --filter "label=com.docker.compose.project.working_dir=$1" \
    --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null | head -1 || true)
  echo "${projeto:-$(projeto "$1")}"
}

# --- Caddy ----------------------------------------------------------------

gera_blocos() {
  local k redir snippet
  for k in "${KEYS[@]}"; do
    e_manual "$k" && continue
    printf '\n%s {\n' "$(endereco_site "$k")"
    [[ -n "$CADDY_TLS" ]] && printf '\t%s\n' "$CADDY_TLS"
    redir=$(redir_da_app "$k")
    [[ -z "$redir" ]] || printf '\tredir %s\n' "$redir"
    snippet=$(snippet_da_app "$k")
    if [[ -n "$snippet" ]]; then
      # O fragmento e escrito na coluna zero; um tab preserva a leitura.
      awk 'NF { print "\t" $0; next } { print "" }' "$(caminho_snippet "$snippet")"
    fi
    printf '\t%s %s\n}\n' "$CADDY_PROXY" "${UPSTREAM[$k]}"
  done
}

gera_apps() {
  cat <<TXT
# Gerado por scripts/stacks/apps-sync.sh. A fonte da verdade e $APPS_ENV.
# Nao edite este arquivo: ele e reescrito na proxima execucao.
TXT
  gera_blocos
}

conflito_no_caddyfile() {
  local fqdn=$1 endereco=$2 linha n conteudo corpo
  local -a linhas=()
  mapfile -t linhas < <(grep -nF "$fqdn" "$CADDYFILE" 2>/dev/null | cut -d: -f1 || true)
  for n in "${linhas[@]:-}"; do
    [[ -n "$n" ]] || continue
    conteudo=$(sed -n "${n}p" "$CADDYFILE")
    conteudo=${conteudo%$'\r'}
    if [[ "$conteudo" != "$fqdn {" && "$conteudo" != "$fqdn{" &&
          "$conteudo" != "$endereco {" && "$conteudo" != "$endereco{" ]]; then
      item "conflito: $CADDYFILE:$n ja cita $fqdn de forma que o gerador nao sabe remover:"
      item "  $conteudo"
      return 0
    fi
    # O bloco so pode ser removido se o corpo nao tiver chaves aninhadas.
    corpo=$(sed -n "$((n + 1)),/^}$/p" "$CADDYFILE")
    if grep -q '{' <<<"$corpo"; then
      item "conflito: o bloco de $fqdn em $CADDYFILE:$n tem chaves aninhadas"
      item "  remova a mao (ou marque a app como manual) e rode de novo"
      return 0
    fi
  done
  return 1
}

# Remove um bloco de host simples (cabecalho `endereco {`, corpo sem chaves
# aninhadas, fecha em `}` na coluna 0). Recusa qualquer estrutura diferente.
remove_bloco() {
  local arquivo=$1 endereco=$2 escapado
  escapado=$(printf '%s' "$endereco" | sed 's/\./[.]/g')
  awk -v alvo="^$escapado[ \t]*[{][ \t]*$" '
    pula == 1 {
      if ($0 ~ /^[ \t]*[{]/) { erro = 1 }
      if ($0 ~ /^[}][ \t]*$/) { pula = 0; next }
      next
    }
    $0 ~ alvo { pula = 1; next }
    { print }
    END { if (erro) exit 3 }
  ' "$arquivo"
}

# O arquivo e reescrito como root. Mantem dono e modo do original para o
# operador seguir editando sem sudo (moya) e o Pi continuar em 644.
preserva_dono() {
  local novo=$1 referencia=$2
  if [[ -f "$referencia" ]]; then
    chmod --reference="$referencia" "$novo" 2>/dev/null || chmod 0644 "$novo"
    chown --reference="$referencia" "$novo" 2>/dev/null || true
  else
    chmod 0644 "$novo"
  fi
}

aplica_caddy() {
  local k tmp backup mudou=0 endereco
  local -a geradas=()
  local conflitos=0

  [[ -f "$CADDYFILE" ]] || erro "Caddyfile nao encontrado em $CADDYFILE"

  mkdir -p "$CADDY_DIR"

  for k in "${KEYS[@]}"; do
    e_manual "$k" && continue
    endereco=$(endereco_site "$k")
    geradas+=("$endereco")
    conflito_no_caddyfile "${FQDN[$k]}" "$endereco" && conflitos=$((conflitos + 1))
  done
  [[ $conflitos -eq 0 ]] || erro "resolva os conflitos acima no Caddyfile e rode de novo; nada foi alterado"

  backup="$CADDYFILE.bak-$(date +%Y%m%d-%H%M%S)"

  tmp=$(mktemp "$CADDY_DIR/.apps.caddy.XXXXXX")
  gera_apps >"$tmp"
  if [[ -f "$CADDY_APPS" ]] && cmp -s "$tmp" "$CADDY_APPS"; then
    rm -f "$tmp"
    item "apps.caddy sem mudanca"
  else
    preserva_dono "$tmp" "$CADDY_APPS"
    mv -f "$tmp" "$CADDY_APPS"
    item "apps.caddy atualizado: $CADDY_APPS"
    mudou=1
  fi

  # O Caddyfile importa apps.caddy de dentro do container. Se o bind mount
  # nao existe, o import falha e o Caddy antigo continua no ar: melhor parar
  # aqui, antes de editar o Caddyfile.
  if ! docker exec "$CADDY_CONTAINER" test -f /etc/caddy/apps.caddy 2>/dev/null; then
    erro "o container $CADDY_CONTAINER nao ve /etc/caddy/apps.caddy.
    Monte a pasta do Caddy em $CADDY_DIR/compose.yaml, no lugar dos mounts
    de Caddyfile e cloudflare.token:
      - ./:/etc/caddy:ro
    Depois: docker compose up -d && sudo $0 --apply"
  fi

  if ! grep -qxF 'import apps.caddy' "$CADDYFILE"; then
    cp -p "$CADDYFILE" "$backup"
    tmp=$(mktemp "$CADDY_DIR/.Caddyfile.XXXXXX")
    garante_import <"$CADDYFILE" >"$tmp"
    preserva_dono "$tmp" "$CADDYFILE"
    mv -f "$tmp" "$CADDYFILE"
    item "import apps.caddy adicionado ao Caddyfile (backup: $(basename "$backup"))"
    mudou=1
  fi

  for endereco in "${geradas[@]:-}"; do
    [[ -n "$endereco" ]] || continue
    grep -qxF "$endereco {" "$CADDYFILE" || continue
    tmp=$(mktemp "$CADDY_DIR/.Caddyfile.XXXXXX")
    if ! remove_bloco "$CADDYFILE" "$endereco" >"$tmp"; then
      rm -f "$tmp"
      erro "o bloco de $endereco no Caddyfile tem chaves aninhadas; remova a mao e rode de novo"
    fi
    [[ -f "$backup" ]] || cp -p "$CADDYFILE" "$backup"
    preserva_dono "$tmp" "$CADDYFILE"
    mv -f "$tmp" "$CADDYFILE"
    item "bloco de $endereco saiu do Caddyfile (agora vem de apps.caddy)"
    mudou=1
  done

  # Depois de tirar blocos que passaram a ser gerados, sobram linhas vazias
  # no topo. Uma linha em branco entre blocos ja basta.
  if grep -qE '^[[:space:]]*$' "$CADDYFILE"; then
    tmp=$(mktemp "$CADDY_DIR/.Caddyfile.XXXXXX")
    awk 'BEGIN { vazias = 0; impressas = 0 }
         /^[[:space:]]*$/ { vazias++; if (vazias <= 1 && impressas) print ""; next }
         { vazias = 0; impressas = 1; print }' "$CADDYFILE" >"$tmp"
    if cmp -s "$tmp" "$CADDYFILE"; then
      rm -f "$tmp"
    else
      [[ -f "$backup" ]] || cp -p "$CADDYFILE" "$backup"
      preserva_dono "$tmp" "$CADDYFILE"
      mv -f "$tmp" "$CADDYFILE"
      item "linhas em branco extras removidas do Caddyfile"
      mudou=1
    fi
  fi

  caddy_validate || erro "caddy validate falhou; Caddyfile e apps.caddy mantidos, sem reload"
  if [[ $mudou -eq 1 ]]; then
    caddy_reload || erro "caddy reload falhou"
    item "Caddy recarregado"
  else
    item "Caddy ja estava com a configuracao do env"
  fi

  for k in "${KEYS[@]}"; do
    e_manual "$k" || continue
    if ! grep -qF "${FQDN[$k]}" "$CADDYFILE"; then
      aviso "${FQDN[$k]} esta marcada como manual mas nao aparece no Caddyfile"
    fi
  done
}

garante_import() {
  # Le o Caddyfile do stdin e devolve com o import no fim: os snippets (cf,
  # proxy) ja estao definidos acima, entao a ordem e segura.
  cat
  printf '\nimport apps.caddy\n'
}

caddy_validate() {
  local token=""
  if [[ -r "$CADDY_TOKEN_FILE" ]]; then
    token=$(tr -d '\r\n' <"$CADDY_TOKEN_FILE")
  fi
  if [[ -n "$token" ]]; then
    docker exec -e "CLOUDFLARE_API_TOKEN=$token" "$CADDY_CONTAINER" \
      caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1
    return
  fi
  if grep -q '{env\.' "$CADDYFILE"; then
    aviso "sem $CADDY_TOKEN_FILE; validando sem o token da Cloudflare"
  fi
  docker exec "$CADDY_CONTAINER" \
    caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1
}

caddy_reload() {
  docker exec "$CADDY_CONTAINER" \
    caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1
}

# --- DNS ------------------------------------------------------------------

gera_dns() {
  local k
  cat <<TXT
# Gerado por scripts/stacks/apps-sync.sh. Nao edite: ele e reescrito.
TXT
  if [[ "$DNS_MODE" == "wildcard" ]]; then
    cat <<TXT
# Qualquer nome em *.$DOMAIN responde com o Pi; nao ha entrada por app.
# Entradas exatas no Pi-hole (custom.list) continuam valendo.
address=/$DOMAIN/$DNS_IP
TXT
  else
    cat <<TXT
# Uma entrada por app declarada: $DOMAIN e mDNS, entao sem wildcard.
TXT
    for k in "${KEYS[@]}"; do
      echo "address=/${FQDN[$k]}/$DNS_IP"
    done
  fi
}

aplica_dns() {
  local tmp atual=0
  mkdir -p "$(dirname "$DNS_CONF")"
  tmp=$(mktemp "$(dirname "$DNS_CONF")/.dns.XXXXXX")
  gera_dns >"$tmp"
  if [[ -f "$DNS_CONF" ]] && cmp -s "$tmp" "$DNS_CONF"; then
    rm -f "$tmp"
    item "DNS sem mudanca: $DNS_CONF"
  else
    chmod 0644 "$tmp"
    mv -f "$tmp" "$DNS_CONF"
    item "DNS gravado: $DNS_CONF"
    atual=1
  fi

  if [[ "$(docker exec "$PIHOLE_CONTAINER" pihole-FTL --config misc.etc_dnsmasq_d 2>/dev/null | tail -1)" != "true" ]]; then
    docker exec "$PIHOLE_CONTAINER" pihole-FTL --config misc.etc_dnsmasq_d true >/dev/null 2>&1 ||
      erro "nao consegui ligar misc.etc_dnsmasq_d no Pi-hole"
    item "misc.etc_dnsmasq_d ligado no pihole.toml"
    atual=1
  fi

  if [[ $atual -eq 1 ]]; then
    docker restart "$PIHOLE_CONTAINER" >/dev/null 2>&1 || erro "falhou o restart do $PIHOLE_CONTAINER"
    item "Pi-hole reiniciado para ler $DNS_CONF"
  fi

  confirma_dns
}

confirma_dns() {
  local tentativa alvo valor k
  local -a alvos=()
  if [[ "$DNS_MODE" == "wildcard" ]]; then
    alvos=("sync-1.$DOMAIN")
  else
    for k in "${KEYS[@]}"; do
      alvos+=("${FQDN[$k]}")
    done
  fi
  for tentativa in $(seq 1 20); do
    local faltou=""
    for alvo in "${alvos[@]}"; do
      valor=$(dig +short +time=2 +tries=1 "$alvo" @"$DNS_QUERY_HOST" 2>/dev/null | head -1 || true)
      [[ "$valor" == "$DNS_IP" ]] || faltou=$alvo
    done
    if [[ -z "$faltou" ]]; then
      item "DNS confirmado: ${#alvos[@]} nome(s) -> $DNS_IP"
      return 0
    fi
    sleep 1
  done
  erro "o Pi-hole nao respondeu $faltou com $DNS_IP; confira $DNS_CONF e misc.etc_dnsmasq_d"
}

# --- Containers e pastas --------------------------------------------------

lista_removidas() {
  local k
  for k in "${ANT_KEYS[@]}"; do
    declarada "$k" || echo "$k"
  done
}

relata_containers() {
  local k projeto_nome presentes ausentes=0
  if ! tem_docker; then
    aviso "docker nao encontrado; check de containers pulado"
    return 0
  fi
  for k in "${KEYS[@]}"; do
    [[ "${DIR[$k]}" == "-" ]] && continue
    presentes=$(containers_do_dir "${DIR[$k]}" | paste -sd, -)
    if [[ -z "$presentes" ]]; then
      projeto_nome=$(projeto "${DIR[$k]}")
      item "container ausente: $k (projeto compose '$projeto_nome', dir ${DIR[$k]})"
      ausentes=$((ausentes + 1))
    else
      item "container ok: $k -> $presentes"
    fi
  done
  [[ "$ausentes" -eq 0 ]] || item "containers ausentes nao sao iniciados por este script; suba com ./deploy.sh ou docker compose"
}

relata_orfaos() {
  local arquivo pasta declarado k raiz
  local -A vistos=()
  for raiz in $SCAN_ROOTS; do
    [[ -d "$raiz" ]] || continue
    while IFS= read -r arquivo; do
      pasta=$(dirname "$arquivo")
      [[ -n "${vistos[$pasta]:-}" ]] && continue
      vistos[$pasta]=1
      [[ "$pasta" == "$CADDY_DIR" || "$pasta" == "$PIHOLE_DIR" ]] && continue
      [[ "$pasta" == "$QUARANTINE" || "$pasta" == "$QUARANTINE"/* ]] && continue
      declarado=0
      for k in "${KEYS[@]}"; do
        [[ "${DIR[$k]}" == "$pasta" ]] && declarado=1
      done
      [[ $declarado -eq 1 ]] && continue
      item "stack fora do env (nao sera tocada): $pasta"
    done < <(find "$raiz" -maxdepth 3 \( -name 'compose.yaml' -o -name 'compose.yml' -o -name 'docker-compose.yml' -o -name 'docker-compose.yaml' \) 2>/dev/null | sort)
  done
}

poda_containers() {
  local k projeto_nome presente
  while IFS= read -r k; do
    [[ -n "$k" ]] || continue
    [[ "${ANT_DIR[$k]}" == "-" ]] && continue
    projeto_nome=$(projeto_do_dir "${ANT_DIR[$k]}")
    presente=$(containers_do_dir "${ANT_DIR[$k]}" | paste -sd, -)
    if [[ -z "$presente" ]]; then
      item "containers de $k ja estao parados"
      continue
    fi
    if [[ ! -d "${ANT_DIR[$k]}" ]]; then
      aviso "$k saiu do env mas ${ANT_DIR[$k]} nao existe; pare os containers a mao"
      continue
    fi
    item "parando containers de $k (projeto '$projeto_nome'): $presente"
    ( cd "${ANT_DIR[$k]}" && docker compose -p "$projeto_nome" down ) ||
      erro "docker compose down falhou para $k"
  done < <(lista_removidas)
}

protegida() {
  local caminho=$1 p
  for p in "${PROTEGIDOS[@]}"; do
    [[ "$caminho" == "$p" ]] && return 0
  done
  return 1
}

poda_dados() {
  local k dir destino
  while IFS= read -r k; do
    [[ -n "$k" ]] || continue
    dir=${ANT_DIR[$k]}
    [[ "$dir" != "-" && -n "$dir" && -d "$dir" ]] || continue
    if protegida "$dir"; then
      aviso "$dir e caminho de infraestrutura; mover para quarentena exige acao manual"
      continue
    fi
    destino="$QUARANTINE/$k-$(date +%Y-%m-%d_%H%M%S)"
    confirma "mover $dir para $destino"
    mkdir -p "$QUARANTINE"
    chmod 0755 "$QUARANTINE"
    mv "$dir" "$destino" || erro "falhou mover $dir para $destino"
    item "quarentena: $dir -> $destino"
    item "revise e apague quando quiser; o script nao apaga pasta de app"
  done < <(lista_removidas)
}

confirma() {
  local msg=$1 resposta
  if [[ "$YES" -eq 1 ]]; then
    return 0
  fi
  [[ -t 0 ]] || erro "operacao destrutiva ($msg); repita com --yes"
  read -r -p "    $msg [s/N] " resposta
  [[ "$resposta" =~ ^[sSyY]$ ]] || erro "cancelado"
}

grava_estado() {
  local k dir tmp
  # O dry-run roda sem sudo e precisa ler o estado: nada aqui e segredo
  # (key/fqdn/upstream/dir), mas a pasta criada pelo root pode nascer 0700.
  mkdir -p "$(dirname "$APPS_STATE")"
  chmod 0755 "$(dirname "$APPS_STATE")" 2>/dev/null || true
  tmp=$(mktemp "$(dirname "$APPS_STATE")/.apps.XXXXXX")
  {
    echo "# Gerado por scripts/stacks/apps-sync.sh em $(date '+%Y-%m-%d %H:%M:%S')."
    echo "# key|fqdn|upstream|dir|flags aplicados na ultima execucao."
    for k in "${KEYS[@]}"; do
      echo "$k|${FQDN[$k]}|${UPSTREAM[$k]}|${DIR[$k]}|${FLAGS[$k]}"
    done
    # App que saiu do env continua no estado enquanto tiver container ou pasta:
    # e o que permite podar depois sem perder o rastro.
    while IFS= read -r k; do
      [[ -n "$k" ]] || continue
      dir=${ANT_DIR[$k]}
      if [[ "$dir" != "-" ]] && { [[ -n "$dir" && -d "$dir" ]] ||
         { tem_docker && [[ -n "$(containers_do_dir "$dir")" ]]; }; }; then
        echo "$k|${ANT_FQDN[$k]}|${ANT_UPSTREAM[$k]}|$dir|${ANT_FLAGS[$k]}"
      fi
    done < <(lista_removidas)
  } >"$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$APPS_STATE"
  item "estado gravado: $APPS_STATE"
}

# Entradas exatas no Pi-hole (Local DNS) vencem o DNS gerado: se o nome nao
# esta no env, a resolucao continua la ate alguem remover pela UI. O script
# nao edita esse arquivo: o Pi-hole o reescreve.
relata_dns_exatos() {
  local nome sobrando=0
  local escapado=${DOMAIN//./\\.}
  DNS_EXATOS=0
  if ! tem_docker || ! docker exec "$PIHOLE_CONTAINER" true >/dev/null 2>&1; then
    return 0
  fi
  while IFS= read -r nome; do
    [[ -n "$nome" ]] || continue
    declarado_fqdn "$nome" && continue
    item "Pi-hole ainda tem entrada exata para $nome (fora do env)"
    sobrando=1
  done < <(
    {
      docker exec "$PIHOLE_CONTAINER" grep -hoE "\"[^\"]*\.$escapado\"" \
        /etc/pihole/pihole.toml 2>/dev/null | tr -d '"' | awk '{print $NF}'
      docker exec "$PIHOLE_CONTAINER" cat /etc/pihole/hosts/custom.list 2>/dev/null |
        awk '{print $2}'
    } | grep -E "\.$escapado$" | sort -u
  )
  [[ $sobrando -eq 0 ]] ||
    item "essas entradas sao da UI do Pi-hole (Local DNS); remova a mao se quiser o DNS so pelo env"
  DNS_EXATOS=$sobrando
}

# --- Plano ----------------------------------------------------------------

mostra_plano() {
  local k removidas=0 geradas=0 manuais=0
  secao "plano (dry-run; use --apply para escrever)"
  item "env: $APPS_ENV"
  for k in "${KEYS[@]}"; do
    if e_manual "$k"; then
      manuais=$((manuais + 1))
      item "manual: $(endereco_site "$k") (bloco escrito a mao no Caddyfile; upstream ${UPSTREAM[$k]})"
    else
      geradas=$((geradas + 1))
      item "rota: $(endereco_site "$k") -> ${UPSTREAM[$k]}"
    fi
    [[ "${DIR[$k]}" == "-" || -d "${DIR[$k]}" ]] ||
      item "pasta ausente: ${DIR[$k]} (a rota ainda pode ser gerada)"
  done
  item "apps: ${#KEYS[@]} declaradas, $geradas geradas, $manuais manuais"
  mostra_atalhos_plano

  if [[ ${#ANT_KEYS[@]} -eq 0 ]]; then
    item "sem estado anterior em $APPS_STATE: nenhuma remocao sera feita nesta execucao"
  else
    while IFS= read -r k; do
      [[ -n "$k" ]] || continue
      removidas=$((removidas + 1))
      item "fora do env: $k (${ANT_FQDN[$k]}, ${ANT_DIR[$k]})"
    done < <(lista_removidas)
    [[ $removidas -eq 0 ]] || item "$removidas app(s) sairam do env: --prune-containers e --prune-data tratam delas"
  fi
  relata_containers
  relata_orfaos
  relata_dns_exatos
}

mostra_atalhos_plano() {
  local k painel=0 portal=0
  for k in "${KEYS[@]}"; do
    if atalho_inclui "$k" painel; then
      painel=$((painel + 1))
      item "atalho painel: $(nome_da_app "$k") -> $(url_da_app "$k")"
    fi
    atalho_inclui "$k" portal && portal=$((portal + 1))
  done
  if [[ -n "$PORTAL_INI" ]]; then
    item "atalhos: $painel no painel, $portal no portal"
  else
    item "atalhos: $painel no painel (este perfil nao tem portal)"
  fi
}

# --- Doctor ---------------------------------------------------------------
# Somente leitura: compara o declarado com o que esta no host e diz o que
# corrigir. Nunca escreve no env, no Caddyfile nem no estado.

doutor_erro() { ERROS_DOUTOR=$((ERROS_DOUTOR + 1)); item "erro: $*"; }
doutor_aviso() { AVISOS_DOUTOR=$((AVISOS_DOUTOR + 1)); item "aviso: $*"; }
doutor_ok() { item "ok: $*"; }

checa_caddy() {
  local k tmp nome outros
  if [[ ! -r "$CADDYFILE" ]]; then
    doutor_erro "Caddyfile ilegivel: $CADDYFILE"
    return 0
  fi
  if grep -qxF 'import apps.caddy' "$CADDYFILE"; then
    doutor_ok "$CADDYFILE importa apps.caddy"
  else
    doutor_erro "$CADDYFILE nao importa apps.caddy (rode --apply)"
  fi
  if grep -q '^# >>> apps-sync' "$CADDYFILE"; then
    doutor_erro "marcador antigo '# >>> apps-sync' no Caddyfile: apague o trecho, o modo inline nao existe mais"
  fi
  for k in "${KEYS[@]}"; do
    if e_manual "$k"; then
      nome=${FQDN[$k]//./\\.}
      grep -qE "^${nome}(:[0-9]+)?[[:space:]]*\{" "$CADDYFILE" ||
        doutor_erro "$k e manual mas nao tem bloco para ${FQDN[$k]} em $CADDYFILE"
    else
      conflito_no_caddyfile "${FQDN[$k]}" "$(endereco_site "$k")" &&
        ERROS_DOUTOR=$((ERROS_DOUTOR + 1))
      outros=$(snippet_da_app "$k")
      [[ -z "$outros" ]] ||
        { [[ -s "$(caminho_snippet "$outros")" ]] ||
          doutor_erro "$k: snippet '$outros' ausente em $(caminho_snippet "$outros")"; }
    fi
  done

  tmp=$(mktemp)
  gera_apps >"$tmp"
  if [[ ! -f "$CADDY_APPS" ]]; then
    doutor_erro "apps.caddy ausente: $CADDY_APPS (rode --apply)"
  elif cmp -s "$tmp" "$CADDY_APPS"; then
    doutor_ok "apps.caddy igual ao renderizado"
  else
    doutor_erro "apps.caddy diferente do renderizado (rode --apply)"
  fi
  rm -f "$tmp"

  if tem_docker && [[ -n "$(docker ps --format '{{.Names}}' | grep -xF "$CADDY_CONTAINER" || true)" ]]; then
    if caddy_validate; then
      doutor_ok "caddy validate"
    elif [[ ! -r "$CADDY_TOKEN_FILE" ]] && grep -q '{env\.' "$CADDYFILE"; then
      # Sem o token a validacao nao prova o bloco TLS; o --apply (root) le.
      doutor_aviso "validate sem $CADDY_TOKEN_FILE; rode --doctor com sudo para validar o TLS"
    else
      doutor_erro "caddy validate falhou (veja docker logs $CADDY_CONTAINER)"
    fi
  else
    doutor_aviso "container $CADDY_CONTAINER nao esta rodando; validate pulado"
  fi
}

checa_dns() {
  local k nome valor
  if [[ ! -r "$DNS_CONF" ]]; then
    doutor_erro "arquivo de DNS ausente: $DNS_CONF (rode --apply)"
    return 0
  fi
  if [[ "$DNS_MODE" == "wildcard" ]]; then
    grep -qxF "address=/$DOMAIN/$DNS_IP" "$DNS_CONF" &&
      doutor_ok "wildcard address=/$DOMAIN/$DNS_IP" ||
      doutor_erro "falta address=/$DOMAIN/$DNS_IP em $DNS_CONF"
  else
    for k in "${KEYS[@]}"; do
      grep -qxF "address=/${FQDN[$k]}/$DNS_IP" "$DNS_CONF" ||
        doutor_erro "falta address=/${FQDN[$k]}/$DNS_IP em $DNS_CONF"
    done
    while IFS= read -r nome; do
      [[ -n "$nome" ]] || continue
      declarado_fqdn "$nome" || doutor_erro "sobrando no arquivo de DNS: $nome (rode --apply)"
    done < <(sed -n 's#^address=/\([^/]*\)/.*#\1#p' "$DNS_CONF")
  fi

  if command -v dig >/dev/null 2>&1; then
    if [[ "$DNS_MODE" == "wildcard" ]]; then
      nome="sync-1.$DOMAIN"
    else
      nome=${FQDN[${KEYS[0]}]}
    fi
    valor=$(dig +short +time=2 +tries=1 "$nome" @"$DNS_QUERY_HOST" 2>/dev/null | head -1 || true)
    if [[ "$valor" == "$DNS_IP" ]]; then
      doutor_ok "DNS responde $nome -> $DNS_IP"
    else
      doutor_erro "DNS nao responde $nome com $DNS_IP (veio '${valor:-vazio}')"
    fi
  else
    doutor_aviso "dig ausente; consulta real ao Pi-hole pulada"
  fi

  relata_dns_exatos
  [[ "$DNS_EXATOS" -eq 0 ]] ||
    doutor_aviso "$DNS_EXATOS entrada(s) exata(s) no Pi-hole fora do env (limpe pela UI)"
}

checa_containers() {
  local k dir primeiro portas modo_rede host porta outro
  if ! tem_docker; then
    doutor_aviso "docker ausente; checks de container pulados"
    return 0
  fi
  for k in "${KEYS[@]}"; do
    dir=${DIR[$k]}
    host=${UPSTREAM[$k]%%:*}
    porta=${UPSTREAM[$k]##*:}
    if [[ "$dir" != "-" ]]; then
      if [[ ! -d "$dir" ]]; then
        doutor_erro "$k: pasta declarada e ausente: $dir"
      else
        primeiro=$(containers_do_dir "$dir" | head -1 || true)
        if [[ -z "$primeiro" ]]; then
          outro=$(docker ps -a \
            --filter "label=com.docker.compose.project=$(projeto "$dir")" \
            --format '{{.Label "com.docker.compose.project.working_dir"}}' 2>/dev/null |
            grep -vxF "$dir" | head -1 || true)
          if [[ -n "$outro" ]]; then
            doutor_erro "$k: container roda em $outro, o env declara $dir (corrija o dir)"
          else
            doutor_erro "$k: nenhum container na pasta $dir (suba com ./deploy.sh)"
          fi
        else
          modo_rede=$(docker inspect "$primeiro" --format '{{.HostConfig.NetworkMode}}' 2>/dev/null || true)
          portas=$(docker port "$primeiro" 2>/dev/null | sed 's/.*://' | sort -u | tr '\n' ' ')
          if [[ "$modo_rede" == "host" ]]; then
            doutor_ok "$k: $primeiro em host network; upstream ${UPSTREAM[$k]} conferido pela conexao"
          elif [[ -z "${portas// /}" ]]; then
            doutor_aviso "$k: $primeiro sem porta publicada (host network?); confira o upstream ${UPSTREAM[$k]}"
          elif [[ " $portas " != *" $porta "* ]]; then
            doutor_erro "$k: upstream ${UPSTREAM[$k]} mas $primeiro publica $portas"
          else
            doutor_ok "$k: upstream ${UPSTREAM[$k]} confere com $primeiro"
          fi
        fi
      fi
    fi
    if [[ "$TEST_MODE" == "1" ]]; then
      item "upstream: check TCP pulado (TEST_MODE=1)"
    elif timeout 2 bash -c "exec 3<>/dev/tcp/$host/$porta" 2>/dev/null; then
      doutor_ok "$k: $host:$porta aceita conexao"
    elif [[ "$host" == "localhost" || "$host" == "127.0.0.1" ]]; then
      doutor_erro "$k: upstream local $host:$porta recusou conexao"
    else
      doutor_aviso "$k: upstream remoto $host:$porta nao respondeu"
    fi
  done
}

checa_atalhos() {
  local tipo destino tmp
  for tipo in painel portal; do
    if [[ "$tipo" == "portal" ]]; then destino=$PORTAL_INI; else destino=$SERVICES_INI; fi
    [[ -n "$destino" ]] || continue
    if [[ ! -d "$(dirname "$destino")" ]]; then
      doutor_aviso "atalhos ($tipo): $(dirname "$destino") nao existe; nada e gerado"
      continue
    fi
    tmp=$(mktemp)
    render_atalhos "$tipo" >"$tmp"
    if [[ ! -f "$destino" ]]; then
      doutor_erro "atalhos ($tipo) ausente: $destino (rode --apply)"
    elif cmp -s "$tmp" "$destino"; then
      doutor_ok "atalhos ($tipo) iguais ao renderizado"
    else
      doutor_erro "atalhos ($tipo) diferente do renderizado: $destino (rode --apply)"
    fi
    rm -f "$tmp"
  done
}

checa_pastas() {
  local k qtd
  relata_orfaos
  if [[ -d "$QUARANTINE" ]]; then
    qtd=$(find "$QUARANTINE" -mindepth 1 -maxdepth 1 | wc -l)
    if [[ "$qtd" -eq 0 ]]; then
      doutor_ok "quarentena vazia: $QUARANTINE"
    else
      doutor_aviso "quarentena com $qtd item(ns): $QUARANTINE"
    fi
  fi
  while IFS= read -r k; do
    [[ -n "$k" ]] || continue
    doutor_erro "app fora do env e ainda no estado: $k (rode --apply para limpar)"
  done < <(lista_removidas)
}

doutor() {
  secao "env"
  item "arquivo: $APPS_ENV"
  item "snippets: $SNIPPETS_DIR"
  item "apps: ${#KEYS[@]} declaradas"

  secao "caddy"
  checa_caddy

  secao "dns"
  checa_dns

  secao "atalhos"
  checa_atalhos

  secao "containers e upstream"
  checa_containers

  secao "pastas"
  checa_pastas

  secao "resumo"
  item "erros: $ERROS_DOUTOR; avisos: $AVISOS_DOUTOR"
  [[ $ERROS_DOUTOR -eq 0 ]] || item "nada foi alterado: --apply corrige o que for gerado; o resto pede acao"
}

# --- Descobrir ------------------------------------------------------------
# Parte do host, nao do env: sugere linhas para stacks que ficaram de fora e
# aponta dir divergente. Nunca escreve: revisar e commitar e a aprovacao.

descobrir() {
  local nome dir porta chave fqdn k declarado outros sugeridas=0
  local -A vistos=()

  secao "apps declaradas (${#KEYS[@]})"
  for k in "${KEYS[@]}"; do
    item "$k ${FQDN[$k]} ${UPSTREAM[$k]} ${DIR[$k]}"
  done

  if ! tem_docker; then
    secao "stacks no host"
    aviso "docker ausente; nada a descobrir"
    return 0
  fi

  secao "candidatas: stacks no host fora do env"
  while IFS=$'\t' read -r nome _ dir; do
    [[ -n "$dir" && -z "${vistos[$dir]:-}" ]] || continue
    vistos[$dir]=1
    declarado=0
    for k in "${KEYS[@]}"; do
      [[ "${DIR[$k]}" == "$dir" ]] && declarado=1
    done
    [[ $declarado -eq 1 ]] && continue
    porta=$(docker port "$nome" 2>/dev/null | sed 's/.*://' | sort -u | head -1 || true)
    if [[ -z "$porta" ]]; then
      item "sem porta publicada (host network): $dir (container $nome) — informe o upstream"
      continue
    fi
    chave=$(printf '%s' "${dir##*/}" | tr '[:upper:]' '[:lower:]' |
      sed 's/[^a-z0-9]\+/-/g; s/^-//; s/-$//')
    if [[ -z "$chave" ]]; then
      item "$dir: nao consegui derivar uma key pelo nome da pasta"
      continue
    fi
    fqdn="$chave.$DOMAIN"
    item "$chave|$fqdn|127.0.0.1:$porta|$dir|"
    sugeridas=$((sugeridas + 1))
  done < <(docker ps -a --format '{{.Names}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.project.working_dir"}}')
  [[ $sugeridas -gt 0 ]] || item "nenhuma stack fora do env"

  secao "dir divergente (container em outra pasta)"
  for k in "${KEYS[@]}"; do
    [[ "${DIR[$k]}" == "-" ]] && continue
    [[ -z "$(containers_do_dir "${DIR[$k]}" | head -1 || true)" ]] || continue
    outros=$(docker ps -a \
      --filter "label=com.docker.compose.project=$(projeto "${DIR[$k]}")" \
      --format '{{.Label "com.docker.compose.project.working_dir"}}' 2>/dev/null |
      grep -vxF "${DIR[$k]}" | head -1 || true)
    [[ -z "$outros" ]] || item "$k: troque ${DIR[$k]} por $outros"
  done

  secao "resumo"
  item "$sugeridas sugestao(oes); nada foi escrito"
  item "revise e commite $APPS_ENV; depois --apply no host"
}

# --- Entrada --------------------------------------------------------------

[[ $DOUTOR -eq 1 && $APLICAR -eq 1 ]] && erro "--doctor nao combina com --apply: ele so le"
[[ $DESCOBRIR -eq 1 && $APLICAR -eq 1 ]] && erro "--descobrir nao combina com --apply: ele so le"

if [[ $PODAR_CONTAINERS -eq 1 || $PODAR_DADOS -eq 1 ]]; then
  [[ $APLICAR -eq 1 ]] || erro "--prune-containers/--prune-data exigem --apply"
fi
if [[ $PODAR_DADOS -eq 1 && $PODAR_CONTAINERS -eq 0 ]]; then
  erro "--prune-data exige --prune-containers: pare a app antes de mover a pasta"
fi

if [[ $APLICAR -eq 1 ]]; then
  if [[ $EUID -ne 0 && "$TEST_MODE" != "1" ]]; then
    erro "--apply precisa de root (sudo): escreve em $CADDY_DIR e em $APPS_STATE"
  fi
  tem_docker || erro "--apply precisa do docker no PATH"
  command -v dig >/dev/null 2>&1 || erro "--apply precisa do dig para confirmar o DNS"
fi

valida
le_estado

if [[ $DOUTOR -eq 1 ]]; then
  doutor
  [[ $ERROS_DOUTOR -eq 0 ]] || exit 1
  exit 0
fi

if [[ $DESCOBRIR -eq 1 ]]; then
  descobrir
  exit 0
fi

if [[ $APLICAR -eq 0 ]]; then
  mostra_plano
  exit 0
fi

secao "caddy"
aplica_caddy

secao "dns"
aplica_dns

secao "atalhos"
aplica_atalhos

if [[ $PODAR_CONTAINERS -eq 1 ]]; then
  secao "containers fora do env"
  poda_containers
fi

if [[ $PODAR_DADOS -eq 1 ]]; then
  secao "pastas fora do env (quarentena)"
  poda_dados
fi

secao "estado"
grava_estado

secao "dns do Pi-hole"
relata_dns_exatos

secao "resumo"
item "${#KEYS[@]} apps declaradas e aplicadas"
commit_env=$(git -C "$(dirname "$APPS_ENV")" rev-parse --short HEAD 2>/dev/null || true)
if [[ -n "$commit_env" ]]; then
  item "env: $APPS_ENV (commit $commit_env)"
else
  item "env: $APPS_ENV"
fi
item "Caddy: ${CADDYFILE}"
item "DNS: $DNS_CONF"

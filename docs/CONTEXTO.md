# Contexto — Homelab Storage Admin

Documento de retomada para quem chega sem contexto. Última atualização:
**2026-11-16**. Detalhe por área fica em `docs/` (mapa no fim); o histórico da
sessão de 27–29/10 está em [SESSAO-2026-10-29.md](SESSAO-2026-10-29.md).

## O que é

Painel Django que administra o NAS de um homelab: shares Samba, snapshots,
backups restic, discos/RAID/SMART, rede/UFW, containers, terminal e rotas do
Caddy. O mesmo código roda em dois hosts; o que muda entre eles está em
`hosts/<slug>/host.toml`.

| Host | Onde | Acesso |
|---|---|---|
| `pi` (Raspberry Pi 5) | `/opt/stacks/homelab-storage-admin`, `192.168.0.150:8060`, `https://homelab.conradhub.com` (Caddy + DNS Cloudflare) | `conrado@homelab.local`, sudo com senha |
| `moya` (moyaserver) | mesmo path, `127.0.0.1:8060` via Caddy em `moya-storage.local` | `conrado@10.72.60.181`, `sudo -n` |

- Código local (desktop Fedora): `/home/conradoalmeida/development/homelab-storage-admin`.
- Repositório: `https://github.com/ConradoAlmeida/homelab-storage-admin.git`
  (push direto em `main`; avisa bypass do check `test`).
- Em produção: `7bebca6` no moya, `/login/` 200 e `doctor moya` **0 erros/0
  avisos**. O Pi segue na versão anterior até um deploy próprio.
- Testes: `623 passed, 9 skipped` na VM (`moya`); **138 do Credenciais** e
  smoke com as 9 rotas em 200. No Windows restam falhas de plataforma
  (systemd/caminhos), cobertas pela VM.

## Regra: dados de apps no RAID/SSD (2026-11-16)

**Dado vivo de app nunca fica no disco de sistema.** No `moya`, tudo fica sob
`/mnt/data` (RAID): apps e bancos em `/mnt/data/apps/<slug>`, shares em
`/mnt/data/<share>` e Gitea em `/mnt/data/gitea`. No Pi, apps ficam em
`/mnt/nas/apps/<slug>` e shares em `/mnt/nas/<share>` (SSD/array), nunca no
microSD; `/mnt/jellyfin` é o disco de mídia, também fora do sistema. Um caminho
novo só é aceito se estiver em `hosts/<slug>/host.toml` e coberto pelo teste de
perfil.

Exceções explícitas: dumps do Gitea em `/var/backups/gitea` (moya) e estado do
Portal em `/var/lib/homelab-storage-admin`. O Pi-hole segue no SSD do Pi, fora
dos dados de apps.

No moya, os dados vivos de shares e apps saíram do disco de sistema e estão em
`/mnt/data`:

| O quê | Caminho |
|---|---|
| Shares Samba | `/mnt/data/print_files`, `cnc_files`, `kicad_lib`, `Production_Files`, `Veronte_Images` |
| Gitea | `/mnt/data/gitea` |
| Datasheets | `/mnt/data/apps/datasheets/data` (mídia em `data/media`) |
| Data Logger | `/mnt/data/apps/datalogger/data` |
| SharePoint | `/mnt/data/apps/sharepoint/data` |
| Drawing | `/mnt/data/apps/drawing/data` |
| Processos | `/mnt/data/apps/processos/data` |
| Credenciais | `/mnt/data/apps/credenciais/data` |
| Storage Admin | `/mnt/data/apps/storage/data` |

- O Docker tem `RequiresMountsFor=/mnt/data`; se o RAID não montar, ele não
  inicia em vez de subir apps com diretório vazio.
- `STORAGE_ROOT=/mnt/data`, `SNAPSHOT_ROOT=/mnt/data/.snapshots` e
  `ALLOWED_PATH_PREFIXES=/mnt/data/`.
- `/srv/samba` foi removido; os antigos dados ficaram em backups verificados em
  `/mnt/backup/apps-removidos-20261116` e `/mnt/backup/migracao-*`.
- Dumps do Gitea continuam em `/var/backups/gitea` (sistema), por decisão:
  separados do RAID e com espaço de sobra.
- **Portal e Pi-hole ficam no disco de sistema (decisão de 2026-11-16).** O
  estado do Portal é regenerável e o Pi-hole é infraestrutura de DNS; mover
  exigiria parada de DNS sem ganho de dados.
- O job local **Dados dos apps** foi atualizado para os novos caminhos; rodou
  com sucesso (208 MB). O job **Credenciais** também passou a apontar para o
  banco no RAID.
- **Reboot validado em 16/11:** `md0` montou, o Docker esperou `/mnt/data`,
  Samba/Gitea/Credenciais/Storage e demais apps subiram; health 200/302.

## Como funciona

- O container `homelab-storage-admin` **não tem root no host**: toda operação
  privilegiada passa pelo `homelab-storage-agent` (systemd, root, socket
  `/run/homelab-storage-admin/agent.sock`), que só aceita operações da
  allowlist. Nunca `shell=True`, comando livre ou caminho arbitrário.
- `hosts/<slug>/host.toml` é a fonte da verdade do host. `homelabctl render
  <slug> --write --ambos` gera `host.env` + `sync.env` em
  `/etc/homelab-storage-admin`; **não se edita o env no host**.
- `deploy/<slug>/apps.env` é a fonte das rotas: `scripts/stacks/apps-sync.sh`
  gera Caddy, DNS e atalhos. App nova = uma linha no env.
- UI é requisito: `static/css/ui.css` + kit Tailwind (`frontend/src.css` →
  `static/css/kit.css`, versionado). Página nova fora dos componentes quebra o
  padrão.
- No moya a identidade é do **Credenciais** (`CREDENTIALS_MANAGE_USERS=1`
  bloqueia toda a seção `/usuarios/`); no Pi o login é local.
- Jobs em produção: **Credenciais** (banco + `.env`, diário 03:30, 30 dias) e
  **Dados dos apps** (manual, sem timer).

## Comandos

```bash
uv sync --dev
uv run manage.py check
uv run pytest
uv run manage.py tailwind build      # depois de editar frontend/src.css

# bancada server-like (obrigatória neste desktop com virt-manager)
scripts/vm/bench.sh testar --perfil generico|homelab|moya --smoke --yes

# host: TOML -> env, preflight e unit de boot
python3 scripts/homelabctl.py check                  # valida + avisa drift do /etc
python3 scripts/homelabctl.py doctor <slug>          # preflight, sai 1 em erro
sudo python3 scripts/homelabctl.py bootstrap <slug> --escrever --apt
sudo python3 scripts/homelabctl.py render <slug> --write --ambos
python3 scripts/homelabctl.py boot <slug> --write
```

```bash
# no host (Pi ou moya): puxa main, build, /login/, --doctor
cd /opt/stacks/homelab-storage-admin && ./deploy.sh
# quando agent/ ou install-agent.sh mudou
sudo HOST_ENV_PROFILE=<slug> ./install-agent.sh
```

Diagnóstico: `systemctl status homelab-storage-agent`,
`docker logs homelab-storage-admin --tail 100` e, no compose,
`docker compose -f docker-compose.yml -f "$COMPOSE_OVERLAY" ps` (com o
`host.env` carregado).

> Deploy no Pi é decisão do dono: não execute sem pedido explícito.

## Regras que não podem ser quebradas

1. Código compartilhado Pi + moya: feature não se remove por host, use flag
   (`CREDENTIALS_MANAGE_USERS`) e gating por capability.
2. Nada de `500` por falta de recurso: esconda a ação e mostre o motivo.
3. Operação destrutiva exige confirmação; nunca apague repo restic, snapshot
   ou dados de share por ação de UI.
4. Backup só em disco externo; o wizard recusa sistema/dados e o job fica
   `skipped` (não falha) sem disco.
5. Agente só allowlist; containers só `start/stop/restart/logs` (nunca
   `rm`/`exec`/`prune`).
6. Pi-safe: recurso do Credenciais/Gitea ausente não pode gerar alerta falso.

A lista completa e os detalhes estão em `AGENTS.md`.

## O que está pronto

- Dashboard com blocos (Saúde, volumes, discos, snapshots, backups, shares) e
  páginas próprias para cada área.
- Samba: usuários/grupos, shares, senha, snapshots por share e navegador
  read-only de versões.
- Backups: restic por disco (agenda, retenção, verificação, unlock, restore),
  restore de snapshot, backup local de arquivos, Gitea (dump + USB + restore) e
  cópia fria USB.
- Discos/SMART standby-safe, RAID, métricas ao vivo; Rede com UFW editável.
- **UFW ativo no moya:** SSH, HTTP, DNS, Samba, Gitea (HTTP/SSH), apps
  publicados e descoberta WS-Discovery liberados; forward dos containers
  liberado para não quebrar o Docker.
- Sistema: host + apt, Configuração, chaves SSH, logs, serviços systemd,
  terminal no navegador e Admins locais (break-glass); Containers mostra
  stacks Compose, CPU/RAM ao vivo, sem remover nem executar; modo demo com
  `STORAGE_ADMIN_DEMO=1 DEBUG=1`.
- Host genérico: TOML com `schema`/defaults, `detect`/`init`, `render`,
  `doctor`, `bootstrap`, `boot`, CI (`bash -n` + `shellcheck`, arm64 só em
  push para `main`).

## Pendências / próximos jobs

1. **HD externo:** organizar a cópia fora do servidor; hoje os dumps do Gitea e
   os backups locais ficam no `sda`.
2. **Pi:** `host.env`/`sync.env` ainda precisam ser renderizados do `host.toml`
   e o deploy feito no Pi. Bloqueado em 16/11: o host não respondia na LAN
   (`192.168.0.150`); religar antes de `render pi --write --ambos` e
   `./deploy.sh`.
3. **Gitea:** dumps antigos no pendrive e cópia USB manual; a cópia automática
   foi decidida como "não".
4. Testes físicos de disco/USB (restic real, cópia fria) dependem de hardware.

## Armadilhas conhecidas

- Sem repo restic a UI mostra "aguardando disco"; `skipped` não é falha.
- Estado de disco `n/d` não é falha: controladora USB/RAID não responde ao
  `hdparm -C`/`smartctl -n standby`.
- `CREDENTIALS_MANAGE_USERS=1` bloqueia `/usuarios/` inteiro (pessoas, senha,
  grupos); storage continua no Storage Admin.
- Senha Samba ≠ senha Linux: no Pi a conta é `nologin` e só tem credencial
  Samba; no moya a igualdade vem de push do Credenciais.
- O overlay do Compose vem do `host.env`; sem ele o app fica fora da rede.
- O Docker depende de `/mnt/data` (`RequiresMountsFor`): se o RAID não montar,
  os apps não sobem. Confira `findmnt /mnt/data` antes de investigar app.
- No Pi, `data` é symlink para `/mnt/nas/apps/homelab-storage-admin/data`:
  num clone novo, recrie o symlink antes de rodar `manage.py`.
- Sessões do Credenciais são revalidadas a cada request.
- Não rode o app antigo `moya-storage-admin` junto com este.

## Onde ler mais

- `README.md` — índice do projeto.
- [INSTALACAO](INSTALACAO.md) — pré-requisitos, deploy, checklist, rollback, boot e variáveis.
- [PRESETS](PRESETS.md) — `host.toml`, schema, `homelabctl` e runbook de host novo.
- [ARQUITETURA](ARQUITETURA.md) — agente, allowlist, fluxo de dados.
- [ARMAZENAMENTO](ARMAZENAMENTO.md) · [BACKUPS](BACKUPS.md) · [REDE](REDE.md) · [SEGURANCA](SEGURANCA.md) · [SISTEMA](SISTEMA.md) · [ROTINAS](ROTINAS.md) · [TROUBLESHOOTING](TROUBLESHOOTING.md).
- [VM_TESTES](VM_TESTES.md) — bancada `linux2024` (`bench.sh`, snapshots por perfil).
- `AGENTS.md` — regras para agentes (ler antes de mexer).

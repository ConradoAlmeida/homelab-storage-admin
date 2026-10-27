# Homelab Storage Admin

Painel web para administrar o NAS do homelab (`homelab`, Raspberry Pi 5) sem
decorar comandos: usuários e grupos do Samba, shares, snapshots Btrfs ou rsync
e espaço em disco. O mesmo código atende o Pi, o moyaserver e um
Ubuntu+Samba via perfil de host.

> **Nunca comite `.env`.** Este repositório não contém senhas. A senha do admin
> é definida no `.env` do servidor (modo `600`) e trocada com
> `docker compose exec web python manage.py changepassword admin`.

---

## 1. O que ele faz

| Tarefa | Interface |
|---|---|
| Criar usuário Linux + Samba | Usuários → Novo usuário |
| Criar grupo Linux/Samba | Usuários → Novo grupo |
| Trocar senha do Samba | Usuários → Senha |
| Editar grupos | Usuários → Grupos |
| Ativar/desativar acesso | Usuários → botão Ativar/Desativar |
| Criar share no `smb.conf` | Shares → Novo share |
| Navegar histórico/snapshots | Histórico (`/history/`) — read-only |
| Ver temperatura/SMART dos discos | Discos (`/storage/`) — leitura sob demanda, standby-safe |
| Visão geral do host | Dashboard — sistema, todos os discos, volumes, RAID/Btrfs, backup e resumo de snapshots |
| Preparar disco de backup | Backups (`/backups/`) — wizard com confirmação extra |
| Consultar senha do restic | Backups → Credenciais — exige senha do app |
| Ver status de snapshot por share | Shares/Snapshots — sim (keep N) ou não configurado |

| Cadastrar jobs/periodicidade | Backups → Novo job / Editar |
| Cópia fria USB | Backups → Cópia fria (USB) — restic copy + check + eject |
| Ver versões de um arquivo | Histórico → arquivo → Versões |
| Share privado/oculto | Shares → Novo share → Privado (`browseable = no`) |
| Ver dados e snapshots | Dashboard / Shares |
| Criar/remover snapshot Btrfs | Snapshots |

O dashboard carrega primeiro o estado básico e busca os tamanhos dos shares
depois, em `/metrics/shares/`; assim o `du`/`btrfs du` não bloqueia o render.

Fora do escopo: Active Directory (o Samba é `tdbsam` standalone), autoatendimento
de senha, backup externo (use `restic` no host) e o **Jellyfin**. O Jellyfin tem
stack, bibliotecas, plugins, transcoding e config próprios em `/opt/stacks/jellyfin`;
este repo não instala, atualiza, configura nem faz backup dele. O dashboard só
mostra um atalho, e o share Samba `jellyfin` é gerenciado como share comum (sem
snapshot/restic).

---

## 2. Arquitetura

```
Navegador (LAN)
   |
   | HTTP :8060
   v
Container Docker "homelab-storage-admin"
  Django 5.2 + gunicorn, sem acesso ao host além do socket
   |
   | Unix socket /run/homelab-storage-admin/agent.sock (0660 root:root)
   v
homelab-storage-agent (systemd, root no host)
   |-- useradd / usermod / groupadd
   |-- pdbedit / smbpasswd
   |-- testparm + smbcontrol reload-config
   |-- btrfs subvolume snapshot -r / delete
   v
/etc/samba/smb.conf, /mnt/nas, /mnt/nas/.snapshots
```

O container **não** tem root no host, não monta `/etc/samba` e não executa shell.
Ele só pede operações conhecidas ao agente, que valida cada argumento.

### Perfis de host

O perfil fica em `/etc/homelab-storage-admin/host.env` e é lido pelo agente
(`EnvironmentFile` do systemd) e pelo `deploy.sh` (variáveis do Compose). O
`install-agent.sh` copia um exemplo **apenas se o arquivo não existir**; nunca
sobrescreve um perfil existente.

| Perfil | Exemplo | Overlay | Storage | Snapshots |
|---|---|---|---|---|
| Pi (default) | `host.env.example` | `docker-compose.homelab.yml` | `/mnt/nas` | `auto` (Btrfs no Pi) |
| moyaserver | `host.env.moya.example` | `docker-compose.moya.yml` | `/srv/samba` + `/mnt/data` | `rsync` |
| mínimo | sem Btrfs/restic | `docker-compose.yml` | conforme `host.env` | `none`/`rsync` |

Variáveis principais: `SITE_NAME`, `STORAGE_ROOT`, `SNAPSHOT_ROOT`,
`ALLOWED_PATH_PREFIXES`, `DF_MOUNTS`, `SHARE_OWNER`, `SNAPSHOT_DENYLIST`,
`SNAPSHOT_BACKEND=auto|btrfs|rsync|none`, `BACKUP_ROOT`, `AGENT_SOCKET`,
`BIND_ADDR`, `BIND_PORT`, `DATA_DIR`.

O agente detecta `btrfs`, `restic`, `smartctl`, `hdparm`, `mdadm`, fans e o
filesystem do `STORAGE_ROOT`. A UI esconde abas/botões quando o recurso não
existe; nada deve virar erro 500. O app **não gerencia** Cockpit, Pi-hole,
Caddy, DNS, Jellyfin ou o data-root do Docker. O Jellyfin é um vizinho: só
aparece como atalho no dashboard e como share Samba `jellyfin` (sem snapshot/restic).

No moyaserver, primeira instalação:

```bash
cd /opt/stacks/homelab-storage-admin
cp .env.example .env
chmod 600 .env
# edite .env: SECRET_KEY, senha do admin, ALLOWED_HOSTS e CSRF do moya
mkdir -p data
if [ ! -f data/services.ini ]; then
  cp services.ini.example data/services.ini   # edite a lista de atalhos
fi
sudo env HOST_ENV_PROFILE=moya ./install-agent.sh
./deploy.sh
```

O `deploy.sh` usa o `COMPOSE_OVERLAY` definido no `host.env`
(`docker-compose.moya.yml`). O bind fica em `127.0.0.1:8060`; publique com o
proxy que já existe no host.

> **No moyaserver:** o app antigo `moya-storage-admin` foi substituído em
> 2026-10-25. O novo app fica em `/opt/stacks/homelab-storage-admin`, com bind
> `127.0.0.1:8060`; o Caddy local publica em `moya-storage.local`. O repo/dados
> antigos foram preservados em `/home/conrado/documents/moya-storage-admin` e
> em backup; o agente antigo está desabilitado. Não rode os dois ao mesmo tempo.

### Atalhos de serviços (curadoria por host)

O dashboard **não descobre** serviços e **não faz health check**. Ele mostra
somente o que estiver no `services.ini` do host, em `DATA_DIR/services.ini`
(no Pi: `/mnt/nas/apps/homelab-storage-admin/data/services.ini`). O arquivo é
lido a cada request; editou, aparece sem restart.

Use `services.ini.example` como base:

```ini
[jellyfin]
name = Jellyfin
description = Midia · filmes e series
url = http://jellyfin.homelab.lan
icon = jellyfin
color = #a78bfa
order = 10
```

- `url` precisa ser `http://` ou `https://`; inválida é ignorada.
- `icon`: `jellyfin`, `cockpit`, `dockge`, `pihole` ou `generic`.
- `color`: hexadecimal `#rrggbb`; inválida cai no azul padrão.
- `order`: inteiro; menor aparece primeiro.
- Sem arquivo ou arquivo vazio: nenhum card é exibido.
- O moya escolhe a própria lista; o Pi mantém a lista atual.
- Não há descoberta automática, probe, health check ou criação de containers.

### Layout Btrfs

- `/mnt/nas` é o subvolume `@data` do array (RAID1 degradado + Btrfs).
- O container monta `/mnt/nas` **read-only** para o navegador de histórico; escritas continuam só pelo agente root.
- O app **não** acessa `/dev` nem roda `smartctl`/`hdparm`: o agente root expõe
  `storage_overview`, `storage_smart` e `storage_smart_test` via socket.
- O banco SQLite e os dados do app ficam em
  `/mnt/nas/apps/homelab-storage-admin/data` (bind mount), fora do microSD.
- Cada share que terá snapshots é um **subvolume Btrfs** próprio:
  `/mnt/nas/documentos`, `/mnt/nas/midia`, etc.
- Os snapshots ficam fora do share, em
  `/mnt/nas/.snapshots/<share>/@GMT-YYYY.MM.DD-HH.MM.SS`.
- O Samba usa `vfs objects = shadow_copy2` com `shadow:snapdir` apontando para
  esse diretório. No Windows, isso vira a aba **Versões anteriores**.

Se um share foi criado como diretório comum (sem snapshot), ele não pode ser
snapshotado pelo Btrfs. Recrie-o como subvolume com a opção de snapshot marcada.

---

## 3. Pré-requisitos no Pi

- Ubuntu Server 26.04.1 LTS (arm64), kernel com Btrfs e suporte ao HAT.
- Array montado em `/mnt/nas` (ver `HOMELAB.md`).
- Docker + Compose.
- Samba instalado: `sudo apt install samba samba-common-bin` (obrigatório).
- Opcionais: `btrfs-progs`, `restic`, `smartmontools`, `hdparm`, `mdadm`.
  Sem eles o install não aborta; o recurso correspondente é escondido.
- Usuário `conrado` com sudo e no grupo `docker`.
- `smbd` rodando: `sudo systemctl enable --now smbd`.

---

## 4. Deploy

### No PC (desenvolvimento)

```bash
cd ~/development/homelab-storage-admin
git add -A
git commit -m "mensagem"
git push origin main
```

O remoto é `https://github.com/ConradoAlmeida/homelab-storage-admin.git`.
Para push via SSH, use:

```bash
git remote set-url --push origin git@github.com:ConradoAlmeida/homelab-storage-admin.git
```

### No Pi

```bash
git clone https://github.com/ConradoAlmeida/homelab-storage-admin.git \
  /opt/stacks/homelab-storage-admin
cd /opt/stacks/homelab-storage-admin
cp .env.example .env
chmod 600 .env
# edite .env: SECRET_KEY, senha do admin, ALLOWED_HOSTS e CSRF
sudo ./install-agent.sh   # cria /etc/homelab-storage-admin/host.env se faltar
./deploy.sh               # usa host.env + COMPOSE_OVERLAY
```

Atualizações seguem sempre o mesmo fluxo: `git pull` + `./deploy.sh` no Pi.
O `deploy.sh` exige `/etc/homelab-storage-admin/host.env`; se ele não existir,
rode antes `sudo ./install-agent.sh`.

```bash
cd /opt/stacks/homelab-storage-admin
./deploy.sh
```

Se o agente mudou, o `deploy.sh` avisa; rode `sudo ./install-agent.sh`.

### Checklist de deploy seguro

Vale para Pi e moya. A ordem importa:

1. **Backup dos configs do host** (root):
   ```bash
   STAMP=$(date +%Y%m%d-%H%M)
   sudo tar -czf /root/homelab-pre-deploy-$STAMP.tgz \
     /etc/systemd/system/homelab-*.service \
     /etc/systemd/system/homelab-*.timer \
     /etc/samba/smb.conf \
     /opt/stacks/homelab-storage-admin/.env
   ```
2. **Perfil e agente**:
   - Pi: `sudo ./install-agent.sh`
   - Moya: `sudo env HOST_ENV_PROFILE=moya ./install-agent.sh`
   - O script cria `host.env` só se não existir; nunca sobrescreve.
3. **App**:
   ```bash
   ./deploy.sh
   ```
   O `deploy.sh` exige `host.env`, lê `COMPOSE_OVERLAY` e aborta se o overlay
   não existir.
4. **Atalhos** (opcional, sem restart):
   ```bash
   cp services.ini.example data/services.ini
   # edite data/services.ini
   ```
5. **Smoke**:
   ```bash
   sudo systemctl is-active homelab-storage-agent
   curl -fsS -o /dev/null -w '%{http_code}\n' http://192.168.0.150:8060/login/
   cd /opt/stacks/homelab-storage-admin
   set -a; . /etc/homelab-storage-admin/host.env; set +a
   docker compose -f docker-compose.yml -f "$COMPOSE_OVERLAY" ps
   docker compose -f docker-compose.yml -f "$COMPOSE_OVERLAY" logs --tail=80 web
   ```
   No moya, use `http://127.0.0.1:8060/login/`.

### Rollback

Se o smoke falhar:

```bash
cd /opt/stacks/homelab-storage-admin
git reset --hard <commit-anterior>
sudo ./install-agent.sh
set -a; . /etc/homelab-storage-admin/host.env; set +a
docker compose -f docker-compose.yml -f "$COMPOSE_OVERLAY" up -d --build
```

Se o problema for só unidade/Samba, restaure o tar do passo 1:

```bash
sudo tar -xzf /root/homelab-pre-deploy-<stamp>.tgz -C /
sudo systemctl daemon-reload
sudo systemctl restart homelab-storage-agent smbd
```

O rollback não mexe em `/mnt/nas`, snapshots, banco ou dados de share.

### Boot no Pi (`homelab-compose.service`)

A unidade de boot do Pi é específica do host e fica versionada em
`deploy/pi/homelab-compose.service`. Ela espera o IP `192.168.0.150` em
**qualquer interface** (Wi-Fi ou Ethernet) e sobe Pi-hole, o storage-admin,
Dockge e Caddy. A linha do storage-admin carrega
`/etc/homelab-storage-admin/host.env` e usa `COMPOSE_OVERLAY`.

Instalação/atualização:

```bash
sudo install -m 0644 deploy/pi/homelab-compose.service \
  /etc/systemd/system/homelab-compose.service
sudo systemctl daemon-reload
```

Ela não é instalada pelo `install-agent.sh` porque também inicia stacks de
terceiros (Pi-hole/Dockge/Caddy), que estão fora do escopo do app.

O banner de login do Pi também fica versionado:

```bash
sudo install -m 0644 deploy/pi/motd /etc/motd.d/cockpit
```

### Desenvolvimento local (uv)

O projeto usa **uv** e Python **3.12**; o `uv.lock` é versionado:

```bash
uv sync --dev
uv run manage.py migrate
uv run manage.py check
uv run pytest
uv run manage.py runserver 0.0.0.0:8000
```

A suíte normal roda sem root, sem Btrfs, sem Samba e sem hardware. Testes que
exigem loop devices/Btrfs real são marcados `lab` e devem rodar só em uma VM
descartável. O CI roda `manage.py check` + `pytest`.

O container também usa uv (`ghcr.io/astral-sh/uv`) e não tem `requirements.txt`.

> No host do Pi, `data` é um symlink para
> `/mnt/nas/apps/homelab-storage-admin/data`, então `uv run manage.py ...` usa o
> banco real. Se o symlink não existir num clone novo:
>
> ```bash
> mkdir -p /mnt/nas/apps/homelab-storage-admin/data
> ln -sfn /mnt/nas/apps/homelab-storage-admin/data data
> ```
>
> Alternativa: `DJANGO_SQLITE_PATH=/mnt/nas/apps/homelab-storage-admin/data/db.sqlite3 uv run manage.py ...`.
> O caminho recomendado para operações do dia a dia é dentro do container
> (`docker compose exec web ...`), que já enxerga o banco certo.

### Superusuário

O `entrypoint.sh` cria o usuário `admin` automaticamente a partir do `.env` na
primeira subida. Por isso, rodar `createsuperuser` com `admin` falha com
`That username is already taken`. Superusuários atuais no Pi: `admin` e
`conrado`. Para trocar a senha:

```bash
docker compose exec web python manage.py changepassword admin
```

Para criar outro superusuário:

```bash
docker compose exec -it web python manage.py createsuperuser --username outro
```

---

## 5. Variáveis do `.env`

| Variável | Exemplo | Função |
|---|---|---|
| `DJANGO_SECRET_KEY` | 64 hex | assinatura de sessão/CSRF |
| `DJANGO_DEBUG` | `0` | nunca `1` em produção |
| `DJANGO_ALLOWED_HOSTS` | `192.168.0.150,homelab,homelab.lan,storage.homelab.lan` | Host headers aceitos |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `http://storage.homelab.lan:8060,...` | origens confiáveis |
| `DJANGO_SUPERUSER_*` | admin / senha / e-mail | criado só se não existir |
| `DJANGO_SECURE_COOKIES` | `0` | `1` atrás de HTTPS |
| `DJANGO_SQLITE_PATH` | (vazio) | opcional; no host do Pi aponte para `/mnt/nas/apps/homelab-storage-admin/data/db.sqlite3` |
| `AGENT_SOCKET` | `/run/homelab-storage-admin/agent.sock` | socket do agente |

Gere a chave com `openssl rand -hex 32`.

### Perfil do host (`host.env`)

| Variável | Default do Pi | Função |
|---|---|---|
| `SITE_NAME` | `Homelab Storage` | nome na UI/admin |
| `STORAGE_ROOT` | `/mnt/nas` | raiz dos shares/volume principal |
| `SNAPSHOT_ROOT` | `/mnt/nas/.snapshots` | snapdir Btrfs |
| `ALLOWED_PATH_PREFIXES` | `/mnt/nas/` | prefixos aceitos (vírgula) |
| `DF_MOUNTS` | `/,/mnt/nas,/mnt/backup,/mnt/jellyfin` | mounts do `df` |
| `SHARE_OWNER` | `conrado` | dono dos shares |
| `SNAPSHOT_DENYLIST` | vazio | shares que nunca recebem snapshot |
| `SNAPSHOT_BACKEND` | `auto` | `auto`, `btrfs`, `rsync` ou `none` |
| `BACKUP_ROOT` | `/mnt/backup` | raiz dos discos restic |
| `AGENT_SOCKET` | `/run/homelab-storage-admin/agent.sock` | socket (não renomear) |
| `BIND_ADDR` / `BIND_PORT` | `192.168.0.150` / `8060` | bind do container |
| `COMPOSE_OVERLAY` | `docker-compose.homelab.yml` | overlay do deploy (moya usa `docker-compose.moya.yml`) |
| `DATA_DIR` | `/mnt/nas/apps/homelab-storage-admin/data` | banco/dados do app |

O unit `homelab-storage-agent.service` e o socket **não são renomeados**. O
`deploy.sh` carrega esse arquivo e usa o overlay do host.

---

## 6. Snapshots

- **Manual:** botão “Criar snapshot agora” na tela Snapshots.
- **Diário:** `homelab-storage-snapshot.timer` roda às 03:00 e cria um snapshot
  para cada share com política ativa.
- **Retenção:** campo `keep` da política (padrão 7).
- **Backend:** `auto` usa Btrfs quando o filesystem é Btrfs; senão usa `rsync`.
  `SNAPSHOT_BACKEND=btrfs|rsync|none` força o modo.
- **Btrfs:** snapdir em `SNAPSHOT_ROOT/<share>`, `btrfs subvolume snapshot -r`.
- **rsync:** snapdir em `<path>/.snapshots`, `rsync -aHAX --link-dest` com
  hardlinks; exclusão de `.snapshots` evita recursão.
- **Tamanho:** Btrfs usa `btrfs filesystem du` (aproximado por extents
  compartilhados). rsync usa live sem `.snapshots` + extra = `du(share) - live`.
- **Restauração:** copie do snapshot para o share ou use a aba Versões anteriores
  no Windows. Para rollback completo, pare o Samba e recrie o subvolume.

No backend Btrfs o agente exige que o share seja um subvolume e que
`STORAGE_ROOT` esteja montado; se o mount cair, ele aborta em vez de escrever no
microSD. No backend rsync não há essa exigência, mas o path precisa estar dentro
de um prefixo permitido.

---

### Histórico (read-only)

`/history/` navega os shares e snapshots `@GMT-...`:
- live e cada snapshot, com breadcrumb;
- lista de pastas/arquivos, paginação e download;
- “Versões” por arquivo, comparando live + snapshots;
- tudo somente leitura; restauração ainda não implementada.

O container precisa do `STORAGE_ROOT` montado read-only (no Pi, `/mnt/nas`;
no moya, `/srv/samba` e `/mnt/data`). O app não escreve nos dados por esse
caminho; qualquer escrita continua no agente root.

## 6.5 Discos e SMART

`/storage/` mostra:
- temperatura da CPU, fans/PWM (quando expostos), load e RAM;
- total/uso/livre somando os volumes monitorados e um cartão por volume;
- cada disco (`sda`, `sdb`, `sdd`, `mmcblk0`), modelo, serial, tamanho, montagem, uso e estado;
- temperatura **somente se o disco já estiver ativo**;
- RAID (`/proc/mdstat`, `mdadm --detail`) e Btrfs (usage, device stats, scrub).

A coleta é **diária** (`homelab-storage-metrics.timer`, 06:00) e fica em cache;
o dashboard e `/storage/` não executam `smartctl` no request. O botão
**Atualizar agora** força uma coleta. Disco em standby não é acordado.

Regras de standby:
- o agente usa `hdparm -C` para o estado e `smartctl -n standby` para temperatura/SMART;
- se o disco estiver em `standby`/`sleeping`, o comando retorna sem acordar;
- “Ler SMART” é um POST explícito e também respeita standby;
- testes **curto/longo** só por botão; o longo pede confirmação e pode demorar horas;
- a página não inicia teste nem SMART completo sozinha.
- No **Active Cooler oficial**, `0 rpm` com `PWM 0%` significa fan parado; a curva começa por volta de 50 °C. A UI mostra o zero explicitamente, em vez de “—”.

## 6.6 Backups — preparação de disco

`/backups/` começa pelo wizard de disco:
- lista discos com modelo, serial, tamanho, filesystem/label, montagem e se já há backup;
- recusa disco do sistema, membro de RAID, montado ou com holders;
- disco vazio pede `FORMATAR /dev/sdX`;
- disco com **filesystem existente** (mesmo vazio) pede **aviso extra** + `APAGAR /dev/sdX`;
- disco já configurado pede **aviso extra** + `RECONFIGURAR /dev/sdX`;
- o destino é mostrado como **ext4 (recomendado)**; nesta versão é fixo em ext4;
- sempre exige a senha do app;
- o agente revalida estado, frase e `allow_existing` antes de qualquer `wipefs`.

O wizard formata ext4, cria entrada no fstab por UUID, monta em
`/mnt/backup/<label>`, inicializa o restic e mostra a senha de recuperação.
A senha fica em arquivo root-only em `/etc/homelab-backup/secrets/` e também
pode ser consultada em **Backups → Credenciais**, mediante a senha do app
(com registro no audit log). O submit mostra um loading em tela cheia enquanto
formata/monta/inicializa; a requisição usa timeout de 900 s no Gunicorn.

O disco preparado fica registrado em `/etc/homelab-backup/config.json`; o
cadastro de jobs usa esse registro na seção 6.7.

## 6.7 Jobs de backup

`/backups/jobs/new/` e `/backups/jobs/<nome>/edit/` configuram:
- nome do job e disco de destino;
- fontes (shares) e exclusões (`--iexclude`, case-insensitive);
- exclusões **pré-preenchidas** com temporários, locks, downloads parciais e backups auxiliares de CAD/design (SolidWorks, Blender, FreeCAD, Inkscape, GIMP, Krita, AutoCAD, SketchUp, Rhino, InDesign); os arquivos reais não entram na lista; botão **Restaurar lista padrão**; `.snapshots` também fica de fora;
- periodicidade **diário**, **semanal** ou **mensal**, com horário;
- retenção diária/semanal/mensal;
- ativo/desativado.

Ao salvar, o agente grava o job em `/etc/homelab-backup/config.json` e cria/atualiza
um timer systemd `homelab-restic-backup-<job>.timer`. O serviço
`homelab-restic-backup@<job>.service` executa
`/usr/local/sbin/homelab-restic-backup <job>` como root.

O executor:
- valida mountpoint, repo e senha root-only;
- roda `restic backup` com as fontes e exclusões;
- aplica `forget --keep-daily/--keep-weekly/--keep-monthly --prune`;
- grava status em `/etc/homelab-backup/status/<job>.json` e log em
  `/var/log/homelab-restic/<job>.log`;
- usa cache do restic no próprio disco de backup (`.restic-cache`).

Na tela de jobs: **Rodar agora** (systemd, sem bloquear a requisição),
**Ativar/Desativar**, **Editar** e **Excluir** (o repositório restic é mantido).
A tabela mostra último status e próxima execução.

## 7. Samba

O app escreve seções no `/etc/samba/smb.conf`, roda `testparm -s` e recarrega
com `smbcontrol smbd reload-config`. Se a configuração for inválida, restaura o
backup `.bak-AAAAMMDD-HHMMSS`.

Cada share novo cria os grupos `<share>`, `<share>_ro` e `<share>_rw`, com
permissões `2775`. O dono padrão é `conrado` (ajustável em
`SHARE_OWNER` no service do agente). O checkbox **Privado** adiciona
`browseable = no`; a restrição real continua sendo o grupo `<share>_rw`
(adicione só o dono nele).

**Usuários → Novo grupo** cria um grupo Linux/Samba com nome validado e GID
opcional (1000–60000). O agente bloqueia grupos reservados, grupos existentes e
GIDs em uso; não há renomear/excluir pela UI.

Para gerenciar senhas Samba fora do app: `sudo smbpasswd -a usuario`.

---

## 8. Segurança

- Container escuta em `192.168.0.150:8060`, não em `0.0.0.0`.
- Acesso só na LAN. Para fora de casa, siga a seção 8.1: Cloudflare Tunnel com
  Access para o painel e Tailscale para SMB/DNS. Nunca publique a porta 8060.
- O agente roda como root, mas só expõe operações da allowlist em
  `agent/homelab-storage-agent.py`.
- O socket é `0660 root:root`; o container roda como root para acessá-lo. Se
  quiser endurecer, crie um grupo dedicado e rode o container com esse grupo.
- O README antigo do projeto `moya-storage-admin` continha uma senha real. Ela
  **não** foi trazida para este repositório; rotacione a senha no servidor antigo
  se ele ainda existir.

---

## 8.1 Acesso remoto

Fora de casa são duas necessidades diferentes, com duas ferramentas diferentes.
Não tente resolver as duas com o mesmo túnel.

| Necessidade | Ferramenta | Por quê |
|---|---|---|
| Painel e apps web (`:8060`, Jellyfin, Cockpit, Dockge) | Cloudflare Tunnel + Access | URL pública com HTTPS e MFA, sem abrir porta e sem cliente VPN |
| Arquivos (SMB) e nomes `.lan` | Tailscale (subnet router + split DNS) | SMB não trafega por HTTP; o Pi-hole precisa de rota até a LAN |

O `BIND_ADDR` continua `192.168.0.150`: o `cloudflared` roda no próprio Pi e
conecta em `http://192.168.0.150:8060` por dentro. Nenhum bind novo e nenhuma
porta publicada no roteador.

**No moyaserver** o perfil é outro: o bind é `127.0.0.1:8060` e quem publica é o
Caddy local. Se você montar túnel lá também, o `ingress` aponta para
`http://127.0.0.1:8060` (ou para o Caddy), nunca para o IP da LAN do Pi. Nada
nesta seção muda o deploy do moya.

### Cloudflare Tunnel (painel e apps)

Pré-requisito: a zona do domínio precisa estar na Cloudflare (nameservers
apontados para ela). *Public hostname* não existe em domínio fora da zona.

1. Instale o `cloudflared` (`.deb` oficial) e **desabilite a unit do pacote**
   para não rodar dois conectores no mesmo túnel:

```
sudo systemctl disable --now cloudflared
```

2. Crie o túnel e a rota DNS:

```
cloudflared tunnel login
cloudflared tunnel create homelab
cloudflared tunnel route dns homelab storage.seudominio.com
```

3. Crie o usuário, a config e o credentials:

```
sudo useradd --system --home-dir /var/lib/cloudflared --create-home \
  --shell /usr/sbin/nologin cloudflared
sudo install -d -o root -g cloudflared -m 0750 /etc/cloudflared
sudo install -o root -g cloudflared -m 0640 ~/.cloudflared/<UUID>.json /etc/cloudflared/
sudo install -o root -g cloudflared -m 0640 \
  deploy/pi/cloudflared-config.yml.example /etc/cloudflared/config.yml
sudoedit /etc/cloudflared/config.yml   # UUID, credentials-file e hostname
```

4. Suba a unit:

```
sudo install -m 0644 deploy/pi/homelab-cloudflared.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-cloudflared
```

5. **Access é obrigatório.** No Zero Trust → Access → Applications → Add
   self-hosted, aponte para `storage.seudominio.com` com policy `Allow` para o
   seu e-mail (One-time PIN) ou IdP. Sem isso o login do Django é a única
   barreira, e o app controla um agente root.

6. Acrescente o hostname ao `.env` e redeploy:

```
DJANGO_ALLOWED_HOSTS=...,storage.seudominio.com
DJANGO_CSRF_TRUSTED_ORIGINS=...,https://storage.seudominio.com
DJANGO_SECURE_COOKIES=1
```

O `SECURE_PROXY_SSL_HEADER` já está em `config/settings.py`, então o Django
reconhece o HTTPS terminado na Cloudflare. `BIND_ADDR` e overlay não mudam.

#### Cookies e HTTPS na LAN

`DJANGO_SECURE_COOKIES=1` marca o cookie como `Secure`: o navegador **para de
enviá-lo em `http://192.168.0.150:8060`** e o login pela LAN falha. Escolha uma:

| Opção | Efeito |
|---|---|
| Caddy do Pi na frente, com TLS interno (`https://storage.homelab.lan`) | LAN e WAN em HTTPS; instale o CA raiz do Caddy nos clientes |
| `DJANGO_SECURE_COOKIES=0` | LAN em HTTP volta a funcionar; o cookie só é cifrado na Cloudflare, não na LAN |
| Manter `1` e usar a LAN por IP só como emergência | simples, mas quebra o hábito de usar a LAN |

#### Limites da Cloudflare que afetam este app

- **Timeout de 100 s na borda** (free/Pro): o wizard **Backups → disco**
  (`timeout 900 s` no Gunicorn) estoura com **524** quando disparado pelo túnel.
  Rode esse passo pela LAN ou pelo Tailscale.
- **ToS 2.8:** o plano free não serve vídeo/arquivos grandes de forma
  desproporcional a HTML. **Jellyfin não deve ir por aqui.** Painel, `/history/`
  leve e downloads ocasionais, tudo bem.
- **100 MB por request** (free/Pro): upload por formulário acima disso falha.
- **Cloudflare fora do ar** deixa o painel inacessível. Mantenha o acesso por IP
  na LAN como fallback documentado.

### Tailscale (arquivos e DNS)

SMB continua sem passar por HTTP. Instale o Tailscale no Pi e use-o como **subnet
router**: os dispositivos passam a enxergar a `192.168.0.0/24` inteira, então
`BIND_ADDR`, `smb.conf` e `ALLOWED_HOSTS` não mudam.

```
echo 'net.ipv4.ip_forward = 1'          | sudo tee -a /etc/sysctl.d/99-tailscale.conf
echo 'net.ipv6.conf.all.forwarding = 1' | sudo tee -a /etc/sysctl.d/99-tailscale.conf
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf
sudo tailscale up --advertise-routes=192.168.0.0/24
```

Aprove a rota no admin console (**Machines → homelab → Edit route settings**).

DNS: **não** use o Pi-hole como resolver global ("Override local DNS") — se o Pi
cair, o celular fica sem internet. Use **split DNS**:

- Admin console → DNS → Nameservers → Add → Custom → `100.x.y.z` (IP Tailscale do Pi)
- **Restrict to domain** → `homelab.lan`

Assim só `*.homelab.lan` vai para o Pi-hole; o resto continua no DNS da rede onde
você estiver. O Pi-hole precisa aceitar query de fora das subnets locais:

- Pi-hole v6: **Settings → DNS**, responder em todas as origens.
- `ufw`: liberar `53` **na interface `tailscale0`**:

```
sudo ufw allow in on tailscale0 from 100.64.0.0/10 to any port 53 proto udp
sudo ufw allow in on tailscale0 from 100.64.0.0/10 to any port 53 proto tcp
```

Atenção ao conflito de faixa: `192.168.0.0/24` é o default de quase todo roteador
doméstico. Num Wi-Fi de terceiro que use a mesma faixa, a rota colide e o acesso
"desaparece". Nesse caso use o IP Tailscale do Pi (`100.x.y.z`) diretamente —
funciona sempre.

Desative a expiração de chave do nó do Pi no console; senão ele sai do tailnet
em ~180 dias e você perde o acesso remoto.

### Checklist de verificação

```
# tunnel no ar e rota criada
sudo systemctl status homelab-cloudflared
cloudflared tunnel info homelab

# app respondendo local (deve dar 302/200)
curl -fsS -o /dev/null -w '%{http_code}\n' http://192.168.0.150:8060/login/

# de fora: deve redirecionar para o login do Access, não direto para o Django
curl -sI https://storage.seudominio.com/login/ | head -5

# VPN e DNS
tailscale status
tailscale ping <celular>              # precisa dizer "direct", não "via DERP"
dig +short storage.homelab.lan @100.x.y.z
testparm -s | grep -iE 'interfaces|hosts allow'   # vazio = liberado para todos
```

No Windows 11, depois do Tailscale: `\\192.168.0.150\documentos`. No celular, iOS
em **Arquivos → Conectar ao servidor → `smb://192.168.0.150`**; Android com
qualquer cliente SMB.

Nunca: publicar `8060` no roteador, expor `445` na internet, usar *trycloudflare*
como endereço permanente ou apontar o Jellyfin para o túnel gratuito.

---

## 9. Troubleshooting

| Sintoma | Causa provável | Ação |
|---|---|---|
| “Agente indisponível” | serviço parado ou socket ausente | `sudo systemctl status homelab-storage-agent` |
| `ModuleNotFoundError: No module named 'django'` | rodou `python3 manage.py` no host, fora do venv/container | use `uv run manage.py ...` ou `docker compose exec web ...` |
| `attempt to write a readonly database` | rodou no diretório antigo `~/homelab-storage-admin` ou sem `DJANGO_SQLITE_PATH` | use `/opt/stacks/homelab-storage-admin` e o banco em `/mnt/nas/apps/...`; ou o container |
| `btrfs ... not a subvolume` | share criado como diretório comum | recriar com snapshot marcado |
| `/mnt/nas nao esta montado` | array não montado | `mount /mnt/nas` / conferir `fstab` |
| `testparm` falhou | seção inválida no `smb.conf` | o app restaura o backup; revisar o log |
| Versões anteriores vazias | `shadow_copy2`/`shadow:snapdir` errado | conferir a seção do share e reiniciar o `smbd` |
| `400 Bad Request` no domínio público | hostname fora de `DJANGO_ALLOWED_HOSTS` | acrescentar e rodar `./deploy.sh` |
| `CSRF verification failed` atrás do túnel | origem `https://` fora de `DJANGO_CSRF_TRUSTED_ORIGINS` | acrescentar `https://storage.seudominio.com` |
| Login ok fora de casa, falha na LAN | `DJANGO_SECURE_COOKIES=1` com acesso HTTP | ver 8.1, "Cookies e HTTPS na LAN" |
| `502` no `cloudflared` | `config.yml` aponta para `127.0.0.1` ou porta errada | `curl -I http://192.168.0.150:8060/login/` no Pi |
| `524` ao preparar disco de backup | wizard passa dos 100 s da borda da Cloudflare | rodar pela LAN ou pelo Tailscale (8.1) |
| `.lan` não resolve fora de casa | sem split DNS/Tailscale | ver 8.1 |
| SMB não conecta pelo celular | `hosts allow` no `[global]` ou Pi-hole recusando `100.64.0.0/10` | ver 8.1 |

Logs:

```bash
sudo journalctl -u homelab-storage-agent -n 50
sudo tail -50 /var/log/homelab-storage-agent.log
docker compose logs -f web
sudo journalctl -u homelab-cloudflared -n 50
```

---

## 10. Estrutura

```
homelab-storage-admin/
├── agent/
│   ├── homelab-storage-agent.py
│   ├── homelab-storage-agent.service
│   ├── homelab-storage-snapshot.py
│   ├── homelab-storage-snapshot.service
│   └── homelab-storage-snapshot.timer
├── config/            # settings Django (env)
├── core/              # views, forms, models, cliente do agente
├── history/           # navegador read-only de snapshots/versoes
├── storage/           # temperatura/estado/SMART sob demanda (standby-safe)
├── backups/           # wizard de disco + (proximo) jobs restic
├── templates/         # UI escura, sem dependências externas
├── deploy/pi/
│   ├── homelab-compose.service
│   ├── homelab-cloudflared.service
│   ├── cloudflared-config.yml.example
│   └── motd
├── docker-compose.yml
├── install-agent.sh
├── deploy.sh
└── .env.example
```

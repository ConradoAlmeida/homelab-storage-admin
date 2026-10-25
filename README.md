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

No moyaserver, instale o agente já com o perfil correto:

```bash
sudo env HOST_ENV_PROFILE=moya ./install-agent.sh
./deploy.sh
```

O `deploy.sh` usa o `COMPOSE_OVERLAY` definido no `host.env`
(`docker-compose.moya.yml`). O bind fica em `127.0.0.1:8060`; publique com o
proxy que já existe no host.

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
| `DF_MOUNTS` | `/,/mnt/nas,/mnt/backup` | mounts do `df` |
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
- cada disco (`sda`, `sdb`, `mmcblk0`), modelo, serial, tamanho, montagem e estado;
- temperatura **somente se o disco já estiver ativo**;
- RAID (`/proc/mdstat`, `mdadm --detail`) e Btrfs (usage, device stats, scrub).

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

Para gerenciar senhas Samba fora do app: `sudo smbpasswd -a usuario`.

---

## 8. Segurança

- Container escuta em `192.168.0.150:8060`, não em `0.0.0.0`.
- Acesso só na LAN; para fora de casa use Cloudflare Tunnel com Access, nunca
  publique a porta 8060.
- O agente roda como root, mas só expõe operações da allowlist em
  `agent/homelab-storage-agent.py`.
- O socket é `0660 root:root`; o container roda como root para acessá-lo. Se
  quiser endurecer, crie um grupo dedicado e rode o container com esse grupo.
- O README antigo do projeto `moya-storage-admin` continha uma senha real. Ela
  **não** foi trazida para este repositório; rotacione a senha no servidor antigo
  se ele ainda existir.

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

Logs:

```bash
sudo journalctl -u homelab-storage-agent -n 50
sudo tail -50 /var/log/homelab-storage-agent.log
docker compose logs -f web
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
├── docker-compose.yml
├── install-agent.sh
├── deploy.sh
└── .env.example
```

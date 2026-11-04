# Instalação e deploy

[← Voltar ao README](../README.md) · [Contexto](CONTEXTO.md) · [Arquitetura](ARQUITETURA.md) · [Segurança](SEGURANCA.md)

> Pré-requisitos, deploy no PC e no Pi, checklist, rollback, boot, desenvolvimento local e variáveis de ambiente.

---

## Pré-requisitos no Pi

- Ubuntu Server 26.04.1 LTS (arm64), kernel com Btrfs e suporte ao HAT.
- Array montado em `/mnt/nas` (ver [Layout Btrfs](ARQUITETURA.md#layout-btrfs)).
- Docker + Compose.
- Samba instalado: `sudo apt install samba samba-common-bin` (obrigatório).
- Opcionais: `btrfs-progs`, `restic`, `smartmontools`, `hdparm`, `mdadm`.
  Sem eles o install não aborta; o recurso correspondente é escondido.
- Usuário `conrado` com sudo e no grupo `docker`.
- `smbd` rodando: `sudo systemctl enable --now smbd`.

---

## Deploy

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

CSS do kit Tailwind: edite `frontend/src.css` e compile com
`uv run manage.py tailwind build`. O resultado `static/css/kit.css` entra no
commit; o container não baixa o CLI no `docker build`.

Para pré-visualizar a UI sem agente nem host (dados fictícios):

```bash
STORAGE_ADMIN_DEMO=1 DJANGO_DEBUG=1 uv run manage.py runserver 127.0.0.1:8000
```

O modo demo só liga com `DEBUG=1` e nunca deve ser usado em produção.

A suíte normal roda sem root, sem Btrfs, sem Samba e sem hardware. Testes que
exigem loop devices/Btrfs/restic reais são marcados `lab` e **entram na
bancada**: no desktop Fedora, rode-os na VM do virt-manager
(`docs/VM_TESTES.md`, `linux2024`). Só pule se este host não tiver
libvirt/virt-manager, e deixe isso explícito. O CI roda `manage.py check` +
`pytest` e **não** substitui a VM.

Na VM Ubuntu 26.04, a suíte roda **201 testes** (+ **5 lab**); no Windows,
**180** e os testes POSIX são pulados.

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

## Variáveis do `.env`

| Variável | Exemplo | Função |
|---|---|---|
| `DJANGO_SECRET_KEY` | 64 hex | assinatura de sessão/CSRF |
| `DJANGO_DEBUG` | `0` | nunca `1` em produção |
| `DJANGO_ALLOWED_HOSTS` | `192.168.0.150,homelab,conradhub.lan,storage.conradhub.lan` (aliases `homelab.lan` ainda listados) | Host headers aceitos |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `http://storage.conradhub.lan,...` | origens confiáveis |
| `DJANGO_SUPERUSER_*` | admin / senha / e-mail | criado só se não existir |
| `DJANGO_SECURE_COOKIES` | `0` | `1` atrás de HTTPS |
| `DJANGO_SQLITE_PATH` | (vazio) | opcional; no host do Pi aponte para `/mnt/nas/apps/homelab-storage-admin/data/db.sqlite3` |
| `AGENT_SOCKET` | `/run/homelab-storage-admin/agent.sock` | socket do agente |

Gere a chave com `openssl rand -hex 32`.

### Perfil do host (`host.env`)

No homelab, a tela de entrada centraliza a casa, menor, e o nome Conrado Homelab, um pouco maior, os dois em roxo. A barra repete essa marca: a casa como ícone e o mesmo nome. Os ícones do navegador usam só a casa. No moya, com `CREDENTIALS_MANAGE_USERS=1`, permanece o wordmark Moya.

| Variável | Default do Pi | Função |
|---|---|---|
| `SITE_NAME` | `Homelab Storage` | nome na UI/admin, abaixo da marca |
| `STORAGE_ROOT` | `/mnt/nas` | raiz dos shares/volume principal |
| `JELLYFIN_ROOT` | `/mnt/jellyfin` | mídia Jellyfin read-only (sem snapshot/restic) |
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
| `DOWNLOAD_DIR` | `DATA_DIR/downloads` | arquivos temporários baixados do restic |
| `TORRENT_API_TOKEN` | vazio | Primeiro token da API, se o banco ainda não tiver um. Depois a página Torrents é quem troca |
| `CREDENCIAIS_DB` | `/home/conrado/moya_credenciais_app/data/db.sqlite3` | banco do Credenciais (moya) |
| `CREDENCIAIS_ENV` | `/home/conrado/moya_credenciais_app/.env` | `.env` do Credenciais (moya) |
| `CREDENCIAIS_BACKUP_DIR` | `/var/backups/moya-credenciais` | destino dos arquivos, `700 root:root` |
| `CREDENCIAIS_CONTAINER` | `moya-credenciais` | container reiniciado após restauração |
| `CREDENCIAIS_TIME` | `03:30` | horário do timer diário |
| `CREDENCIAIS_RETENTION_DAYS` | `30` | retenção em dias |

O unit `homelab-storage-agent.service` e o socket **não são renomeados**. O
`deploy.sh` carrega esse arquivo e usa o overlay do host.

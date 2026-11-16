# Instalação e deploy

[← Voltar ao README](../README.md) · [Contexto](CONTEXTO.md) · [Arquitetura](ARQUITETURA.md) · [Segurança](SEGURANCA.md)

> Pré-requisitos, deploy, checklist, rollback, boot, desenvolvimento local e variáveis de ambiente.

O código é o mesmo para qualquer Ubuntu Server. O que muda entre hosts está em
`hosts/<slug>/host.toml` — os presets `pi` e `moya` e o fluxo de host novo
estão em [Hosts e presets](PRESETS.md).

---

## Pré-requisitos

- Ubuntu Server (amd64 ou arm64) com Docker + Compose.
- Python 3.11+ (`tomllib`) para o `homelabctl`; o app roda em 3.12.
- O disco dos dados montado e um disco externo para backup (nunca o mesmo).
- Samba só se `samba = true`: `sudo apt install samba samba-common-bin`
  (`smbd` habilitado). Ferramentas de disco só se `discos = true`:
  `sudo apt install parted e2fsprogs`.
- Opcionais por feature: `btrfs-progs`, `restic`, `smartmontools`, `hdparm`,
  `mdadm`, `ufw`. Sem eles o install avisa e o recurso é escondido na UI;
  `homelabctl requisitos <slug>` diz o que falta e o pacote.
- Usuário com sudo e no grupo `docker`.

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

### No host

```bash
git clone https://github.com/ConradoAlmeida/homelab-storage-admin.git \
  /opt/stacks/homelab-storage-admin
cd /opt/stacks/homelab-storage-admin
python3 scripts/homelabctl.py bootstrap <slug>          # dry-run: o que falta
sudo python3 scripts/homelabctl.py bootstrap <slug> --escrever --apt
sudo HOST_ENV_PROFILE=<slug> ./install-agent.sh          # gera o que faltar
python3 scripts/homelabctl.py doctor <slug>              # 0 erros antes do deploy
./deploy.sh                                              # usa host.env + COMPOSE_OVERLAY
```

O `bootstrap` grava `host.env` e `sync.env`, cria o `.env` a partir do
`.env.example` com segredo aleatório em modo `600` e instala os pacotes das
features obrigatórias; ele nunca sobrescreve arquivo existente — para aplicar
mudança de TOML num host já instalado é `render <slug> --write --ambos`. O
`.env` gerado traz `ALLOWED_HOSTS`/`CSRF` do `lan_ip` e um segredo aleatório;
revise o usuário admin no primeiro acesso. Host sem TOML: `homelabctl init`
([PRESETS](PRESETS.md)).

### Apps e rotas (Caddy + DNS)

O perfil vem do `HOST_PROFILE` do `host.env` e as diferenças (domínio, TLS,
DNS, caminhos) do `sync.env`; os dois são gerados do `host.toml`. Cada host tem
seu `deploy/<slug>/apps.env` versionado, é a fonte da verdade das rotas:

```bash
sudo scripts/stacks/apps-sync.sh            # dry-run: mostra o plano
sudo scripts/stacks/apps-sync.sh --apply    # gera apps.caddy + DNS
scripts/stacks/apps-sync.sh --doctor        # só lê: o que diverge?
scripts/stacks/apps-sync.sh --descobrir     # só lê: stacks fora do env
```

O `--perfil <slug>` continua aceito (e a tela de Configuração mostra o comando
certo); sem ele vale o `HOST_PROFILE`. Host sem Caddy (`upstream = "nenhum"`)
ou sem DNS (`dns_modo = "nenhum"`) roda o `--apply` só para atalhos e estado.

App nova, redirect e bloco especial são linhas no `apps.env` (flags `redir=` e
`snippet=`, fragmentos em `deploy/<slug>/snippets/`); nada é editado à mão no
Caddyfile do host.

O stack do Caddy precisa montar a pasta (uma vez, no `compose.yaml` dele), no
lugar dos mounts de `Caddyfile` e `cloudflare.token`:

```yaml
volumes:
  - ./:/etc/caddy:ro
```

A pasta montada evita o problema de o arquivo gerado ainda não existir na
primeira subida do container.

Sem `--apply` nada é escrito. Depois de remover uma linha do `apps.env`, o
`--apply` sozinho não para containers nem mexe em pasta: use
`--prune-containers` e `--prune-data` (quarentena em
`/opt/stacks/_removidos/`).

### Diferenças por host

O preset `pi` usa TLS pelo Cloudflare e wildcard no Pi-hole; o `moya` usa
HTTP:80 e DNS por nome. Os dois estão em [Hosts e presets](PRESETS.md) — aqui
fica só o que vale para todos: `APPS_ENV_PATH` aponta para
`<repo>/deploy/<slug>/apps.env`, e a página Configuração mostra o comando com
`--perfil <slug>` quando o host não é o `pi`.

Atualizações seguem sempre o mesmo fluxo: `git pull` + `./deploy.sh` no host.
O `deploy.sh` exige `/etc/homelab-storage-admin/host.env`; se ele não existir,
rode antes `sudo ./install-agent.sh`. Ele também exige o `.env` do clone com
modo `600` e `DJANGO_SECRET_KEY` que não seja a de exemplo, e acesso ao Docker
pelo usuário (`docker info`); sem isso, aborta com o comando de correção antes
de mexer em qualquer coisa. Depois de mudar o `host.toml`, rode
`sudo python3 scripts/homelabctl.py render <slug> --write --ambos` — o
`doctor` acusa o env fora de sync e o deploy falha até corrigir.

```bash
cd /opt/stacks/homelab-storage-admin
./deploy.sh
```

Se o agente mudou, o `deploy.sh` avisa **antes** do `docker compose up`; rode
`sudo ./install-agent.sh`. A comparação cobre os quatro binários e as units que
o `install-agent.sh` instala (menos o timer de snapshots, que o agente reescreve
conforme a agenda). A configuração inicial do qBittorrent e o passo de UPnP
viram aviso, não falha: o app já está no ar quando eles rodam.

### Checklist de deploy seguro

Vale para qualquer host. A ordem importa:

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
   ```bash
   sudo HOST_ENV_PROFILE=<slug> ./install-agent.sh
   python3 scripts/homelabctl.py doctor <slug>
   ```
   O perfil vem de `HOST_ENV_PROFILE` ou do `HOST_PROFILE` do `host.env`; sem
   `hosts/<slug>/host.toml` o script para. Ele cria `host.env`/`sync.env` só
   se não existirem e nunca sobrescreve. O `doctor` lista, sem escrever, env
   fora de sync, dependências, `.env`, mounts, `apps.env` e unit de boot
   (`erros: 0` antes de seguir).
3. **App**:
   ```bash
   ./deploy.sh
   ```
   O `deploy.sh` exige `host.env`, lê `COMPOSE_OVERLAY` (vazio usa só o
   `docker-compose.yml`) e aborta se o overlay declarado não existir. Ele
   termina conferindo `/login/` no endereço de `BIND_ADDR`:
   sem resposta em 90 s, sai 1 com o comando de `logs`. Se o `apps.env` for
   mais novo que o estado do `--apply`, avisa e mostra o comando do perfil. No
   fim roda o `--doctor` (sem sudo): erro de rota/DNS/atalho **derruba o
   deploy** (o app está no ar, mas o host não está no estado do env); aviso,
   como o token da Cloudflare sem sudo, só informa.
4. **Atalhos** (opcional, sem restart): saem do `deploy/<slug>/apps.env`
   (`atalho=painel`), não de um arquivo copiado à mão.
   ```bash
   sudo scripts/stacks/apps-sync.sh --apply   # gera Caddy, DNS e services.ini
   ```
   `services.ini.example` fica só como referência do formato da INI gerada.
5. **Smoke**:
   ```bash
   sudo systemctl is-active homelab-storage-agent
   curl -fsS -o /dev/null -w '%{http_code}\n' http://<BIND_ADDR>:8060/login/
   cd /opt/stacks/homelab-storage-admin
   set -a; . /etc/homelab-storage-admin/host.env; set +a
   docker compose -f docker-compose.yml -f "$COMPOSE_OVERLAY" ps
   docker compose -f docker-compose.yml -f "$COMPOSE_OVERLAY" logs --tail=80 web
   ```
   Se `BIND_ADDR` for `127.0.0.1`, rode o curl no próprio host.

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

### Boot do preset `pi` (`homelab-compose.service`)

A unidade de boot do Pi é específica daquele host e fica versionada em
`deploy/pi/homelab-compose.service`. Ela espera o IP do preset em **qualquer
interface** (Wi-Fi ou Ethernet) e sobe Pi-hole, o storage-admin, Dockge e
Caddy. A linha do storage-admin carrega
`/etc/homelab-storage-admin/host.env` e usa `COMPOSE_OVERLAY`. Host novo sem
stacks de terceiros não precisa dela.

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
sudo install -m 0644 deploy/pi/motd /etc/motd.d/homelab-storage
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
commit; o container não baixa o CLI no `docker build`. Tokens e componentes
compartilhados ficam em `static/vendor/moya-ui/` e são atualizados a partir do
`moya_art_design` (`scripts/sync-ui.py --apps homelab-storage-admin`).

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
| `DJANGO_ALLOWED_HOSTS` | `192.168.0.150,homelab,homelab.conradhub.com` | Host headers aceitos |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://homelab.conradhub.com,...` | origens confiáveis |
| `DJANGO_SUPERUSER_*` | admin / senha / e-mail | criado só se não existir |
| `DJANGO_SECURE_COOKIES` | `0` no exemplo | `1` quando o mesmo `https://homelab.conradhub.com` vale em casa e no Tailscale. No Pi já está `1` desde o `./deploy.sh` de 2026-11-04. `http://192.168.0.150:8060` abre e não mantém sessão |
| `DJANGO_SQLITE_PATH` | (vazio) | opcional; no host do Pi aponte para `/mnt/nas/apps/homelab-storage-admin/data/db.sqlite3` |
| `AGENT_SOCKET` | `/run/homelab-storage-admin/agent.sock` | socket do agente |

Gere a chave com `openssl rand -hex 32`. Fora de casa o acesso é o Tailscale;
os nomes não têm DNS público. Ver [Nomes](REDE.md#nomes).

### Perfil do host (`host.env`)

O `host.env` é **gerado** de `hosts/<slug>/host.toml` por
`homelabctl render <slug> --write`. A tabela abaixo documenta as chaves
(resultado no preset `pi`); a fonte da verdade é o TOML.

No homelab, a tela de entrada mostra o wordmark vertical Conradhub Homelab. A barra usa o símbolo com CONRADHUB e a linha HOMELAB. Os ícones do navegador vêm desse pacote. No moya, com `CREDENTIALS_MANAGE_USERS=1`, permanece o wordmark Moya.

| Variável | Default do preset `pi` | Função |
|---|---|---|
| `HOST_PROFILE` | `pi` | slug do host; é ele que a UI usa para montar o `--perfil` e que o `apps-sync` lê sem flag |
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
| `COMPOSE_OVERLAY` | `docker-compose.homelab.yml` | overlay do deploy; vazio usa só o `docker-compose.yml` (moya usa `docker-compose.moya.yml`) |
| `APPS_ENV_PATH` | `/opt/stacks/homelab-storage-admin/deploy/<slug>/apps.env` | fonte das rotas, do DNS e dos atalhos (mostrada em Configuração); vazio esconde a linha |
| `APPS_ENV_FILE` | `deploy/<slug>/apps.env` dentro do container | leitura da página Rotas e atalhos (`./deploy` montado read-only) |
| `APPS_STATE_FILE` | `/var/lib/homelab-storage-admin/apps.aplicados` | estado do último `--apply`, usado para dizer o que está aplicado |
| `APPS_SCHEME` | `https` (Pi) / `http` (moya, no overlay) | esquema das rotas exibidas |
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

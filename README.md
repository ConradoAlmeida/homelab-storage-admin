# Homelab Storage Admin

Painel web para administrar o NAS do homelab (`homelab`, Raspberry Pi 5) sem
decorar comandos: usuários e grupos do Samba, shares, snapshots Btrfs e espaço
em disco.

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
| Ver versões de um arquivo | Histórico → arquivo → Versões |
| Share privado/oculto | Shares → Novo share → Privado (`browseable = no`) |
| Ver dados e snapshots | Dashboard / Shares |
| Criar/remover snapshot Btrfs | Snapshots |

Fora do escopo: Active Directory (o Samba é `tdbsam` standalone), autoatendimento
de senha e backup externo (use `restic` no host).

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

### Layout Btrfs

- `/mnt/nas` é o subvolume `@data` do array (RAID1 degradado + Btrfs).
- O container monta `/mnt/nas` **read-only** para o navegador de histórico; escritas continuam só pelo agente root.
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
- Samba instalado: `sudo apt install samba samba-common-bin btrfs-progs`.
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
docker compose up -d --build
sudo ./install-agent.sh
```

Atualizações seguem sempre o mesmo fluxo: `git pull` + `./deploy.sh` no Pi.

```bash
cd /opt/stacks/homelab-storage-admin
./deploy.sh
```

Se o agente mudou, o `deploy.sh` avisa; rode `sudo ./install-agent.sh`.

### Desenvolvimento local (uv)

O projeto usa **uv** e Python **3.12**; o `uv.lock` é versionado:

```bash
uv sync
uv run manage.py migrate
uv run manage.py check
uv run manage.py runserver 0.0.0.0:8000
```

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

---

## 6. Snapshots

- **Manual:** botão “Criar snapshot agora” na tela Snapshots.
- **Diário:** `homelab-storage-snapshot.timer` roda às 03:00 e cria um snapshot
  para cada share com política ativa.
- **Retenção:** campo `keep` da política (padrão 7).
- **Tamanho:** `btrfs filesystem du` é aproximado, porque snapshots compartilham
  extents. O número no dashboard é uma referência, não a soma exata.
- **Restauração:** copie do snapshot para o share ou use a aba Versões anteriores
  no Windows. Para rollback completo, pare o Samba e recrie o subvolume.

O agente exige que o share seja um subvolume Btrfs e que `/mnt/nas` esteja
montado; se o mount cair, ele aborta em vez de escrever no microSD.

---

### Histórico (read-only)

`/history/` navega os shares e snapshots `@GMT-...`:
- live e cada snapshot, com breadcrumb;
- lista de pastas/arquivos, paginação e download;
- “Versões” por arquivo, comparando live + snapshots;
- tudo somente leitura; restauração ainda não implementada.

O container precisa de `/mnt/nas` montado read-only. O app não escreve nos dados
por esse caminho; qualquer escrita continua no agente root.

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
├── templates/         # UI escura, sem dependências externas
├── docker-compose.yml
├── install-agent.sh
├── deploy.sh
└── .env.example
```

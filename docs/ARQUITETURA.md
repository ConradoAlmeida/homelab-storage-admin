# Arquitetura e código

[← Voltar ao README](../README.md) · [Contexto](CONTEXTO.md) · [Instalação](INSTALACAO.md) · [Armazenamento](ARMAZENAMENTO.md)

> Desenho do container e do agente, perfis de host, layout Btrfs, estrutura do repositório, UI e login pelo Credenciais.

---

## Desenho geral

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
`BIND_ADDR`, `BIND_PORT`, `DATA_DIR`, `FIREWALL_MANAGE=0|1`,
`FIREWALL_SAFE_PORTS=22/tcp,53/tcp,53/udp,80/tcp,443/tcp,8060/tcp,137/udp,138/udp,139/tcp,445/tcp`.
No perfil do Pi, o exemplo também inclui `5001/tcp` (Dockge) e `8080/tcp`
(web do Pi-hole); só entram se estiverem em uso público no momento da ativação.

O agente detecta `btrfs`, `restic`, `smartctl`, `hdparm`, `mdadm`, fans e o
filesystem do `STORAGE_ROOT`. A UI esconde abas/botões quando o recurso não
existe; nada deve virar erro 500. O app **não gerencia** Cockpit, Pi-hole,
Caddy, DNS, a configuração do Jellyfin ou o data-root do Docker. No Pi o
navegador usa `https://homelab.conradhub.com`; o Caddy (`homelab-caddy:2`,
`/opt/stacks/caddy`) termina o TLS. Fora de casa só o Tailscale. Detalhe em
[Nomes](REDE.md#nomes). O Jellyfin é um vizinho: atalho no dashboard, share
Samba `jellyfin` (sem snapshot/restic) e, se o container existir, downloads
por magnet para as pastas das bibliotecas.

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
url = https://jellyfin.conradhub.com
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
- Cada share no Btrfs é um **subvolume** próprio (`/mnt/nas/documentos`, etc.),
  mesmo quando nasce sem política de versões; a política pode ser ligada depois.
- Os snapshots ficam fora do share, em
  `/mnt/nas/.snapshots/<share>/@GMT-YYYY.MM.DD-HH.MM.SS`.
- O Samba usa `vfs objects = shadow_copy2` com `shadow:snapdir` apontando para
  esse diretório. No Windows, isso vira a aba **Versões anteriores**.

Shares antigos que ainda são diretório comum só viram subvolume quando a
política de snapshot é ativada com confirmação explícita do nome do share.

## Estrutura do repositório

### Sistema de UI

A consistência visual é requisito, não preferência. Todas as páginas usam os
mesmos componentes de `static/css/ui.css` (carregado depois de `app.css`).
O kit Tailwind (`frontend/src.css` → `static/css/kit.css`) entra por último e,
neste piloto, acrescenta layout da lista de usuários (`person-id`,
`group-strip`, `table-fit`) e da página Torrents (`torrent-page`). Sem npm: `uv add django-tailwind-cli` e
`uv run manage.py tailwind build`. A folha compilada vai no Git para o
`collectstatic` do Pi/moya não baixar o CLI.

| Componente | Uso |
|---|---|
| `page-head` | título, lead e ações da página |
| `section` + `section-head` | blocos e subtítulos |
| `card` | conteúdo agrupado |
| `alert` (`danger`, `warn`, `ok`) | avisos e estados |
| `btn` (`primary`, `danger`, `small`) | ações |
| `table-wrap` + `table` | listas |
| `tag` / `badge` | estados |
| `metric-grid` + `metric` | números |
| `action-grid` + `action-card` | atalhos grandes |
| `form-grid`, `form-group`, `form-control`, `check` | formulários |

- Campos de formulário são renderizados por `partials/form_field.html`.
- Textos longos (rotas, chaves, caminhos) usam `pre`/`mono` com quebra;
  não podem estourar o card.
- Evite classes novas para o mesmo papel; se precisar, promova o componente
  para `frontend/src.css` (kit) ou `ui.css` em vez de estilizar a página.
- Não há `<style>` nem handlers inline nos templates.

### Views e frontend

- Views autenticadas usam `Class-based views`:
  - `FormView` para formulários;
  - `TemplateView` para páginas de leitura;
  - `View` com `get()`/`post()` explícitos nos fluxos críticos.
- `core/view_base.py` concentra apenas login e o ciclo de vida comum; validação,
  confirmação e auditoria continuam explícitas em cada fluxo.
- `ListView`/`DetailView` não são usados para shares/snapshots/jobs porque eles
  vêm do agente, não de models Django.
- `templates/partials/` reúne mensagens, busca, resultados, métricas do sistema e
  o coletor live.
- CSS e JavaScript ficam em `static/css/` e `static/js/`; o HTML não contém
  `<style>`, `<script>` inline nem handlers `onclick`/`onsubmit`.
- `STATICFILES_DIRS` aponta para `static/`; o `collectstatic` do entrypoint
  publica os arquivos para o WhiteNoise.

```
homelab-storage-admin/
├── agent/
│   ├── homelab-storage-agent.py
│   ├── homelab-storage-agent.service
│   ├── homelab-storage-snapshot.py
│   ├── homelab-storage-snapshot.service
│   └── homelab-storage-snapshot.timer
├── config/            # settings Django (env)
├── core/              # CBVs, forms, models, cliente do agente, helpers HTTP
├── history/           # navegador read-only de snapshots/versoes
├── storage/           # temperatura/estado/SMART sob demanda (standby-safe)
├── backups/           # wizard, jobs, snapshots restic e navegador read-only
├── frontend/          # fonte Tailwind (src.css); compile com tailwind build
├── templates/         # UI escura, partials e sem dependências externas
├── static/            # CSS (ui.css + kit.css) e JavaScript, fora do HTML
├── deploy/pi/
│   ├── homelab-compose.service
│   └── motd
├── docker-compose.yml
├── install-agent.sh
├── deploy.sh
└── .env.example
```

`deploy/pi/homelab-cloudflared.service` e `cloudflared-config.yml.example`
continuam no disco e não fazem parte do acesso.

## Login pelo Credenciais (moyaserver)

No moyaserver, o Storage Admin usa a senha única do Credenciais. O container
entra na rede `moya` e recebe `CREDENTIALS_URL`/`CREDENTIALS_API_TOKEN`.

- Quem não tem a concessão `storage` no Credenciais recebe "não tem acesso".
- O acesso é binário: quem entra pode operar o Storage Admin; não há papéis.
- **Regra fixa:** o código é compartilhado com o Pi. As features continuam
  existindo; o que muda é uma flag explícita por host.
- `CREDENTIALS_MANAGE_USERS=0` (Pi): todas as funções de usuário/grupo ficam
  disponíveis.
- `CREDENTIALS_MANAGE_USERS=1` (moyaserver): o Storage Admin bloqueia apenas
  a sobreposição de identidade — criar usuário, senha, grupos do usuário,
  ativar/desativar e excluir. A lista de usuários continua; criar/excluir
  grupos Linux e as operações de servidor continuam disponíveis.
- No moyaserver, a fonte de identidade dos apps e do Samba é o Credenciais.
  Alterações locais feitas no Storage Admin não atualizam o hash do
  Credenciais; para acesso aos apps, use o Credenciais.
- O usuário local `admin` continua funcionando como acesso de emergência se o
  Credenciais estiver fora do ar.
- No Pi, sem `CREDENTIALS_URL`, o login é o usuário local deste servidor.
  A tela diz "conta deste servidor". No moyaserver, com URL e token, continua
  "mesma conta do Credenciais".
- Textos, ajuda e páginas de Gitea e de backup local de arquivos seguem as
  capacidades do host. No Pi, sem o container do Gitea e sem o app Credenciais,
  esses blocos não aparecem. No moyaserver, com o container e com
  `CREDENCIAIS_DB`/`CREDENCIAIS_ENV`, o atalho do Gitea, os jobs de arquivos e
  a gestão de usuários pelo Credenciais continuam.

### Propagação da senha para o Samba (moyaserver)

No moyaserver, a conta Samba é criada e atualizada por automação do Credenciais,
fora deste repositório. A senha do app e a do Samba são iguais porque o mesmo
texto é empurrado no evento, não porque exista um armazenamento compartilhado:
o Credenciais fica com o hash dele e o Samba com o hash NT em `passdb.tdb`.

- O evento de criação (ativar conta e definir a senha) cria a conta Samba.
- Troca de senha posterior precisa do mesmo push; sem ele, a senha nova vale
  nos apps e a antiga continua no SMB.
- Desativar e excluir precisam de `smbpasswd -d`/`-x`; credencial Samba órfã
  continua dando acesso ao share.
- O push é idempotente: `smbpasswd -a` em usuário existente só troca a senha,
  então reexecutar depois de falha é seguro.
- O painel não participa desse caminho e, com `CREDENTIALS_MANAGE_USERS=1`,
  também não disputa a fonte da verdade.

No Pi não há Credenciais nem automação: a senha definida na interface vale só
para o Samba. A conta Linux nasce sem senha e com shell `nologin`.

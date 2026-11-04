# Homelab Storage Admin

Painel web para administrar o NAS do homelab (`homelab`, Raspberry Pi 5) sem
decorar comandos: usuários e grupos do Samba, shares, snapshots Btrfs ou rsync
e espaço em disco. O mesmo código atende o Pi, o moyaserver e um
Ubuntu+Samba via perfil de host.

> **Nunca comite `.env`.** Este repositório não contém senhas. A senha do admin
> é definida no `.env` do servidor (modo `600`) e trocada com
> `docker compose exec web python manage.py changepassword admin`.

> **Acesso:** `https://homelab.conradhub.com` em casa e no Tailscale. Fora de
> casa só o Tailscale. Sem túnel e sem Access. Ver [Rede](docs/REDE.md) e
> [Segurança](docs/SEGURANCA.md).

## Comece por aqui

- **Instalar ou atualizar:** [Instalação e deploy](docs/INSTALACAO.md)
- **Entender o desenho:** [Arquitetura e código](docs/ARQUITETURA.md)
- **Retomar o contexto:** [docs/CONTEXTO.md](docs/CONTEXTO.md)
- **Regras para agentes:** [AGENTS.md](AGENTS.md)

## O que ele faz

| Tarefa | Interface |
|---|---|
| Criar usuário Linux + Samba | Usuários → Novo usuário |
| Criar grupo Linux/Samba | Usuários → Novo grupo |
| Trocar senha do Samba | Usuários → Senha |
| Editar grupos | Usuários → Grupos |
| Ativar/desativar acesso | Usuários → botão Ativar/Desativar |
| Criar share no `smb.conf` | Shares → Novo share |
| Navegar/buscar snapshots Btrfs | Snapshots → Navegar (`/history/`) — read-only, busca e download |
| Ver temperatura/SMART dos discos | Discos (`/storage/`) — leitura sob demanda, standby-safe |
| Visão geral do host | Dashboard — sistema, todos os discos, volumes, RAID/Btrfs, backup e resumo de snapshots |
| Preparar disco de backup | Backups (`/backups/`) — wizard com confirmação extra |
| Consultar senha do restic | Backups → Senha do repositório — exige senha do app |
| Ver status de snapshot por share | Shares/Snapshots — sim (keep N) ou não configurado |
| Ver saúde do host | Dashboard — card Saúde com discos, backups, containers e pendências |
| Ver e gerenciar rede/firewall | Rede (`/rede/`) - interfaces, rotas, portas, Docker e regras UFW |
| Ver e operar containers | Containers (`/containers/`) — Docker ou Podman, iniciar/parar/reiniciar e logs |
| Backup local de arquivos | Backups → Backup de arquivos — jobs independentes, retenção e restore |
| Cadastrar jobs/periodicidade | Backups → Novo job / Editar |
| Listar snapshots restic | Backups → Snapshots restic — data, arquivos, tamanho e fontes |
| Navegar/baixar/buscar no restic | Backups → Snapshots restic → Navegar — read-only, busca e download |
| Cópia fria USB | Backups → Cópia fria (USB) — restic copy + check + eject |
| Backup do Credenciais | Backups → Backup do Credenciais — banco + `.env`, sem restic |
| Ver versões de um arquivo | Histórico → arquivo → Versões |
| Share privado/oculto | Shares → Novo share → Privado (`browseable = no`) |
| Ver dados e snapshots | Dashboard / Shares |
| Criar/remover snapshot Btrfs | Snapshots |

O dashboard e a página de shares carregam primeiro a lista e buscam os
tamanhos depois, em `/metrics/shares/`. O agente reaproveita cada `du` por
3 minutos, então abrir a página de novo não mede o disco outra vez.
O card **Saúde** vem de `health_overview` e o card **Backup de arquivos** lê os
jobs de `/backups/arquivos/`; jobs restic aparecem em documento separado.

## Início rápido

No PC (desenvolvimento):

```bash
uv sync --dev
uv run pytest
uv run manage.py runserver 0.0.0.0:8000
```

No Pi:

```bash
git clone https://github.com/ConradoAlmeida/homelab-storage-admin.git \
  /opt/stacks/homelab-storage-admin
cd /opt/stacks/homelab-storage-admin
cp .env.example .env && chmod 600 .env
# edite .env: SECRET_KEY, senha do admin, ALLOWED_HOSTS e CSRF
sudo ./install-agent.sh
./deploy.sh
```

> Checklist, rollback, boot e variáveis: [Instalação e deploy](docs/INSTALACAO.md).

## Arquitetura em 30 segundos

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

## Perfis de host

O mesmo código atende o Pi, o moyaserver e um Ubuntu+Samba. O perfil fica em
`/etc/homelab-storage-admin/host.env`; os overlays são
`docker-compose.homelab.yml` (Pi) e `docker-compose.moya.yml` (moya). O app
**não** gerencia Cockpit, Pi-hole, Caddy, DNS nem o Jellyfin — são vizinhos.
Detalhes: [Arquitetura](docs/ARQUITETURA.md#perfis-de-host).

## Documentação

| Documento | Conteúdo |
|---|---|
| [Instalação e deploy](docs/INSTALACAO.md) | Pré-requisitos, deploy, checklist, rollback, boot, dev local e `.env` |
| [Arquitetura e código](docs/ARQUITETURA.md) | Container/agente, perfis de host, Btrfs, estrutura, UI e Credenciais |
| [Snapshots, discos e Samba](docs/ARMAZENAMENTO.md) | Snapshots, Jellyfin, histórico, SMART e shares |
| [Backups](docs/BACKUPS.md) | Disco de backup, jobs restic, backup local, cópia fria e Gitea |
| [Rede, saúde e containers](docs/REDE.md) | Saúde, nomes, firewall UFW e containers |
| [Segurança e acesso remoto](docs/SEGURANCA.md) | Tailscale, cookies HTTPS e checklist |
| [Testes na VM](docs/VM_TESTES.md) | Roteiro server-like no virt-manager |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Sintomas, causas e correções |
| [Contexto](docs/CONTEXTO.md) | Estado atual, decisões e pendências |

## Estrutura do repositório

| Caminho | Papel |
|---|---|
| `agent/` | Operações root no host (usuários, Samba, snapshots, discos, restic, Gitea, rede) |
| `core/` | Dashboard, rede, usuários, shares, snapshots e cliente do agente |
| `backups/` | Wizard de disco, jobs restic, snapshots, cópia fria e backup local |
| `storage/` | Discos, SMART e RAID/Btrfs |
| `history/` | Navegador read-only de arquivos e versões |
| `templates/` + `static/` | UI |
| `deploy/` | Units e exemplos do Pi |
| `docs/` | Manuais por área (este README é o índice) |

## Fora do escopo

Active Directory (o Samba é `tdbsam` standalone), autoatendimento de senha,
backup externo (use `restic` no host) e a **administração do Jellyfin**. O
Jellyfin tem stack, bibliotecas, plugins, transcoding e config próprios; este
repo não instala, atualiza, configura nem faz backup dele. O dashboard mostra um
atalho, o share Samba `jellyfin` segue como share comum (sem snapshot/restic) e,
somente quando o container existe, a página **Torrents** envia um link magnético
para uma pasta de mídia já configurada nele.

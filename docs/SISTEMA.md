# Sistema (host, configuração, rotas, chaves, logs, serviços, terminal)

Sete telas no menu **Sistema**, mesmo código no Pi e no moyaserver. O que o host
não oferece some com explicação (sem erro 500).

## Configuração (`/sistema/config/`)

Somente leitura: comando **SSH** em destaque (`SSH_LOGIN` no `host.env`, ou
`SHARE_OWNER` + hostname do agente) e tabela com caminhos absolutos no host:

- `/etc/homelab-storage-admin/host.env` — perfil (prefixos, overlay, `SSH_LOGIN`).
- `/opt/stacks/homelab-storage-admin/.env` — segredo Django do painel.
- `services.ini` no `DATA_DIR` do host — no Pi
  `/mnt/nas/apps/homelab-storage-admin/data/services.ini`; no moya
  `/opt/stacks/homelab-storage-admin/data/services.ini` (atalhos da home,
  gerados do `deploy/<perfil>/apps.env`).
- No moyaserver, com `CREDENCIAIS_ENV` definido: caminho do `.env` do Credenciais
  (ex.: `/home/conrado/moya_credenciais_app/.env`). No Pi essa linha não aparece.

O Compose repassa `SSH_LOGIN`, `SERVICES_INI_HOST`, `STACK_ENV_PATH` e
`CREDENCIAIS_ENV` para o Django sem expor `/app/data` na UI. Não há botão de
salvar; `host.env` e `.env` do stack valem após `install-agent.sh` e `deploy.sh`;
`services.ini` (gerado pelo `apps-sync`) vale ao recarregar o painel; a
curadoria é `atalho=` no env, não edição no host.

## Rotas e atalhos (`/sistema/rotas/`)

Somente leitura: lê o `deploy/<perfil>/apps.env` (montado do checkout em
`/app/deploy`, sem depender do build) e o estado do último `apps-sync --apply`
(`/var/lib/homelab-storage-admin/apps.aplicados`, 0644). Uma tabela com app,
rota, atalhos (`painel`/`portal`), grupo do portal e estado:

- `aplicado` — a linha do estado é idêntica à do env;
- `pendente` — o env mudou depois do último `--apply`;
- `novo` — ainda não aparece no estado (primeira execução ou sem sudo);
- `fora do env` — seção separada com o que está aplicado mas saiu do env;
  os containers/pastas só saem com `--prune-containers`/`--prune-data`.

O resumo mostra quantas rotas, quantas no painel, quantas no portal e quantas
estão sem atalho. `atalho=` é curadoria: sem a flag a app tem rota e DNS, mas
não aparece em lugar nenhum. Grupo só vale para o portal. Env ou estado
ausente viram aviso na tela, nunca erro 500 — a página não escreve nada.

## Host (`/sistema/`)

Ficha somente leitura: hostname, nome amigável (`SITE_NAME` em `host.env`),
sistema (`/etc/os-release`), kernel e horário.

Com **apt** e **SYSTEM_MANAGE** (no `host.env` e no Django): **Verificar
atualizações** dispara tarefa longa (`apt_check`: `apt-get update` +
listagem). **Instalar atualizações** exige a frase exata `ATUALIZAR` e dispara
`apt_upgrade` (`apt-get upgrade -y`), também como tarefa longa.

## Chaves (`/sistema/chaves/`)

Fingerprints das chaves em `~/.ssh/authorized_keys` (`ssh-keygen -lf`). A
chave privada não é lida.

Com capability **jellyfin**: linha da API de torrents — indica se há token e o
SHA-256 do segredo (valor vindo do banco/env, como na página Torrents); o
segredo em claro só na página Torrents.

## Logs (`/sistema/logs/`)

Um formulário com filtro fechado: sistema, storage, rede, serviço, container.
Argumentos do `journalctl` são fixos no agente; prioridade e período só no
filtro **sistema**. Storage junta o identificador `udisksd` com o kernel de
Btrfs/md/RAID. Rede usa o identificador (`-t`) de `systemd-networkd`,
`systemd-networkd-wait-online` e NetworkManager, para o timeout chamado pelo
`apt-daily` aparecer. Até 500 linhas. Sem `journalctl`, mensagem explicativa.

**Container**: só aparece com runtime Docker/Podman. A rota antiga
`/containers/logs/` redireciona para Logs com filtro container.

Atalho de log de unit: `/sistema/logs/?filtro=servico&unit=nome.service`.

## Serviços (`/sistema/servicos/`)

Lista units (`systemctl list-units`). Com **systemctl** e **SYSTEM_MANAGE**:
start, stop, restart, enable, disable. Parar, reiniciar e desabilitar pedem
confirmação digitando o nome completo da unit. Denylist no agente: ssh, sshd,
homelab-storage-agent, docker, containerd, podman, systemd-journald,
systemd-networkd.

## Terminal (`/sistema/terminal/`)

Ligado por padrão (`TERMINAL_ENABLE=1` no app e no agente). `0` oculta a
rota. A página pede usuário Linux e senha sudo; o agente confere com
`sudo -S -v` dessa conta e abre o shell **dela**, não um shell root. O pty
vira o terminal de controle da sessão, com posse da conta, para o bash ter
job control e o `sudo` pedir a senha nesse terminal. A senha
vai no stdin e não entra na auditoria nem no argv. Segundo socket Unix
(`TERMINAL_SOCKET` / `terminal.sock`). Abrir e fechar são auditados. O
conteúdo da sessão não é gravado. Inatividade de 15 minutos encerra.

## Variáveis

| Variável | Onde | Efeito |
|---|---|---|
| `SYSTEM_MANAGE` | `host.env`, agente, Django | 1 liga apt e systemctl na UI; 0 somente leitura |
| `TERMINAL_ENABLE` | `host.env`, agente, Django | padrão 1, publica rota e menu; 0 oculta |
| `TERMINAL_SOCKET` | Django (opcional) | Caminho do segundo socket (default: `.../terminal.sock`) |

Capabilities derivadas de binários no host: `apt`, `journal`, `systemctl`;
`jellyfin` e `containers` como hoje.

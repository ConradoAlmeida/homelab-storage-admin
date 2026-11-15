# Sistema (host, configuração, rotas, chaves, logs, serviços, terminal)

Sete telas no menu **Sistema**, mesmo código no Pi e no moyaserver. O que o host
não oferece some com explicação (sem erro 500).

## Configuração (`/sistema/config/`)

Somente leitura, organizada por **frequência de mudança**, não por arquivo:

1. **Rotas, DNS e atalhos** — `deploy/<perfil>/apps.env`: o único arquivo do
   dia a dia. Um cartão com o caminho no host, o que controla e **Como
   aplicar**, em passos numerados e com os comandos reais: editar no
   repositório → `git pull` no host → `sudo bash
   scripts/stacks/apps-sync.sh [--perfil moya] --apply` (sem `--apply` é
   dry-run) → `--doctor` para conferir. O flag `--perfil moya` só aparece onde
   o script não assume o perfil. Link para
   [Rotas e atalhos](#rotas-e-atalhos-sistemarotas); sem `APPS_ENV_PATH`
   definido, o cartão vira aviso.
2. **Perfil e segredos** — `host.env` (perfil: portas `BIND_*`, prefixos,
   `SSH_LOGIN`, overlay do Compose) e o `.env` do stack (segredo do Django);
   no moyaserver, também o `.env` do Credenciais quando `CREDENCIAIS_ENV` está
   definido. Mudam raramente e valem após `install-agent.sh` e `deploy.sh`.
3. **Gerados** — `services.ini` do `DATA_DIR` (atalhos do painel) e, no moya,
   o `apps-portal.ini` do portal. São artefatos do `apps-sync`: editar no host
   se perde na próxima execução (na primeira vez ele guarda `.bak-<data>`).
4. Comando **SSH** (`SSH_LOGIN`, ou `SHARE_OWNER` + hostname do agente).

Não há botão de salvar. O Compose repassa `SSH_LOGIN`, `SERVICES_INI_HOST`,
`STACK_ENV_PATH`, `CREDENCIAIS_ENV` e `APPS_ENV_PATH` para o Django sem expor
`/app/data` na UI.

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

# Sistema (host, chaves, logs, serviços, terminal)

Cinco telas no menu **Sistema**, mesmo código no Pi e no moyaserver. O que o host
não oferece some com explicação (sem erro 500).

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

Só com **TERMINAL_ENABLE=1** no ambiente do app e `terminal_enable` nas
capabilities do agente. Segundo socket Unix no mesmo diretório que o socket
principal (`TERMINAL_SOCKET` / `terminal.sock`). O cliente HTTP fala com o
agente via `terminal_*` no JSON; abrir/fechar vão para auditoria; conteúdo da
sessão não é gravado. Inatividade 15 minutos encerra no agente.

## Variáveis

| Variável | Onde | Efeito |
|---|---|---|
| `SYSTEM_MANAGE` | `host.env`, agente, Django | 1 liga apt e systemctl na UI; 0 somente leitura |
| `TERMINAL_ENABLE` | `host.env`, agente, Django | 1 publica rota e menu; 0 oculta |
| `TERMINAL_SOCKET` | Django (opcional) | Caminho do segundo socket (default: `.../terminal.sock`) |

Capabilities derivadas de binários no host: `apt`, `journal`, `systemctl`;
`jellyfin` e `containers` como hoje.

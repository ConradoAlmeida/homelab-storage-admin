# Telas de sistema (Host, Chaves, Logs, Serviços, Terminal)

## Objetivo

Trazer para o painel o que hoje só existe no Cockpit, em cinco telas no menu
Sistema. O mesmo código vale para o Pi e para o moyaserver. O que o host não
tem some da tela, com o motivo, e não vira erro 500.

## Escopo

Telas novas, nesta ordem, na seção Sistema:

| Tela | Rota | O que faz |
|---|---|---|
| Host | `/sistema/` | Ficha somente leitura e atualização de pacotes |
| Chaves | `/sistema/chaves/` | Fingerprints de SSH e o slot da API de torrents |
| Logs | `/sistema/logs/` | Uma tela; o filtro escolhe a fonte |
| Serviços | `/sistema/servicos/` | Units systemd e o atalho para o log da unit |
| Terminal | `/sistema/terminal/` | Shell no navegador, só com flag no host |

Filtros da tela Logs:

| Filtro | Fonte fixa no agente |
|---|---|
| Sistema | Journal do host, com prioridade e período de uma lista fechada |
| Storage | `udisksd` / `udisks2` e mensagens de Btrfs, md e RAID |
| Rede | `systemd-networkd`, `systemd-networkd-wait-online`, NetworkManager |
| Serviço | Journal da unit aberta em Serviços |
| Container | A cauda que `/containers/logs/` já pede hoje |

`/containers/logs/` passa a redirecionar para Logs com o filtro Container.
A página Containers continua só com iniciar, parar e reiniciar.

Fora deste plano: editar hostname, gravar `authorized_keys`, `dist-upgrade`,
`autoremove`, mask de unit, editar unit, firewalld, particionar disco,
histórico PCP, desligar o host, varrer o disco atrás de segredo, e silenciar
o timeout do `apt-daily` no `systemd-networkd-wait-online`.

## Decisões

- Sem `if pi` / `if moya` nas views. Presença de binário vira capability
  (`apt`, `journal`, `systemctl`). Recurso de outro app segue as capabilities
  que já existem (`jellyfin`, `containers`).
- `CREDENTIALS_MANAGE_USERS` não bloqueia estas rotas. Elas não criam pessoa,
  não trocam senha e não mexem em grupo de usuário. No moya o login continua
  o do Credenciais.
- Ficha do host é leitura: hostname, nome amigável, sistema, kernel e
  horário. Os dois hosts mostram a própria ficha. Não há botão de renomear.
- Atualizar pacotes é `apt-get update` na verificação e `apt-get upgrade -y`
  no disparo. Sem nome de pacote vindo da UI, sem `dist-upgrade`, sem
  `autoremove`. O disparo pede a frase `ATUALIZAR` e corre como tarefa longa,
  no mesmo modelo dos backups. Sem `apt`, o bloco explica e não oferece ação.
- `SYSTEM_MANAGE=1` liga verificação/disparo de pacotes e start/stop/restart/
  enable/disable de unit. `0` deixa Host, Chaves, Logs e a lista de serviços
  em leitura. Os exemplos do Pi e do moya nascem com `1`, no mesmo espírito
  de `FIREWALL_MANAGE`. `install-agent.sh` não sobrescreve `host.env` já
  existente: ligar no Pi e no moya é um passo do dono.
- Parar, reiniciar ou desabilitar unit pede confirmação com o nome da unit.
  A denylist recusa `ssh`, `sshd`, `homelab-storage-agent`, `docker`,
  `containerd`, `podman`, `systemd-journald` e `systemd-networkd`. O nome da
  unit tem de casar com `^[a-zA-Z0-9:_.@\\-]+$` e existir no systemd.
- Chaves SSH são leitura: usuário, comentário e fingerprint
  (`ssh-keygen -lf`). Não se lê chave privada. O slot da API de torrents só
  aparece com `capabilities.jellyfin` (Pi com Jellyfin; moya sem). A tela
  mostra se há token e o fingerprint SHA-256; o segredo continua na página
  Torrents, com a senha do administrador. Sem varredura de token do Caddy,
  do Tailscale ou de senha do restic.
- Logs não aceitam argumento livre de `journalctl`. Cada filtro é um argv
  fixo. Prioridade e período vêm de listas fechadas. A resposta cabe no
  limite de 1 MiB da linha do socket (no máximo 500 linhas). Journal vazio
  é tabela vazia. Sem `journalctl`, a tela mostra o motivo. Sem runtime de
  container, o filtro Container some.
- O filtro Rede não inclui o `UFW BLOCK` do kernel. A página Rede já mostra
  as regras. O que o Cockpit mostrou em 2026-11-06 (timeout do
  `systemd-networkd-wait-online` chamado pelo `apt-daily`, e `udisksd` sem
  os `.so` de btrfs/iscsi/lvm2) cai nos filtros Rede e Storage.
- Terminal é sessão PTY, não um `op` de comando livre e não `shell=True` nas
  operações já existentes. O socket de uma linha JSON permanece. A sessão
  usa um segundo socket Unix, no mesmo diretório do agente, modo `0660`.
  Só entra na UI com `TERMINAL_ENABLE=1`. Os exemplos nascem com `0`.
  Abrir e fechar vão para a auditoria; o conteúdo da sessão não é gravado.
  Timeout de inatividade de 15 minutos. Um worker do Gunicorn fica ocupado
  enquanto a sessão está aberta. Emulador em `static/`, sem npm.
- UI com `page-head`, `section-head`, `card`, `alert`, `btn`, `table-wrap`
  e `tag`. Ajuda contextual nas cinco páginas. Texto em português.

## Passos

- [x] Capabilities `apt`, `journal` e `systemctl` no agente, mais
      `SYSTEM_MANAGE` e `TERMINAL_ENABLE` lidos do `host.env`. Exemplos do
      Pi, do moya e fixtures de teste.
- [x] Host: `op_host_info` (leitura) e tarefas `apt_check` / `apt_upgrade`
      com frase `ATUALIZAR`. Tela `/sistema/`.
- [x] Chaves: `op_ssh_keys` só com fingerprint. Linha do token de torrents
      condicionada a `jellyfin`, sem revelar o segredo.
- [x] Logs: `op_journal` com filtro enum. Tela única. Redirect de
      `/containers/logs/`. Atalho da unit usa `?filtro=servico&unit=`.
- [x] Serviços: listar e as cinco ações, denylist e confirmação no stop,
      restart e disable.
- [x] Terminal: segundo socket, relay na view, flag, auditoria de abrir e
      fechar, timeout.
- [x] Menu Sistema, ajuda, `docs/SISTEMA.md`, índice do `README.md` e
      `docs/CONTEXTO.md`.

## Verificação

- `uv run pytest`: páginas renderizam sem `apt`, sem `journalctl`, sem
  systemd e sem containers; filtro desconhecido e unit fora da denylist ou
  do regex são recusados; moya (`CREDENTIALS_MANAGE_USERS=1` e sem
  `jellyfin`) não mostra o slot de torrents e não bloqueia as rotas; Pi
  com `jellyfin` mostra o slot sem o segredo; `SYSTEM_MANAGE=0` não dispara
  apt nem systemctl; `TERMINAL_ENABLE=0` não publica a rota; ações de
  pacote, unit e terminal geram auditoria; frase errada não atualiza.
- UI no navegador, no modo demo ou no runserver: as cinco telas, o filtro
  de Logs, a confirmação de unit e o estado sem capability.
- Lab na VM (`docs/VM_TESTES.md`, `linux2024`): `journalctl` e `systemctl`
  reais nos dois perfis de `host.env`; `apt-get update` e a lista de
  pacotes; o upgrade fica no `-s` (simulação), sem aplicar pacote na VM.
  Sem virt-manager neste host, declarar a exceção. Pytest local não
  substitui a VM.
- Deploy no Pi e no moya fica com o dono. Não rodar `./deploy.sh` neste
  plano.

## Estado

Implementado em 2026-11-06 pelo Composer 2.5, com correção do coordenador:
`apt_check`/`apt_upgrade` param no `_checkpoint` (senão o precheck rodava o
apt e recusava a tarefa); chaves SSH leem `authorized_keys`; filtro Rede usa
`-t` para pegar o `systemd-networkd-wait-online` disparado pelo `apt-daily`;
linha vazia `-- No entries --` não entra no journal.

Bancada: pytest local e na VM `linux2024` (`192.168.122.26`) 358 passed,
6 skipped. Lab `sudo bash scripts/vm/run-lab-tests.sh`: 6 passed. Nos perfis
pi e moya, journal, systemctl e `apt-get -s upgrade` reais; `ssh.service`
recusado. UFW estava inativo; a ativação de prova ficou para o dono confirmar
a volta ao inativo.

Em 2026-11-06, à tarde: `TERMINAL_ENABLE` passa a valer 1 por padrão. A
sessão só abre depois de `sudo -S -v` da conta Linux e o shell é dessa conta.

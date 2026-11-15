# Bancada de VM Ubuntu 26.04 (perfis homelab e moya)

Roteiro para validar o ecossistema Moya em uma VM descartavel com Ubuntu
Server 26.04. Pytest no clone (Fedora ou CI) cobre contrato e UI; **nao**
cobre Samba, UFW, restic/Btrfs em disco virtual nem restore server-like. Neste
desktop a VM e a `linux2024` (`qemu:///system`, x86_64, qcow2 sem backing).

A bancada e **obrigatoria** aqui. A unica excecao e trabalhar num host sem
libvirt/virt-manager (outro notebook, SSH, CI): declare que o laboratorio nao
rodou. WSL2 nao serve para Samba/UFW reais.

## Como funciona

Um script no host (`scripts/vm/bench.sh`) e dois no convidado (`perfil-*.sh`,
`clean.sh`). Cada execucao **comeca e termina no snapshot do perfil**, entao a
segunda rodada comeca igual a primeira.

```
base-limpo ──preparar homelab──► homelab-pronto ──testar──► volta
           └─preparar moya────► moya-pronto    ──testar──► volta
```

| Script | Onde roda | Papel |
|---|---|---|
| `scripts/vm/bench.sh` | host | revert, start, espera guest agent, ssh, snapshot |
| `scripts/vm/perfil-homelab.sh` | convidado (root) | `/mnt/nas`, `/mnt/backup`, `host.env`, overlay, agente |
| `scripts/vm/perfil-moya.sh` | convidado (root) | `/srv/samba`, `/mnt/data`, rede `moya`, `host.env`, agente |
| `scripts/vm/clean.sh` | convidado (root) | remove so o que o projeto instalou |

`base-limpo` e a origem (so `setup-ubuntu-2604.sh`) e nunca recebe testes.
Snapshots sao internos: criar, reverter e apagar exigem a VM desligada, e e o
`bench.sh` que faz isso.

## Primeira vez

```bash
# 1. no convidado, uma unica vez (cria /etc/homelab-vm-bench)
sudo INSTALL_DOCKER=1 bash scripts/vm/setup-ubuntu-2604.sh

# 2. no host: VM desligada e o estado limpo vira a origem
scripts/vm/bench.sh snapshot criar base-limpo

# 3. no host: perfil instalado e congelado
scripts/vm/bench.sh preparar --perfil homelab
scripts/vm/bench.sh preparar --perfil moya
```

O `preparar` reverte `base-limpo`, clona/reseta o clone do repo
(`~/homelab-storage-admin`), roda o `perfil-*.sh`, desliga e cria
`<perfil>-pronto`. Use `--ref <branch|tag|sha>` para testar um commit que nao
esta em `main` e `--recriar` para atualizar o snapshot do perfil.

## Rodar a bancada

```bash
scripts/vm/bench.sh testar --perfil homelab --smoke
scripts/vm/bench.sh testar --perfil moya --smoke
```

O que roda, na ordem:

| Perfil | Etapas |
|---|---|
| homelab | `manage.py check`, `pytest -q`, `scripts/vm/run-lab-tests.sh` |
| moya | `manage.py check`, `pytest -q`, `scripts/vm/run-unit-tests.sh` (Credenciais + Storage) |
| ambos com `--smoke` | `./deploy.sh` real + 7 rotas HTTP (login, painel, saude, backups, containers, sistema) |

Esperado hoje: **453 passed, 8 skipped** (skips = laboratorio/hardware) e
**8 lab passed** no homelab; **138 testes do Credenciais** e a mesma suite do
Storage no moya. O `--smoke` leva alguns minutos por causa do `--build`.

Flags uteis:

```bash
--manter    # deixa a VM ligada e NAO reverte (quebra o invariante de proposito)
--yes       # sem confirmacao interativa (CI, terminal sem tty)
--perfil    # homelab | moya
```

Estado e limpeza:

```bash
scripts/vm/bench.sh snapshot listar
scripts/vm/bench.sh limpar --perfil homelab   # volta ao snapshot, sem testar
scripts/vm/bench.sh snapshot apagar moya-pronto
```

## Limpeza guardada

O `clean.sh` so roda com o marker `/etc/homelab-vm-bench` (criado pelo setup).
Ele remove units, binarios, `/etc/homelab-*`, containers/imagens do projeto,
sockets e o que os perfis registraram em `/var/lib/homelab-vm-bench/criado`.
Nunca `docker system prune`, nunca `rm -rf /mnt/*`.

```bash
sudo bash scripts/vm/clean.sh            # dry-run, nao altera nada
sudo bash scripts/vm/clean.sh --apply    # executa e autoverifica (CLEAN_OK)
```

Ele e a rede de seguranca para reconstruir o `base-limpo`: limpar, conferir
que nao sobrou nada e recriar o snapshot. Repositorios em `~` nao sao tocados.

## Fora do bench (manual)

- **E2E de identidade/Samba e Mailpit:** ficam no outro repo, em
  `moya_credenciais_app/docs/E2E_VM.md` (`MOYA_E2E=1`, cria e apaga usuario
  real, usa o share `e2e`). O perfil moya sobe o app sem token, entao o login e
  local (break-glass); o E2E do IdP continua la.
- **Login cruzado Credenciais → Storage:** precisa do stack do Credenciais em
  `127.0.0.1:8080` e de `CREDENTIALS_URL`/`CREDENTIALS_API_TOKEN` no `host.env`.
- **UFW:** a VM valida o agente e as regras, nao a topologia do Pi ou do moya.
  Com a VM ligada (`--manter`), ative pelo painel ou `sudo ufw enable` e
  mantenha o console aberto; para voltar, `sudo ufw disable` ou reverta o
  snapshot.
- **Backups/restic:** anexe um disco virtual secundario (ex.: `/dev/vdb`) e use
  o wizard do painel; loop devices tambem servem para o repo restic.
- **Disco:** 18 GB com ~11 GB livres (crescido em 2026-11-15); ainda cabe um
  repo restic de teste. Crescer de novo exige apagar os snapshots, porque o
  snapshot interno guarda o tamanho do disco.

## O que nao da para validar na VM

- SMART real, USB fisico, RAID fisico e falha de disco;
- hardware/desempenho do RPi5 e arm64;
- Graph/Exchange, caixas compartilhadas e rotacao real do Gmail;
- carga e disponibilidade de producao.

## Emergencia

```bash
sudo smbpasswd -x it-XXXXXXXXXX     # so usuario de teste
sudo userdel -r it-XXXXXXXXXX
scripts/vm/bench.sh limpar --perfil homelab   # no host
```

Nunca copie `.env` de producao para a VM.

# Snapshot depois da criação do share

## Objetivo

Share em Btrfs nasce subvolume mesmo sem política de versões. Ativar o snapshot depois grava o `smb.conf` e a política. Se a pasta ainda for diretório comum, a ativação converte para subvolume depois de confirmação explícita, preservando os arquivos.

## Escopo

- Agente: `op_create_share` e `op_snapshot_policy_save`.
- UI: texto da caixa no formulário de share; confirmação na política quando a conversão for necessária.
- Testes locais e laboratório na VM `linux2024`.
- Docs da área, ajuda e `docs/CONTEXTO.md`.

Fora: deploy no Pi, conversão de `/mnt/nas/transfer` no homelab, pastas que ninguém pediu para snapshot (`apps`, `docker`, `backups`).

## Decisões

- A caixa "Criar com snapshot…" só liga a política, o `shadow_copy2` e a retenção. No Btrfs ela não decide mais se o caminho é subvolume.
- Backend `btrfs` ou `auto` com filesystem Btrfs e `STORAGE_ROOT` montado: `btrfs subvolume create` na criação, com ou sem a caixa. Sem política e sem linhas `shadow:` quando a caixa está desmarcada.
- Backend `rsync`, `none`, ou Btrfs desmontado: sem subvolume. Desmontado, a criação em caminho Btrfs recusa em vez de `mkdir` no disco de baixo. Ext4 continua `mkdir`; snapshot ligado continua rsync.
- Denylist permanece: não cria subvolume nem política para nome proibido quando o snapshot está pedido; sem a caixa, o share denylist continua diretório comum.
- Ativar política em subvolume que já existe: mesmo fluxo de hoje (`_smb_set_shadow` + `snapshots.json`). Sem confirmação extra.
- Ativar política em diretório comum no Btrfs: o agente só converte se `confirmation` for exatamente o nome do share. Sem isso, não move arquivo, não grava Samba e não grava política. A tela pede o nome.
- Conversão: subvolume temporário irmão (`.NOME.subvol-new`), `rsync -aHAX --numeric-ids` do conteúdo, renomeia o diretório para `.NOME.dir-old`, coloca o subvolume no caminho original. Falha no meio devolve o diretório ao lugar e apaga o subvolume temporário. O `.dir-old` só sai depois que o caminho final é subvolume. Sem `shell=True`. Caminhos só sob os prefixos permitidos, nunca dentro de `.snapshots`. Se já existir resíduo `.subvol-new` ou `.dir-old`, recusa. Subvolume aninhado dentro da pasta: recusa.
- Desativar política não converte e não apaga snapshot.
- `snapshot_policy_save` segue tarefa longa por causa do rsync.

## Passos

- [x] Branch `feat/snapshot-subvolume` a partir de `main`, sem levar o WIP alheio (cloudflared, REDE, SEGURANCA, services.ini, plano do Cockpit).
- [x] Criar subvolume na criação Btrfs sem política; manter mkdir no rsync.
- [x] Converter diretório comum na ativação, só com o nome do share confirmado, e então gravar Samba e política.
- [x] Formulário de share e tela de política explicam o comportamento; confirmação com os componentes de `ui.css`.
- [x] Testes de agente, view e um caso no `tests/lab` (criar sem política, arquivo sobrevive, ativar com confirmação, snapshot read-only).
- [x] Pytest local e laboratório na VM `linux2024` (`scripts/vm/run-lab-tests.sh` e a suíte do app).
- [x] Docs: `docs/ARMAZENAMENTO.md`, `docs/ARQUITETURA.md`, `docs/TROUBLESHOOTING.md`, `core/ajuda.py`, `docs/CONTEXTO.md`.
- [ ] Commit atômico e `git push -u origin HEAD`. Sem deploy.

## Verificação

- `uv run pytest` no clone.
- VM `linux2024` ligada no virt-manager: rsync do clone para a cópia da VM e `sudo bash scripts/vm/run-lab-tests.sh`, mais a suíte do app na VM. Sem virt-manager, parar e dizer. Não declarar a VM sem ter rodado.
- Não converter `/mnt/nas/transfer` no Pi.

## Estado

Plano fechado em 2026-11-08. Execução delegada ao Composer 2.5. WIP alheio no working tree de `main` não entra no commit.

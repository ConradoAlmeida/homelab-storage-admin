# Uso dividido de cada disco

## Objetivo

No dashboard, cada disco mostra as fatias que o ocupam, com tipo de filesystem e o uso de cada uma. A linha "sem FS" e a barra única de `/` saem.

## Escopo

Só o cartão Discos do dashboard. A página Discos (SMART) não muda. Sem commit, push ou deploy neste plano: quem implementa para na verificação local.

## Decisões

- A fatia vem dos filhos do `lsblk`, não do `fstype` do disco inteiro.
- Entra todo nó com ponto de montagem. Entra também nó com `fstype` e sem montagem quando nenhum filho traz a montagem. Some o nó que só existe para agrupar (disco, PV do LVM) se um filho já mostra o volume.
- No RAID, a partição aparece como `linux_raid_member` com o tamanho dela. O ext4 montado em `/mnt/data` aparece na sequência, com o uso do espelho. Os dois membros mostram o mesmo uso.
- No Seagate, as linhas são as que existem de fato: EFI, `/boot`, `/` e `/mnt/backup`, cada uma com o próprio tamanho e uso.
- O uso é lido na hora com `shutil.disk_usage` em cada montagem já ativa. Não chama `smartctl`, `hdparm` nem `lsblk` de novo no request. A árvore de partições continua na coleta diária; só o uso e o `/proc/mdstat` são relidos.
- Disco em standby não é acordado: sem montagem, não há `disk_usage`.
- A coluna Tamanho deixa de mostrar "sem FS".

## Passos

- [x] Agente: guardar `parts` (nome, tamanho, fstype, mounts) na coleta. Função pura que achata a árvore do `lsblk`.
- [x] Agente: em toda resposta de `storage_overview`, preencher o uso vivo de cada montagem, no mesmo espírito de `_raid_now`.
- [x] Dashboard: no lugar da barra única, uma linha por fatia com tipo, montagem, livres/total e a barra. Sem "sem FS".
- [x] Testes: árvore do Seagate gera as quatro fatias; árvore do WD gera o membro e o `/mnt/data`; o segundo `storage_overview` não recolhe SMART e mesmo assim atualiza o uso; a página não contém "sem FS" e contém `/mnt/backup`.
- [x] Uma frase em `docs/ARMAZENAMENTO.md`. Pytest desses testes. Sem VM e sem `systemctl`.

## Verificação

O `sda` lista EFI, `/boot`, `/` e `/mnt/backup` com tipos e barras separadas. O `sdb` e o `sdc` listam a partição RAID e o uso de `/mnt/data`. Abrir o dashboard não dispara SMART.

## Estado

2026-11-10: plano fechado. Implementação delegada ao Composer 2.5. Produção fica para depois da revisão.

2026-11-10: implementado (agente `parts` + uso vivo, dashboard por fatia, testes e doc). Pytest local verde; VM não rodada nesta sessão.

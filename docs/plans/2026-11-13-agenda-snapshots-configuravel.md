# Agenda de snapshots configurável

## Objetivo

Deixar a agenda global dos snapshots de share configurável de verdade: 1 a 24
cópias por dia e o primeiro horário, em vez dos dois horários fixos do cron
legado `samba-snapshot.sh`.

## Problema

Em 2026-11-12 o `moyaserver` tinha duas agendas ativas ao mesmo tempo:

- `homelab-storage-snapshot.timer`: 1×/dia às 03:00, usando `snapshots.json`;
- `/etc/cron.d/samba-snapshots`: 2×/dia (00:05 e 12:05), usando
  `/usr/local/bin/samba-snapshot.sh` com shares e keep fixos no script.

O formulário em Backups escrevia só o cron, então a regra exibida não era a
regra efetiva.

## Decisões

- A agenda passa a ser global, porém configurável: `per_day` (1–24) e
  `first_time` (HH:MM). Os horários são distribuídos igualmente a partir do
  primeiro.
- O agente grava `snapshot-schedule.json` em `CONFIG_DIR` e reescreve
  `homelab-storage-snapshot.timer` com um `OnCalendar` por horário, seguido de
  `daemon-reload` e `restart` do timer.
- Na primeira reconciliação, se existir o cron antigo do
  `samba-snapshot.sh`, o agente importa os dois horários (2×/dia), grava a nova
  agenda e remove o cron para evitar duplicidade.
- `install-agent.sh` continua instalando o timer padrão (2×/dia); ao subir, o
  agente reaplica a agenda salva, então reinstalar não perde a configuração.
- A política por share continua só com `enabled` e `keep`. Frequência é global.
- A página Backups mostra a agenda atual, os horários calculados, o keep, a
  contagem e o último snapshot de cada share. Shares e Snapshots também exibem a
  agenda.

## Limites

- A agenda vale para todos os shares com política ativa; não há frequência
  diferente por share.
- Falhas em um share não impedem os demais (o runner já era assim).
- O antigo `samba-snapshot.sh` pode permanecer no disco, mas deixa de ser
  agendado.

## Testes

- `tests/test_versoes_schedule.py`: cálculo de horários para 1, 2 e 4 por dia,
  validação de faixa e horário, gravação do JSON/timer, remoção do cron e
  migração do legado.
- `tests/test_views.py`: POST da agenda com `per_day`/`first_time`.

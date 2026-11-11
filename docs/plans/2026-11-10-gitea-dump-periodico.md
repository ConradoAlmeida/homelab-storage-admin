# Dump periódico do Gitea

## Objetivo

O admin define, na página Backup do Gitea, uma agenda que gera o dump no servidor sozinha. A cópia para USB continua manual.

## Escopo

Entra a agenda (diária, semanal ou mensal), o timer systemd e a exibição da próxima execução. Fica de fora cópia USB automática, mudar `GITEA_KEEP`, commit, push e deploy.

## Decisões

- O timer chama só `homelab-gitea-backup@host.service`. Nunca um disco USB.
- A agenda nasce desligada. O formulário sugere diário às 05:00, mas nada é instalado até o admin marcar ativo e salvar.
- Arquivo próprio `/etc/homelab-backup/gitea-schedule.json` (600 root), separado de `gitea.json`. O status de uma execução não apaga a agenda.
- Timer fixo `homelab-gitea-backup.timer` em `SYSTEMD_DIR`, no mesmo formato de `homelab-arquivos-backup-<job>.timer`: `OnCalendar`, `Persistent=true`, `WantedBy=timers.target`.
- Ao ativar, gravar o stamp em `/var/lib/systemd/timers` antes do `enable --now`, para o `Persistent=true` não disparar um dump na hora. Ao desativar, `disable --now` e apagar o arquivo do timer.
- Se `SYSTEMD_DIR` não existir, gravar a agenda e não falhar. É o caso dos testes e de um host sem systemd.
- Periodicidade igual à dos jobs de arquivos: `daily`, `weekly` (0–6, `WEEKDAYS`) e `monthly` (dia 1–28). Horário `HH:MM` (`TIME_RE`). Rótulo em português: `diário 05:00`, `semanal (segunda) 05:00`, `mensal dia 1 05:00`.
- Retenção continua `GITEA_KEEP` (2). A página lembra que só ficam os últimos dumps. Sem campo novo de retenção.
- Validação no agente. A view só envia os campos, mostra `AgentError` e grava `AuditLog` `gitea_schedule_save`.
- Sem `shell=True`, sem comando livre e sem caminho vindo do browser no timer.
- Host sem container Gitea continua sem a página e sem alerta falso.

## Passos

- [x] Agente: ler/gravar a agenda, validar, calcular `OnCalendar`, `label` e `next_run`. `op_gitea_schedule_save` e o bloco `schedule` em `op_gitea_overview`. Registrar a op em `OPS`.
- [x] Cliente `core/agent.py`: `gitea_schedule_save`.
- [x] View, URL `gitea/schedule/` e formulário na página, com `form-grid`, `card` e `btn`. Mostrar o rótulo, a próxima execução e quantos dumps ficam no servidor.
- [x] Ajuda (`core/ajuda.py`), `docs/BACKUPS.md` e a pendência 5 de `docs/CONTEXTO.md`.
- [x] Testes de agente (agenda válida, horário inválido, timer escrito, desligar remove o timer) e da página (formulário, POST auditado, erro do agente).
- [x] `uv run pytest` dos testes de Gitea e da ajuda. O pytest local não chama `systemctl`.
- [x] Na VM `linux2024`, o laboratório cria o timer de verdade, confere e apaga.

## Verificação

A página mostra a agenda desligada por padrão. Salvar ativo grava o JSON e o timer `OnCalendar` certo. Desmarcar ativo remove o timer e não apaga os zips. Host sem Gitea não ganha alerta. Pytest local verde.

## Estado

2026-11-10: na VM `linux2024`, pytest 394 passed e `tests/lab` 8 passed. O timer de teste foi removido. Seguindo para commit e deploy no moya.

# Backups por estratégia

## Objetivo

A página Backups mostra cada estratégia num bloco próprio, com o nome curto no título. Dá para ver o estado e chegar na edição sem a grade de atalhos misturados.

## Escopo

- Entra: `templates/backups/index.html`, o contexto de `BackupIndexView`, a agenda de `versoes_snapshots` (ler e gravar os dois horários) e os testes da página.
- Fica de fora: trocar `tar`, `gitea dump`, restic ou `shadow_copy2` por outro motor. Não recriar o `samba_rsnapshot`. Não mudar o menu Snapshots além de linkar para ele.

## Decisões

- Quatro blocos, nesta ordem: `arquivos_targz`, `gitea_dump`, `restic_repo`, `versoes_snapshots`.
- Some a seção Atalhos e o botão "Novo job restic" do cabeçalho. Cópia fria, senha, snapshots restic, novo job e a tabela de discos ficam dentro de `restic_repo`.
- Reusar as classes que a página já usa (`section`, `section-head`, `file-table`, `btn`, `card`, `alert`, `tag`, `empty`). Sem CSS novo.
- `arquivos_targz` e `gitea_dump` continuam editados nas páginas que já existem. O bloco mostra o resumo e o link.
- `versoes_snapshots`: a política por share (ligado, keep) continua em `snapshot_policy_edit`. A agenda global (dois horários, minuto 05) passa a ser do agente, no arquivo de cron `VERSOES_CRON` (padrão `/etc/cron.d/samba-snapshots`). Padrão quando o arquivo não existe: 00:05 e 12:05. O keep 48 do script não muda nesta tarefa.
- O lead da página cita os quatro nomes. Sem recurso de Gitea ou de arquivos, o bloco correspondente não aparece. `restic_repo` e `versoes_snapshots` aparecem sempre.

## Passos

- [x] Reescrever `templates/backups/index.html` nos quatro blocos, sem atalhos.
- [x] `BackupIndexView` carrega `gitea_overview` (se o recurso existir), `snapshot_usage(include_size=False)` e a agenda de versões.
- [x] Agente: `versoes_schedule` e `versoes_schedule_save`. A gravação reescreve só a linha de cron `5 H1,H2 * * *`, com dois horários válidos e distintos. Cliente em `core/agent.py` e ramo no `core/demo_agent.py`.
- [x] POST na própria página de Backups salva a agenda e volta para `#versoes_snapshots`.
- [x] Testes: a página contém os quatro títulos e não contém "Atalhos" nem "Novo job restic". Sem os recursos, Gitea e arquivos continuam ausentes. Agenda inválida é recusada. Atualizar `test_backups_renders_empty_state_without_restic` e `test_escopo_do_moya_mantem_gitea_e_arquivos`.

## Verificação

`python -m pytest tests/test_views.py tests/test_gitea_backup_web.py tests/test_backup_credenciais_web.py -q --tb=line`

## Estado

Implementação concluída neste clone (Windows). Pytest pedido: **122 passed** (incluindo `tests/test_versoes_schedule.py`). `manage.py check` ok. Sem commit, push nem deploy. VM server-like não rodada neste host (sem virt-manager no Windows). A ajuda da página passou a usar os quatro nomes.

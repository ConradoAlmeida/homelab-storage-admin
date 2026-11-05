# Organizar só a pasta que já saiu da lista

Base: `main` atual (`3634868`), que já inclui `c90b6a1` e o painel **Organizar**. O `renameFolder` deixa nfo, capa e legenda na pasta antiga. O dono prefere não tocar no qBittorrent: pasta com torrent fica quieta, e a organização real só acontece depois de remover o torrent da lista mantendo os arquivos.

## Objetivo

A lista continua mostrando a pasta fora do padrão. Se ainda houver torrent, a linha explica o que fazer e não é movida. Sem torrent, o agente mescla como hoje.

## Escopo

- `core/qbittorrent.py` — `listar_pastas_fora_padrao` e `organizar_linhas`
- `templates/torrents.html` e, se a lista for preenchida no cliente, `static/js/downloads.js`
- `tests/test_qbittorrent.py`, `tests/test_views.py`
- `docs/ARMAZENAMENTO.md`, `docs/CONTEXTO.md`, `core/ajuda.py` se o texto ainda disser que o torrent ativo é renomeado pelo qBittorrent

Fora: `agent/homelab-storage-agent.py`, `_ESTADOS_INSTAVEIS`, `mv` no core, deploy, push.

## Decisões

- Linha com torrent ganha `torrent_organizavel`: verdadeiro só com progresso `>= 1` e estado `uploading`, `stalledUP`, `pausedUP` ou `stoppedUP`. O texto pronto:
  - organizável: "Torrent concluído — remova-o da lista (manter arquivos) e rode o organizador de novo."
  - qualquer outro estado: "Torrent em download — aguarde concluir."
- Sem torrent, a linha segue como está, inclusive `sem_ano` e o aviso de resíduo `>= 1 GiB`.
- `organizar_linhas` não chama `renameFolder`. Pasta com torrent vai para `ignorados`, com o mesmo texto. Pasta sem torrent continua no agente. `sem_ano` e resíduo não passam a mover o que hoje já é recusado.
- O checkbox dessa linha fica desabilitado. Um POST forjado com o nome também cai em `ignorados`, sem merge e sem rename.
- O card tem Feitos, Não feitos e Ignorados. A lista mostra a tag "torrent ativo — ignorada" e o texto da linha.
- `virt-manager` existe. A VM `linux2024` não exercita esse merge. O contrato é o pytest: conflito de tamanho e pasta de pelo menos 1 GiB com arquivo esparso, sem gravar gigabytes de verdade e sem instalar nada na VM.

## Passos

- [x] Lista com `torrent_organizavel` e `feedback`. Organizar só sem torrent; com torrent, `ignorados`.
- [x] Tag, texto e grupo Ignorados no painel. Checkbox desabilitado.
- [x] Docs. `uv run pytest`. Sem suíte da VM.
- [x] Commit `refactor(torrents): organizar só sem torrent ativo`. Sem push e sem deploy.

## Verificação

- Torrent concluído estável não gera chamada de rename nem de merge; o relatório o lista em ignorados com o texto de remover da lista.
- Torrent baixando usa o texto de aguardar. `sem_ano` e resíduo grande continuam em não feito.
- Pasta sem torrent ainda chama o merge.

## Estado

Implementado em 2026-11-04. Pytest: 324 passed, 6 skipped (lab). Sem push e sem deploy.

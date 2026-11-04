# Torrents: estado instável, pasta sem ano, resíduo grande

Base: `b14abbd` em `main`. O fluxo de lista e de pastas marcadas está em `docs/plans/2026-11-04-torrents-pastas-soltas.md`. Esta noite, apagar um torrent em `moving`/`checking*` fez o qBittorrent mexer na pasta de outro torrent com o mesmo nome de release (`The.Walking.Dead.Daryl.Dixon...[TGx]`): a `.incomplete` do torrent novo sumiu e sobrou uma pasta de 20,2 GB na raiz da biblioteca.

## Objetivo

Remover e apagar arquivos só com o torrent parado num estado estável. Pasta sem ano não vira pasta no Jellyfin. Pasta grande sem torrent aparece como resíduo antes e depois de organizar.

## Escopo

- `core/qbittorrent.py` — `acao()`, `listar_pastas_fora_padrao`, `organizar_linhas`
- `core/downloads.py` — `TorrentActionView` só repete o erro que `acao()` já devolve
- `templates/torrents.html` e a linha parcial, se a ação sair de lá
- `core/ajuda.py`, `docs/ARMAZENAMENTO.md`, `docs/CONTEXTO.md`
- testes em `tests/test_qbittorrent.py` e `tests/test_views.py`

Fora: `op_library_merge_dir`, allowlist nova, shell, deploy, push. A pasta de 20,2 GB que já existe não é apagada por este plano.

## Decisões

- Estados instáveis: `moving`, `checkingResumeData`, `checkingDL`, `checkingUP`, `checkingRI`, `checkingRD`, `metaDL`. `acao()` consulta o torrent e, para `delete` e `delete_files`, levanta `AgentError` com o texto "Torrent em movimentação/verificação; aguarde o estado estabilizar antes de remover." antes de qualquer POST de delete. Pausar e retomar seguem em qualquer estado.
- A view não chama o endpoint por conta própria. O botão Remover e o botão Apagar arquivos somem nesse estado e a linha mostra a mesma frase. Um POST manual recebe a frase de novo.
- `sem_ano` é calculado no servidor. A linha entra na lista com `sem_ano: true` quando o alvo não tem `(Ano)` e o título não está em `_OVERRIDES_TITULO`. `organizar_linhas` não chama `renameFolder` nem o agente: vai para não feito com "Sem ano no título e sem override". A página mostra a tag "sem ano". O campo que vier no POST não libera a pasta.
- Torrent mapeado em estado instável também não é renomeado. A linha cai em não feito com a mesma frase de movimentação. Renomear no meio do move é o mesmo tipo de corrida.
- Pasta sem torrent com tamanho de arquivos `>= 1 GiB` ganha aviso na lista ("Resíduo grande, sem torrent") e, se for marcada, o card repete esse aviso junto do resultado. O tamanho é a soma dos arquivos dentro da pasta, sem seguir link simbólico para fora. Isso não apaga a pasta.
- `virt-manager` existe neste desktop. A VM `linux2024` não tem qBittorrent, e `moving` não fica estável para um teste. O contrato é o pytest com o qB falso devolvendo esses estados e o teste garantindo que `/api/v2/torrents/delete` não foi chamado. Não instalar qBittorrent na VM. Não escrever que o laboratório exercitou um qB real.

## Passos

- [x] `acao()` recusa delete e delete_files nos estados instáveis; pause e resume passam.
- [x] Lista marca sem ano e resíduo grande; organizar não move esses casos nem torrent em move.
- [x] Botões de remoção somem no estado instável; tag "sem ano" e o aviso de resíduo aparecem na página.
- [x] Ajuda, `docs/ARMAZENAMENTO.md` e `docs/CONTEXTO.md`.
- [x] `uv run pytest` com os casos novos. Sem suíte da VM.

## Verificação

- Estado `moving` e cada `checking*` e `metaDL`: delete e delete_files devolvem a frase e não há POST de delete. `pausedUP` ainda remove.
- Pasta sem ano fica na lista com a tag e não entra em feito.
- Pasta de 2 GiB sem torrent mostra o aviso na lista e no card.
- Override com ano, como Colony, continua podendo ser organizado.

## Estado

Implementado em 2026-11-04. `uv run pytest`: 319 passed, 6 skipped (lab). Sem push, sem deploy.

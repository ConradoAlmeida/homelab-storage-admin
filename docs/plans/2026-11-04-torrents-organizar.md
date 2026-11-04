# Organizar séries a partir da página Torrents

## Objetivo

Um botão na página `/torrents` dispara, quando a pessoa pede, a mesma organização já validada no Pi: torrents concluídos da categoria `jellyfin` ganham pasta `Título (Ano)`. A página mostra um relatório curto do que foi renomeado, do que já estava no padrão e do que não foi feito.

## Escopo

- `core/qbittorrent.py` — a passada
- `core/downloads.py`, `core/urls.py`, `templates/torrents.html`
- `core/demo_agent.py` só se o demo precisar de um retorno fixo no cliente qB, não no agente
- `core/ajuda.py`, `docs/ARMAZENAMENTO.md`, `docs/CONTEXTO.md`
- testes em `tests/test_qbittorrent.py` e `tests/test_views.py`

Fora: executar arquivo em `/tmp`, senha no código, agente novo, `shell=True`, deploy, commit.

## Decisões

- O arquivo `/tmp/series_organizer.py` do Pi é a especificação desta passada. Não é o programa que o botão chama. `/tmp` some no reboot, é caminho arbitrário e o arquivo traz senha padrão. O painel usa `QBITTORRENT_URL`, `QBITTORRENT_USER` e `QBITTORRENT_PASSWORD`, que já existem. Não copiar senha para o repositório.
- A renomeação continua sendo `POST /api/v2/torrents/renameFolder` do qBittorrent. O container não move arquivo. `os.listdir` só vale se `save_path` estiver dentro de `JELLYFIN_ROOT`. Fora isso, o item vai para "não feito".
- Sem arquivo de checkpoint. Na segunda vez a pasta já igual ao alvo entra em "já no padrão".
- Entram torrents com `progress >= 1`, categoria `jellyfin`, `content_path` sem `/.incomplete/` e estado `stalledUP`, `uploading`, `queuedUP`, `pausedUP` ou `stoppedUP`. O último é o concluído do qBittorrent 5, que o painel já trata como concluído.
- Título: tirar domínio de indexador no começo, trocar `.` `_` `-` por espaço, achar ano `(19xx|20xx)` ou ano solto, cortar em temporada/qualidade. Overrides fixos: Colony (2016), O Eternauta (2025) para `L Eternauta` e `Eternauta`, Station Eleven (2021), The Walking Dead Daryl Dixon (2023), The Walking Dead The Ones Who Live (2024). Sem ano e sem override, o alvo é só o título limpo. Sem título, não renomeia.
- `oldPath` é o caminho relativo ao `save_path` se essa entrada existe no diretório; senão o diretório pai. Se antigo e novo são iguais, já está no padrão. Filme que já está certo cai aqui.
- Botão `Organizar séries` no `page-actions` do cabeçalho, `POST` com `data-confirm`: "Organizar as séries concluídas? As pastas passam a Título (Ano)." Sem Jellyfin ou sem cliente, o botão não aparece.
- O POST reexibe `/torrents` com um `card` "Organização". Três listas, em português: Feito (`antigo → novo`), Já no padrão (nome), Não feito (motivo). Contagem no topo. Lista vazia não vira seção. Falha de API ou de login no qBittorrent é `alert` e não apaga a tabela.
- Auditoria `torrent.organize` com o resumo numérico, sem a lista inteira.
- Demo (`STORAGE_ADMIN_DEMO=1`) devolve um relatório fixo de um item feito e um não feito, sem chamar a rede.

## Passos

- [x] Função pura de título/alvo e `organizar()` em `core/qbittorrent.py`, com `renameFolder` pelo cliente que já existe.
- [x] `POST /torrents/organizar/`, confirmação, card do relatório, botão só com Jellyfin e cliente disponível.
- [x] Ajuda, `docs/ARMAZENAMENTO.md` e `docs/CONTEXTO.md`.
- [x] Testes do título, do skip, do rename e do relatório na página. `uv run pytest`. Sem VM: não mexe em disco, Samba nem restic.

## Verificação

- Página demo: o botão pede confirmação e o card mostra feito e não feito.
- Teste com HTTP falso: um concluído vira `Título (Ano)`, um já certo entra em já no padrão, um sem título entra em não feito, caminho fora de `JELLYFIN_ROOT` não lista o diretório.
- Pytest local verde.

## Estado

Implementado em 2026-11-04. Pytest local verde; browser não verificado nesta sessão (sem runserver).

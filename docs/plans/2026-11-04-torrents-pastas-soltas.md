# Organizar uma biblioteca, só o que estiver na lista

## Objetivo

A pessoa escolhe Séries ou Filmes, vê quais pastas estão fora do padrão e organiza somente as que deixar marcadas. O relatório diz o que foi feito e o que não foi.

## Escopo

- `templates/torrents.html`, `core/downloads.py`, `core/urls.py`, `core/qbittorrent.py`
- `agent/homelab-storage-agent.py` e `core/agent.py` — mover pasta só dentro da biblioteca escolhida
- `core/demo_agent.py`, testes, ajuda, `docs/ARMAZENAMENTO.md`, `docs/CONTEXTO.md`

Fora: caminho livre, varrer `Season 01`, apagar vídeo, deploy, `sudo`.

## O que o disco mostrou

Em `/mnt/jellyfin/series`, às 20:21:

- `From (2022)` ficou com os 10 `.mkv`. A pasta `From (2022) Season 1 S01 ...` ficou só com `.jpg`, `.nfo`, `.srt` e `.png`. O `renameFolder` do qBittorrent move o arquivo do torrent e larga o resto.
- `Silo (2023) Season 1 S01 ...` continua com os `.mkv` e o nome da release. O torrent já tinha saído da lista. A passada atual só olha torrent que ainda existe.
- `Hart of Dixie (2011)` e `Sullivan's Crossing (2023)` já estão no padrão.

## Decisões

- Dois passos. O primeiro só lê a biblioteca escolhida e monta a lista. O segundo organiza só as linhas marcadas. Não há passada que renomeia tudo ao clicar.
- A escolha é uma biblioteca que o Jellyfin já tem, Séries ou Filmes. Sem pasta arbitrária.
- Entra na lista a pasta imediata cujo nome é diferente do alvo `Título (Ano)`. Hart of Dixie fica de fora. Cada linha mostra o nome atual, o nome proposto e se ainda existe torrent apontando para ela.
- A pessoa desmarca o que não quer. Organizar recebe essa lista e não varre de novo para incluir pasta nova.
- Linha com torrent ainda no qBittorrent usa `renameFolder`. Linha sem torrent é a pasta no disco: o agente renomeia ou mescla. O container monta `/mnt/jellyfin` só para leitura.
- A operação do agente aceita a biblioteca já conhecida e dois nomes de um segmento só, sem `/` nem `..`. Destino ausente: renomeia a pasta. Destino presente: move o que falta. Mesmo tamanho no destino é cópia e sai da origem. Tamanho diferente não é sobrescrito. A pasta antiga sai só quando fica vazia.
- O card final lista feito (`antigo → novo`) e não feito (arquivo diferente, ou a linha não estava marcada).
- Para valer no Pi, o agente novo precisa de `sudo ./install-agent.sh` e o painel de `./deploy.sh`. Isso fica para depois do plano fechado.

## Passos

- [x] Leitura da biblioteca escolhida e lista só das pastas fora do padrão.
- [x] Organizar somente as marcadas, com o agente para pasta sem torrent.
- [x] Ajuda e docs. `uv run pytest`. Sem VM.
- [x] Auditoria contra as decisões deste plano, antes do commit. Falhou uma decisão, corrigir e repetir o teste.
- [ ] Commit, push e deploy no Pi. Sem organizar a biblioteca real. `install-agent.sh` só entra se o `sudo` não pedir senha. Sem isso, o deploy do painel segue e o relatório diz que a operação nova do agente ainda não está no host.

## Verificação

- Séries mostra Silo e a pasta antiga de From, e não mostra Hart of Dixie.
- Desmarcar Silo deixa a pasta como está.
- Organizar a pasta antiga de From recolhe nfo, srt e capa do mesmo tamanho e remove a pasta vazia.
- Arquivo de tamanho diferente fica, e o relatório diz isso.
- Filmes é a outra biblioteca, com a mesma lista. Nada roda no Pi neste plano.

## Estado

Auditoria (diff, 2026-11-04):

1. Lista não inclui pasta já no padrão — `listar_pastas_fora_padrao` pula `nome == alvo` e `alvo is None`; teste `test_listar_pastas_ignora_padrao`.
2. Aplicar usa só nomes marcados — `organizar_linhas` itera `nomes_marcados` do POST, sem `listdir` da biblioteca; teste `test_organizar_linhas_só_marcadas`.
3. Torrent presente não renomeia fora do qBittorrent — ramo com `_renomear_pasta`; agente só sem entrada no mapa; teste `test_organizar_linhas_rename_com_torrent`.
4. `library_merge_dir` recusa `/`, `..` e biblioteca desconhecida — `_nome_pasta_biblioteca`, `_biblioteca_jellyfin_por_id`; testes no agente.
5. Tamanho diferente não apaga nem sobrescreve — ramo `conflitos` em `op_library_merge_dir`; teste `test_library_merge_nao_sobrescreve_tamanho_diferente`.
6. Sem senha, `.env` nem shell livre no diff — ok (campo de senha do admin na página de token é pré-existente).

Pytest: 307 passed, 6 skipped (2026-11-04). Próximo: commit, push, deploy Pi, smoke.

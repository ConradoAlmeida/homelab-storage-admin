# Título de release e resíduo que não barra

Base: `main` em `f74ee78`. Cinco pastas reais ficaram em não feito: Colony, See e Paradise só pelo aviso de 1 GiB; Daryl Dixon e The Ones Who Live porque `_DOMINIO_INDEXADOR` engole `.AM` de `.AMZN` e `.COM` de `.COMPLETE` e o alvo vira lixo sem ano.

## Objetivo

O prefixo de site só sai quando é um site de verdade. Pasta marcada com alvo `Título (Ano)` e sem torrent é mesclada mesmo passando de 1 GiB; o aviso continua na lista e no card. Sem ano continua recusa.

## Escopo

- `core/qbittorrent.py` — `_DOMINIO_INDEXADOR` e o `continue` de resíduo em `organizar_linhas`
- `tests/test_qbittorrent.py`
- `docs/ARMAZENAMENTO.md`, `docs/CONTEXTO.md`, `core/ajuda.py` — uma frase cada: resíduo grande não impede o merge quando o alvo tem ano

Fora: `agent/`, `_ESTADOS_INSTAVEIS`, política de sidecar, torrent ativo, commit, push, deploy, suíte da VM.

## Decisões

- O prefixo de indexador é `www.` ou `http(s)://` opcional, um único rótulo sem ponto, um TLD da lista atual e um separador (espaço, ponto, `_`, `-`) ou fim. `[\w.-]+` deixa de valer: ele atravessa o nome e casa `.am` / `.com` no meio do release.
- Casos que têm de continuar iguais: `www.UIndex.org - …` e `www.exemplo.org …` ainda perdem o site; `eztv.re` no meio ou entre colchetes não come o título.
- `organizar_linhas` não recusa mais por `_AVISO_RESIDUO`. A lista segue preenchendo `aviso`. No feito, se o agente também devolver motivo, os dois entram no `aviso` do card, resíduo primeiro, separados por `. `. Sem motivo do agente, fica só o resíduo.
- `sem_ano` continua em não feito com "Sem ano no título e sem override", sem chamar o merge. Se a pasta também for grande, o aviso vai no campo `aviso`, não no `motivo`.
- Vídeo de tamanho diferente, torrent ativo e pasta sem ano não mudam.
- `virt-manager` existe. A VM `linux2024` não exercita o parser. O contrato é o pytest, com o limiar de resíduo reduzido no teste. Sem gravar gigabytes e sem instalar nada na VM.

## Testes

Parametrizar `alvo_da_pasta` com estes pares, além dos que já passam:

- `The.Walking.Dead.Daryl.Dixon.S01.COMPLETE.1080p.AMZN.WEB-DL.DDP5.1.H.264-NTb[TGx]` → `The Walking Dead Daryl Dixon (2023)`
- `The.Walking.Dead.The.Ones.Who.Live.S01.COMPLETE.1080p.WEB-DL.DDP5.1.H264-BEN.THE.MEN` → `The Walking Dead The Ones Who Live (2024)`
- `www.UIndex.org - Paradise-2025-S01 1080p WEBRip 10bit EAC3 5 1 x265-iVy` → `Paradise (2025)`
- `Colony.S01.1080p.x265-ZMNT` → `Colony (2016)`
- `See (2019) Season 1 S01 (1080p ATVP WEB-DL x265 HEVC 10bit EAC3 5.1 t3nzin) REPACK` → `See (2019)`
- `From (2022) Season 1 S01 (1080p AMZN WEB-DL x265 HEVC 10bit EAC3 5.1 t3nzin)` → `From (2022)`
- `Station.Eleven.S01.1080p.WEBRip.x265[eztv.re]` → `Station Eleven (2021)`

Trocar `test_organizar_linhas_recusa_residuo_grande`: pasta `Show (2020) Season 1 S01` acima do limiar, sem torrent, marcada, chama `mesclar` e cai em feitos com `aviso` `Resíduo grande, sem torrent`.

Acrescentar:

- a mesma pasta grande sem ano (`Serie Nova S01 1080p`) não chama `mesclar`; motivo `Sem ano no título e sem override`; `aviso` é o resíduo
- a pasta `The.Walking.Dead.Daryl.Dixon.S01.COMPLETE.1080p.AMZN.WEB-DL.DDP5.1.H.264-NTb[TGx]` grande e sem torrent chama `mesclar` com destino `The Walking Dead Daryl Dixon (2023)` e cai em feitos com o aviso de resíduo

## Passos

- [x] Apertar `_DOMINIO_INDEXADOR` para um rótulo só.
- [x] Tirar o `continue` que recusa resíduo; manter o aviso no card, junto do motivo do agente quando os dois existirem.
- [x] Testes dos nomes reais e dos dois fluxos de organizar (com ano / sem ano).
- [x] Frase em `docs/ARMAZENAMENTO.md`, `docs/CONTEXTO.md` e `core/ajuda.py`.
- [x] `uv run pytest`. Sem VM, sem commit, sem push, sem deploy.

## Verificação

- Os sete nomes acima resolvem para o alvo da tabela.
- Pasta grande com ano é mesclada e o card leva o aviso.
- Pasta grande sem ano não é mesclada.
- `www.exemplo.org Station Eleven S01` continua `Station Eleven (2021)`.

## Estado

Implementação concluída. `_DOMINIO_INDEXADOR` com rótulo único e lookahead de separador; resíduo não barra merge quando há ano; pytest 336 passed, 6 skipped (lab).

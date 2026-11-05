# Colchetes e tags de release no título

Base: `main` em `ac48b92`. O filme `Everything Everywhere All At Once (2022) [1080p] [WEBRip] [5.1] [YTS.MX]` foi marcado feito e a pasta ficou `Everything Everywhere All At Once [1080p] [WEBRip] [5 1] [YTS MX] (2022)`. O corte só vê `1080p` e `WEBRip` depois de um espaço. Entre colchetes o corte não dispara, o ano sai do meio e o resto da release vira o alvo. Como o nome atual passa a ser igual a esse alvo, a listagem seguinte esconde a pasta.

## Objetivo

Alvo de filme e série nesse formato é `Título (Ano)`, no mesmo padrão de `Coco (2017)`. A pasta já renomeada errado volta para a lista, com o alvo limpo. Os nomes que já passam no pytest continuam iguais.

## Escopo

- `core/qbittorrent.py` — `_limpar_titulo` e `_CORTE_TITULO`
- `tests/test_qbittorrent.py`
- uma frase em `docs/ARMAZENAMENTO.md`, `docs/CONTEXTO.md` e `core/ajuda.py`

Fora: `agent/`, resíduo, torrent ativo, merge de sidecar, commit, push, deploy, suíte da VM.

## Decisões

A limpeza fica nesta ordem:

1. Tirar o prefixo de site como hoje (um rótulo só).
2. Ler o ano que está entre parênteses ou colchetes, `(2022)` ou `[2022]`, em qualquer posição. Esse valor ganha do ano solto.
3. Apagar os demais `[...]`.
4. Apagar os demais `(...)`. Não são parte do padrão `Título (Ano)`.
5. Trocar `[._-]+` por espaço, como hoje.
6. Cortar no primeiro token de release que sobrou. A lista atual continua e passa a valer também depois da troca de ponto e hífen: `WEB DL`, `H 264`, `H 265`, `X 264`, `X 265`, `DDP`, `EAC3`, `AAC`, `HDR`, `REPACK`, `PROPER`, `10bit`. `5.1` e `5 1` não são título; se não caíram no colchete, o corte de qualidade anterior a eles já os descarta.
7. Sem ano no passo 2, usar o último ano solto que restou no texto já cortado. Assim `Paradise 2025 S01` continua `Paradise (2025)` e `Blade Runner 2049 (2017)` não perde o `2049`, porque o ano do parêntese foi escolhido no passo 2.

Pasta cujo nome já é o alvo limpo não entra na lista. A pasta torta entra, e organizar chama o merge para o alvo limpo.

## Testes

Manter os pares que já existem em `test_alvo_da_pasta_limpa_titulo`. Acrescentar:

- `Everything Everywhere All At Once (2022) [1080p] [WEBRip] [5.1] [YTS.MX]` → `Everything Everywhere All At Once (2022)`
- `Everything Everywhere All At Once [1080p] [WEBRip] [5 1] [YTS MX] (2022)` → `Everything Everywhere All At Once (2022)`
- `Blade Runner 2049 (2017) [1080p] [WEBRip]` → `Blade Runner 2049 (2017)`
- `Don't Breathe (2016)` → `Don't Breathe (2016)`
- `Movie Name [2022] 1080p WEBRip` → `Movie Name (2022)`
- `Movie Name (1080p) (WEBRip) (2022)` → `Movie Name (2022)`
- `Movie Name WEB-DL 2019` → `Movie Name (2019)`
- `Show.Name.S01E01.1080p.WEB-DL.H.264-GROUP` → alvo `Show Name` (sem ano; organizar não mescla)

`listar_pastas_fora_padrao`: a pasta torta do EEAAO aparece com esse alvo limpo; uma pasta já chamada `Everything Everywhere All At Once (2022)` não aparece.

`organizar_linhas`: a pasta torta, sem torrent, chama `mesclar` com destino `Everything Everywhere All At Once (2022)`.

## Passos

- [x] Limpar colchetes, parênteses que não são o ano, e os tokens partidos por ponto ou hífen.
- [x] Testes dos nomes acima, da listagem e do merge.
- [x] Frase nos três docs.
- [x] `uv run pytest`. Sem VM, sem commit, sem push, sem deploy.

## Verificação

- Os dois nomes do EEAAO resolvem para `Everything Everywhere All At Once (2022)`.
- `Blade Runner 2049 (2017)` conserva o `2049`.
- `Don't Breathe (2016)` e os pares antigos continuam iguais.
- A pasta torta entra na lista e o merge usa o alvo limpo.
- Pasta sem ano continua sem merge.

## Estado

Concluído. `_limpar_titulo` reordenada; `_CORTE_TITULO` ampliada; passo 7 também lê ano solto após o corte quando o release vem antes (ex. `WEB-DL 2019`). `346 passed`, 6 skipped (lab).

# Automatizar o que ainda é manual no apps-sync

## Objetivo

Tirar do operador (e do agente) o trabalho repetitivo em volta do reconciliador.
Hoje cada app nova ou bloco especial custa SSH em cada host, edição do `apps.env`
e do `Caddyfile` como root, `--apply`, e conferência manual com `curl`, `dig` e
`docker ps`. A meta é: **o env declara, o script entende o host e aponta/ajusta o
que diverge**, sem bloco escrito à mão no servidor.

## Escopo

- Entra: env versionado no repo, flags para os casos especiais, fragmentos
  versionados, comando de diagnóstico (`--doctor`) e de descoberta
  (`--descobrir`).
- Não entra: LLM no caminho do `--apply` (o resultado tem que ser determinístico
  e reproduzível); descoberta que escreve sozinha no env; edição pela UI.
- Não muda: perfis `pi`/`moya`, quarentena, confirmações, allowlist do agente.

## Decisões

- **Fonte da verdade sai do `/etc` e entra no repo**: `deploy/pi/apps.env` e
  `deploy/moya/apps.env`. O `host.env` aponta `APPS_ENV_PATH` para o arquivo do
  checkout, então `deploy.sh` (que já faz `git pull`) deixa o env no mesmo commit
  do script. App nova vira um commit revisável, não um `sed` no servidor. A cópia
  em `/etc` fica guardada como backup da migração.
- **`dir=-` deixa de exigir `manual`**: só significa "sem stack local" (caso
  `moya-weather`), então a rota volta a ser gerada e o check de container é
  pulado com aviso.
- **Flags novas** (quinta coluna, separadas por vírgula, sem quebrar as atuais):
  - `redir=<destino>` → na raiz do site; `redir=<origem>-><destino>[@código]`
    para outro caminho/código (padrão 302). Cobre os dois Pi-holes.
  - `snippet=<nome>` → embute `deploy/<perfil>/snippets/<nome>.caddy` dentro do
    bloco gerado, entre o TLS e o `reverse_proxy`. É o fim do bloco escrito à
    mão no host: o fragmento é versionado, testado e aplicado pelo script.
  - `manual` continua existindo só como escape hatch e continua avisando no
    dry-run quando não tem bloco correspondente no `Caddyfile`.
- **`--doctor`** (somente leitura) responde "o que está fora do lugar?" sem eu
  montar laço de `curl`/`dig`/`docker`:
  - `apps.caddy` diferente do renderizado; `import apps.caddy` ausente;
    marcador antigo ou bloco manual duplicando app gerada;
    `snippet` declarado e inexistente.
  - DNS: nome faltando, IP errado, entrada exata fora do env (no arquivo gerado
    e no `dns.hosts` do `pihole.toml`).
  - Containers: app sem container, container em outra pasta (caso Gitea),
    upstream com porta diferente da publicada, upstream recusando conexão.
  - Pastas: declarada e ausente, órfã fora do env, quarentena não vazia.
  - Cada achado com o comando/edição que corrige; código de saída 1 se houver
    erro (serve de check em CI).
- **`--descobrir`** (somente leitura) parte do host, não do env: varre as pastas
  permitidas e os containers com rótulo compose, e imprime a linha pronta para
  revisar e commitar, com `key`, `fqdn` sugerido, porta publicada e pasta real.
  Nunca escreve no env — o commit é a aprovação.

## Passos

- [x] 1. Mover o env para `deploy/<perfil>/apps.env` nos dois hosts; ajustar
      `APPS_ENV_PATH` no `host.env`, o `deploy.sh` e o caminho mostrado em
      Configuração.
- [x] 2. Implementar `redir`, `snippet` e `dir=-` livre; criar os fragmentos
      (`snippets/jellyfin.caddy`) e migrar os quatro blocos manuais de hoje
      (Pi-hole do Pi, Jellyfin do Pi, Pi-hole do moya, weather do moya).
- [x] 3. `--doctor` com os checks acima e saída em seções.
- [x] 4. `--descobrir` com sugestão de linha + explicação.
- [x] 5. Testes em `tests/test_apps_sync.py` para renderização das flags,
      snippet ausente, `redir` inválido, `doctor` num ambiente fake e
      `descobrir` com stack não declarada (29 testes).
- [x] 6. Aplicar nos dois hosts, bancada de VM nos dois perfis, docs
      (`REDE`, `INSTALACAO`, `CONTEXTO`) e plano.

## Verificação

- `apps.caddy` dos dois hosts sai igual ao renderizado, sem bloco manual no
  `Caddyfile` além de `import apps.caddy` e dos snippets.
- `--doctor` limpo nos dois hosts; com um desvio plantado (porta trocada, pasta
  movida, nome sem DNS) ele acusa e o conserto sugerido resolve.
- `--descobrir` lista as 12 apps do moya como já declaradas e uma stack nova
  plantada como candidata.
- `--apply` idempotente; 475 testes + bancada verdes nos dois perfis.

## Resultado

- `deploy/{pi,moya}/apps.env` versionados; o script lê `deploy/<perfil>/apps.env`
  a partir da própria pasta e o `host.env` ficou só com o caminho para a página
  Configuração. A cópia antiga em `/etc` virou `apps.env.bak-20261115`. O
  `deploy.sh` não mudou: ele já fazia `git pull`, que é o que atualiza o env.
- Caddyfile dos dois hosts agora tem só snippets, o bloco `.lan` (Pi) e
  `import apps.caddy`: Pi-hole, Jellyfin e weather saem de flag.
- Pi: `pihole` com `redir=/admin/` (302 conferido), `jellyfin` com
  `snippet=jellyfin` (403 em `/videos/1/stream` com header CF e 200 na página).
- moya: `pihole` com `redir=/admin` e `weather` com `dir=-` (rota gerada).
- `--doctor` limpo nos dois (Pi precisa de sudo para o `caddy validate` ver o
  token; sem sudo ele avisa em vez de errar). `--descobrir` lista as 12 do moya
  como já declaradas.
- A pasta `/home/conrado/portainer` foi removida: era a única sobra do serviço
  apagado e aparecia como app fora do env no estado.

## Estado

Concluído em 2026-11-15; testes e bancada de VM verdes nos dois perfis.

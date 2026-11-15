# Rotinas do dia a dia

**Um arquivo por host**: `deploy/<perfil>/apps.env`. Dele saem a rota no Caddy,
o DNS, o botão Serviços do painel e, no moya, os cards do portal. Nada de
editar `apps.caddy`, `services.ini` ou HTML do portal à mão.

Atalhos usados abaixo:

| Item | Pi | moya |
|---|---|---|
| Repo | `/opt/stacks/homelab-storage-admin` | idem |
| Env | `deploy/pi/apps.env` | `deploy/moya/apps.env` |
| Dados (`DATA_DIR`) | `/mnt/nas/apps/homelab-storage-admin/data` | `/opt/stacks/homelab-storage-admin/data` |
| `services.ini` (gerado) | `DATA_DIR/services.ini` | `DATA_DIR/services.ini` |
| Lista do portal (gerada) | — | `/var/lib/homelab-storage-admin/apps-portal.ini` |
| Quarentena | `/opt/stacks/_removidos` | `/home/conrado/_removidos` |
| Nomes | `*.conradhub.com` (wildcard) | `*.local` (uma entrada por nome) |

## 1. Adicionar uma app Docker

1. **Stack no host**: pasta em `/opt/stacks/<key>` (ou onde o projeto já vive),
   com `compose.yaml`, e **porta publicada** no host:
   `- "127.0.0.1:8097:8000"` (moya) ou `- "192.168.0.150:8097:8000"` (Pi).
   Suba com `docker compose up -d`.
2. **Linha no env** do perfil, no repo. Se a stack já está no ar,
   `bash scripts/stacks/apps-sync.sh [--perfil moya] --descobrir` imprime a
   linha pronta (rota, upstream, `atalho=`, `icone=`/`grupo=` no moya); revise
   o `atalho=` e cole:

   ```
   key|fqdn|upstream|dir|flags
   minha-app|minha-app.conradhub.com|192.168.0.150:8097|/opt/stacks/minha-app|atalho=painel,nome=Minha App,descricao=Resumo curto,cor=#38bdf8
   ```

   `upstream` é a porta publicada; `dir` é a pasta do compose. Sem `atalho=` a
   app tem rota e DNS, mas não aparece no painel nem no portal.
3. **Commit + push** e, no host, `git pull` +
   `sudo bash scripts/stacks/apps-sync.sh [--perfil moya] --apply`.
   Isso gera `apps.caddy`, o DNS e os atalhos, e valida a configuração. No Pi o
   DNS é wildcard: nada a fazer.
4. **Conferir**: `--doctor`, e uma rota de verdade:
   `curl -skI --resolve minha-app.conradhub.com:443:127.0.0.1 https://minha-app.conradhub.com/`
   (no moya: `curl -s -o /dev/null -w '%{http_code}' -H 'Host: minha-app.local' http://127.0.0.1/`).
   O card novo aparece ao recarregar o painel (e o portal, no moya).

Firewall só entra se a porta for acessada fora do Caddy: no Pi, UFW pela
página Rede; no moya não há UFW.

## 2. Remover uma app

1. Apague a linha do env, commit e `git pull` no host.
2. `sudo bash scripts/stacks/apps-sync.sh [--perfil moya] --apply --prune-containers`
   → para os containers com `docker compose down` (sem `-v`).
3. `--prune-data` (junto com o passo 2) → move a pasta para a quarentena,
   nunca apaga. Revise e apague depois.
4. Os atalhos somem sozinhos: a próxima execução reescreve `services.ini` e a
   lista do portal sem a app.
5. Volume nomeado: o script **não** apaga. Veja `docker volume ls` e decida.
6. `--doctor` deve sair sem erro; o estado (`apps.aplicados`) deixa de citar a app.

## 3. Atalhos (painel e portal)

Tudo é flag na linha da app:

| Flag | Para quê |
|---|---|
| `atalho=painel` | botão Serviços do Storage Admin |
| `atalho=portal` | card no portal do moya |
| `atalho=painel+portal` | os dois |
| `atalho=nao` (ou ausente) | rota e DNS, sem atalho |
| `nome=`, `descricao=` | texto exibido (sem vírgula) |
| `cor=#rrggbb`, `icone=<slug>` | cor da borda e ícone (portal; sem SVG cai na inicial) |
| `grupo=services\|infrastructure\|tools` | seção do portal |

Ordem = ordem das linhas no env. Mudou a flag? Commit, `git pull`,
`--apply` (só reescreve o que mudou) e recarregue a página. O `apps-sync`
preserva dono e permissão do arquivo; se ele não tinha o cabeçalho de gerado,
guarda `services.ini.bak-<data>` antes de assumir.

Link para algo que **não** é app daqui (outro host, site externo): declare uma
linha com `dir=-` e o `upstream` do destino; ela ganha rota, DNS e atalho como
qualquer outra (`moya-weather` é assim).

## 4. Atualizar o código do Storage Admin

1. No desktop: `uv run manage.py check`, `uv run pytest` e, se mexeu em
   `frontend/src.css`, `uv run manage.py tailwind build` (o `kit.css` é
   versionado; o CI compila e compara, então esquecer o build reprova).
2. Atualize o doc da área e `docs/CONTEXTO.md` no mesmo commit.
3. Commit + push (`main` protegido; o check `test` precisa passar).
4. No host: `cd /opt/stacks/homelab-storage-admin && ./deploy.sh`
   — `git pull` + build + recreate. Migrações rodam no entrypoint; no Pi o
   deploy avisa quando precisa de `sudo` (config do qBittorrent). O script só
   termina com `OK: …/login/ -> 200` quando o app responde (até 90 s); sem
   resposta ele sai 1 e imprime o comando de `logs`. Se o pull mexeu no
   `apps.env` e o `--apply` não rodou, ele avisa com o comando pronto. No fim
   roda o `--doctor` e mostra `erros`/`avisos`: desvio de rota, DNS ou atalho
   aparece aqui, mas não reprova o deploy (o app está no ar).
5. Se `agent/` mudou: `sudo ./install-agent.sh` (o deploy avisa; ele não instala).
6. Confira `/saude/`, `/sistema/logs/` e a página alterada. Mudança em caminho
   crítico pede bancada de VM (`docs/VM_TESTES.md`).

## 5. Outras rotinas

| Rotina | Como |
|---|---|
| Nova imagem de um container | `cd <pasta> && docker compose pull && docker compose up -d`. Gitea: `gitea dump` antes |
| Mudar porta de uma app | editar `compose.yaml` + `upstream` no env, commit, `--apply`, `--doctor` |
| Trocar o nome (fqdn) | editar o `fqdn` no env, commit, `--apply` (o DNS antigo sai) |
| Renomear a `key` | nova linha + `--apply`; a antiga entra em `fora do env` e pede prune |
| Restaurar app da quarentena | `mv` a pasta de volta, linha no env, `--apply` |
| Backup restic | Backups → wizard/jobs; testar restore de um arquivo por mês; `homelab-restic-check.timer` |
| Cópia fria (USB) | Backups → Cópia fria; o disco é ejetado no fim |
| Atualizar o sistema | Sistema → Verificar/Instalar atualizações (Pi); reboot planejado |
| Token da Cloudflare | trocar `/opt/stacks/caddy/cloudflare.token` e `docker restart caddy` (só Pi) |
| Backup do Caddy/Gitea | `/home/conrado/backups/<data>/` no moya: `Caddyfile`, `caddy_data.tar.gz`, `gitea-dump`, `rollback-*.sh` |
| Usuários | Pi: página Usuários (Samba local). moya: Credenciais; a seção fica bloqueada |
| Share/snapshot | Shares/Snapshots (os dois hosts); política e agenda em Backups |
| Firewall | Rede → UFW (Pi), preservando SSH; auditar depois |
| DNS do moya | nunca editar Local DNS do Pi-hole; o arquivo gerado manda |
| Portal do moya | cards vêm do env; mudou o código do portal, `docker compose up -d --build` em `/home/conrado/moya_portal_interno` |
| Reinstalar/trocar host | `sudo ./install-agent.sh` + `host.env` + `./deploy.sh` (docs/INSTALACAO.md) |
| Limpar backups datados | `*.bak-*` são cópias de uma vez: `apps.env` volta do git e `services.ini` do `--apply`, então podem sair. `host.env.bak-*` é a única cópia da config anterior — guarde a última |
| Ver o que está declarado | Sistema → Rotas e atalhos (rota, atalho, grupo e se está aplicado) |
| Verificação semanal | `pytest`, `--doctor` nos dois, `docker compose ps`, `/saude/` |

## Verificação rápida

```bash
# rotas e DNS (moya)
for n in moya-git moya-storage; do
  printf '%-20s %s\n' "$n" "$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $n.local" http://127.0.0.1/)"
done

# diagnóstico sem escrever
bash scripts/stacks/apps-sync.sh --perfil moya --doctor
sudo bash scripts/stacks/apps-sync.sh --doctor   # no Pi: valida o TLS
```

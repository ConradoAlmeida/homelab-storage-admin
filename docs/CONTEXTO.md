# Contexto — Homelab Storage Admin

Documento de retomada. Última atualização: **2026-11-01**.

Histórico da sessão de 27-29/10: [SESSAO-2026-10-29.md](SESSAO-2026-10-29.md).

## Estado atual

| Item | Valor |
|---|---|
| Versão em produção | `08cbd40` (qBittorrent na rede do Pi) |
| Último deploy | 01/11/2026, Pi |
| Testes | `264 passed` no Linux, sem a suíte `lab` |
| Container | `homelab-storage-admin` |
| Pi | `/opt/stacks/homelab-storage-admin`, `192.168.0.150:8060` |
| moya | mesmo path, `127.0.0.1:8060` via Caddy em `moya-storage.local` |
| Perfil | `/etc/homelab-storage-admin/host.env` |
| Agente | `homelab-storage-agent` (systemd, root, socket Unix) |
| Repositório | `https://github.com/ConradoAlmeida/homelab-storage-admin.git` |

## O que está pronto

- Usuários/grupos Samba, shares, snapshots e navegador read-only de arquivos.
  A política de snapshot também se configura e se edita pela UI, inclusive em
  share que nasceu sem ela. Desativar não apaga os snapshots já criados.
- No homelab o login centraliza a casa, menor, e o nome Conrado Homelab, um pouco
  maior, os dois em roxo. A barra repete essa marca, com a casa no tamanho de
  um ícone. Os ícones do navegador usam só a casa. No moya
  (`CREDENTIALS_MANAGE_USERS=1`) continua o wordmark Moya.
- No host com Jellyfin, a página Torrents envia um link magnético para uma
  biblioteca dele. O qBittorrent continua em container, na rede do Pi, para o
  handshake dos peers não passar pela bridge. A WebUI fica na 8090; a 8080 do
  host não muda. Com o UFW ativo, 6881/tcp e 6881/udp ficam liberadas e a
  8090 só aceita a rede Docker. O UPnP fica ligado. A lista mostra as taxas de
  download e de upload. A busca, a pasta e o estado ficam numa linha,
  com atalhos para todos, ativos, concluídos e com erro. O cabeçalho da
  coluna ordena a lista. Pausar só aparece enquanto
  baixa; no concluído ficam Remover e Apagar arquivos. Sem o Jellyfin, a página
  não aparece. `POST /api/torrents/` repete esse envio com Bearer.
  Token vazio no banco desliga a rota. A categoria no qBittorrent é
  sempre `jellyfin`. Hash já presente na lista responde `409`. O token fica
  legível no banco do painel. O `host.env` só grava o primeiro valor. O
  administrador cria, consulta e troca na página Torrents com a senha da
  própria conta. Sem token, o botão é Criar token. O mesmo registro aparece
  em `/admin`. Quem acompanha o término do arquivo faz isso pelo SMB, na pasta da
  biblioteca: stat remoto e comparação de tamanho, o mesmo critério dos transfers.
- Discos, SMART standby-safe, RAID/Btrfs e métricas ao vivo.
- Backups:
  - jobs restic por disco, com agenda, retenção e verificação semanal;
  - **backup local de arquivos** com jobs independentes (fontes, agenda,
    retenção, restore verificado, cópia para USB);
  - backup do Gitea (dump + USB, hash conferido), **validado manualmente**;
  - cópia fria USB implementada, dependente de repo primário.
- Jobs em produção:
  - **Credenciais** — banco + `.env`, diário 03:30, 30 dias;
  - **Dados dos apps** — 16 fontes, manual, sem timer.
- Página **Rede**: firewall UFW editável (ativar/desativar, adicionar/remover
  regras), interfaces, rotas, portas e containers.
- Card **Saúde** no Dashboard: discos, backups, containers e pendências.
- **Containers** (`/containers/`): Docker ou Podman, estado, portas, iniciar,
  parar, reiniciar e logs; sem remover nem executar comandos. O container do
  painel é protegido contra parada/reinício pela própria UI.
- Login pelo Credenciais no moya, com `CREDENTIALS_MANAGE_USERS=1` e
  break-glass local. No Pi, sem `CREDENTIALS_URL`, o login é local.
- Textos, ajuda e rotas de Gitea, backup local de arquivos e gestão pelo
  Credenciais só aparecem quando o host tem o recurso. O código continua o
  mesmo nos dois ambientes.
- Passe completo de UI: `ui.css` com cabeçalho, seções, cards, avisos, botões,
  tabelas, chips, métricas, ações e formulários padronizados.
- **Ajuda contextual** em todas as páginas autenticadas: o botão **Ajuda desta
  página** no topo abre um painel com um caso de uso (**No dia a dia**) e
  capítulos por funcionalidade da própria página, usando `<details>` nativo e
  sem JavaScript.
- **Novo layout de painel de operação** (branch `ui/layout-telas`, merge `76dc5f2`):
  visual compacto, rotas/firewall em tabelas, status com ponto e ações como texto.
- Modo demo (`STORAGE_ADMIN_DEMO=1` + `DEBUG=1`) para pré-visualizar a UI sem host.
- Dashboard lista jobs de arquivos e jobs restic em seções separadas.
  Os tamanhos dos shares chegam depois do HTML, com cache de 3 minutos no
  agente; a página Shares usa o mesmo caminho.
- Backups do Gitea e do Credenciais validados com restore de teste.
  O Gitea para pendrive também foi validado manualmente; não retestar sem
  mudança no fluxo de dump/cópia USB.

## Decisões que não devem ser revertidas sem conversa

1. **Código compartilhado Pi + moya.** Feature não se remove para atender um host.
2. **Credenciais é o IdP do moya.** Sem OIDC; o Storage Admin só consome.
3. **Acesso ao Storage Admin é binário** (tem ou não tem concessão `storage`).
4. **Portal Interno é público** e não passa por login.
5. **Restic só em disco externo.** O disco do sistema/dados é recusado; sem disco
   os jobs ficam `skipped`, não falham.
6. **Cópia fria exige repo primário.**
7. **Gitea é manual** (dump + USB) até haver RAID1/discos.
8. **ACLs são relatório/sugestão**, sem correção automática.
9. **UI consistente é requisito**, não preferência.
10. **Nada de shell livre no agente.**

## Pendências, em ordem

1. **Deploy no Pi** — responsabilidade do Conrado; o código já está em `main`.
2. **Discos externos**: criar repo restic, jobs, cópia fria, `restic check` e
   restore de teste. Bloqueado por hardware.
3. **Firewall**: a UI já gerencia o UFW; decidir quando ativar no moya/Pi.
   O alerta "Firewall inativo" continua real até a ativação.
4. **Gitea**: automatizar o dump quando houver RAID/disco; apagar os arquivos
   USB antigos inválidos.
5. **Job “Dados dos apps”**: manual por decisão; rodar + “Backup para USB”
   quando quiser cópia fria.
6. **RAID1**: quando os discos chegarem, revisar retenção e cópia externa.
7. **Containers fase 2** (opcional): stacks Compose e CPU/RAM por container.

## Testes em VM

Roteiro completo para Ubuntu Server 26.04: [`docs/VM_TESTES.md`](VM_TESTES.md).

- setup do host: `scripts/vm/setup-ubuntu-2604.sh`
- suites dos dois apps: `scripts/vm/run-unit-tests.sh`
- smoke somente leitura: `scripts/vm/smoke-moyaserver.sh`
- E2E de identidade/Samba: no repo do Credenciais, `docs/E2E_VM.md`

## Como retomar

```bash
# no PC
cd C:\Users\Conrado\development\homelab-storage-admin-credenciais

uv run manage.py check
uv run pytest

git add -A && git commit -m "feat: ..."
git push origin feat/credenciais-login:main
```

```bash
# no servidor (Pi ou moya)
cd /opt/stacks/homelab-storage-admin
./deploy.sh

# se agent/ mudou
sudo ./install-agent.sh
```

> O deploy no Pi é feito pelo responsável; não execute sem pedido explícito.

Diagnóstico:

```bash
sudo systemctl status homelab-storage-agent
docker logs homelab-storage-admin --tail 100
set -a; . /etc/homelab-storage-admin/host.env; set +a
docker compose -f docker-compose.yml -f "$COMPOSE_OVERLAY" ps
```

## Armadilhas conhecidas

- **Sem repo restic** não há snapshots restic; a UI mostra “aguardando disco”.
- **Não rode o app antigo** `moya-storage-admin` junto com este.
- **No Pi**, `data` é symlink para `/mnt/nas/apps/homelab-storage-admin/data`;
  num clone novo, recrie o symlink antes de rodar `manage.py` no host.
- **`CREDENTIALS_MANAGE_USERS=1`** só bloqueia identidade; não confunda com
  remoção de features.
- **O overlay do Compose** vem do `host.env`; sem ele o app fica fora da rede.
- **Sessões do Credenciais** precisam estar válidas: o app revalida a cada request.
- **UI**: qualquer página nova sem `page-head`/`section-head`/`card` quebra o
  padrão e deve ser corrigida.
- **Worktree antigo** em `C:\Users\Conrado\development\homelab-storage-admin`
  (detached, 46 commits atrás) ainda tem WIP de acesso/desconexão SMB, não
  integrado. Patch de segurança em
  `C:\Users\Conrado\Documents\wip-acesso-smb-20261028.patch`. Decidir se integra
  ou descarta antes de remover o worktree.
- **Backups**: nunca apontar job restic para o disco do sistema/dados; o wizard
  recusa de propósito.
- **Job “Dados dos apps”** não tem timer; não estranhe o status “desativado”.

## Documentos irmãos

- `README.md` — operação e comportamento.
- `AGENTS.md` — regras para agentes/automação.
- Credenciais: `C:\Users\Conrado\Documents\moya_credencials_app`
  (`docs/CONTEXTO.md`), fonte de identidade do moya.

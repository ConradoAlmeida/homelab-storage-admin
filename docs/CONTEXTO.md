# Contexto — Homelab Storage Admin

Documento de retomada. Última atualização: **2026-10-28**.

## Estado atual

| Item | Valor |
|---|---|
| Versão em produção | `76dc5f2` (layout de painel de operação) |
| Último deploy | 28/10/2026, moyaserver; Pi pendente (host offline) |
| Testes | `137 passed`, 26 skips de ambiente |
| Container | `homelab-storage-admin` |
| Pi | `/opt/stacks/homelab-storage-admin`, `192.168.0.150:8060` |
| moya | mesmo path, `127.0.0.1:8060` via Caddy em `moya-storage.local` |
| Perfil | `/etc/homelab-storage-admin/host.env` |
| Agente | `homelab-storage-agent` (systemd, root, socket Unix) |
| Repositório | `https://github.com/ConradoAlmeida/homelab-storage-admin.git` |

## O que está pronto

- Usuários/grupos Samba, shares, snapshots e navegador read-only de arquivos.
- Discos, SMART standby-safe, RAID/Btrfs e métricas ao vivo.
- Backups:
  - jobs restic por disco, com agenda, retenção e verificação semanal;
  - **backup local de arquivos** com jobs independentes (fontes, agenda,
    retenção, restore verificado, cópia para USB);
  - backup do Gitea (dump + USB, hash conferido);
  - cópia fria USB implementada, dependente de repo primário.
- Jobs em produção:
  - **Credenciais** — banco + `.env`, diário 03:30, 30 dias;
  - **Dados dos apps** — 16 fontes, manual, sem timer.
- Página **Rede** read-only: UFW, interfaces, rotas, portas e containers.
- Card **Saúde** no Dashboard: discos, backups, containers e pendências.
- Login pelo Credenciais no moya, com `CREDENTIALS_MANAGE_USERS=1` e
  break-glass local.
- Passe completo de UI: `ui.css` com cabeçalho, seções, cards, avisos, botões,
  tabelas, chips, métricas, ações e formulários padronizados.
- **Novo layout de painel de operação** (branch `ui/layout-telas`, merge `76dc5f2`):
  visual compacto, rotas/firewall em tabelas, status com ponto e ações como texto.
- Modo demo (`STORAGE_ADMIN_DEMO=1` + `DEBUG=1`) para pré-visualizar a UI sem host.
- Dashboard lista jobs de arquivos e jobs restic em seções separadas.
- Backups do Gitea e do Credenciais validados com restore de teste.

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
3. **Firewall**: decidir entre ativar UFW ou assumir Caddy em `127.0.0.1`. O
   alerta “Firewall inativo” é real.
4. **Gestão de containers**: lista/stacks, start/stop/restart, logs, uso de
   CPU/RAM, confirmação e auditoria. Decidir tela própria versus Portainer.
5. **Gitea**: automatizar o dump quando houver RAID/disco; apagar os arquivos
   USB antigos inválidos.
6. **Job “Dados dos apps”**: manual por decisão; rodar + “Backup para USB”
   quando quiser cópia fria.
7. **RAID1**: quando os discos chegarem, revisar retenção e cópia externa.

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
- **Backups**: nunca apontar job restic para o disco do sistema/dados; o wizard
  recusa de propósito.
- **Job “Dados dos apps”** não tem timer; não estranhe o status “desativado”.

## Documentos irmãos

- `README.md` — operação e comportamento.
- `AGENTS.md` — regras para agentes/automação.
- Credenciais: `C:\Users\Conrado\Documents\moya_credencials_app`
  (`docs/CONTEXTO.md`), fonte de identidade do moya.

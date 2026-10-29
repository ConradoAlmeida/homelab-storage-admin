# AGENTS.md — Homelab Storage Admin

Instruções para agentes de IA e automação que trabalharem neste repositório.

## O que é

Painel Django que administra o NAS do homelab (Raspberry Pi 5) e também roda no
`moyaserver`. O mesmo código atende os dois hosts; o que muda é o perfil em
`/etc/homelab-storage-admin/host.env` e o overlay do Compose.

Leia `README.md` para o comportamento completo e `docs/CONTEXTO.md` para o
estado atual, decisões e pendências.

## Comandos

```bash
uv sync --dev
uv run manage.py check
uv run pytest
uv run manage.py runserver 0.0.0.0:8000
```

Deploy:

```bash
# Pi
cd /opt/stacks/homelab-storage-admin && ./deploy.sh
# moyaserver (mesmo comando, overlay vem do host.env)
cd /opt/stacks/homelab-storage-admin && ./deploy.sh
# quando agent/ mudar
sudo ./install-agent.sh                 # Pi
sudo env HOST_ENV_PROFILE=moya ./install-agent.sh   # moya
```

> O deploy no Pi é responsabilidade do dono; não execute sem pedido explícito.

## Regras que não podem ser quebradas

1. **O código é compartilhado com o Pi.** Nunca remova uma feature para atender
   o Credenciais. Use flag por host (`CREDENTIALS_MANAGE_USERS`) e gating por
   capability.
2. **No moya, identidade é do Credenciais.** Com `CREDENTIALS_MANAGE_USERS=1`,
   o app bloqueia só a sobreposição: criar pessoa, senha, grupos do usuário,
   ativar/desativar e excluir. Grupos Linux e operações de servidor continuam.
3. **O container não tem root no host.** Toda operação privilegiada passa pelo
   agente, que só aceita operações da allowlist. Nunca adicione `shell=True`,
   comando livre ou caminho arbitrário.
4. **Nada de `500` por falta de recurso.** Se não há Btrfs, `smartctl`, `restic`
   ou disco, esconda a ação e mostre o motivo.
5. **Operações destrutivas exigem confirmação explícita**: formatar disco,
   reconfigurar repo, restaurar backup, excluir job, remover snapshot. Nunca
   reduza a confirmação para facilitar teste.
6. **Nunca apague repositório restic, snapshots ou dados de share** por ação de
   UI. Excluir job mantém o repositório.
7. **Backups não podem rodar no disco do sistema/dados.** O wizard recusa de
   propósito; jobs restic ficam `skipped` sem disco externo.
8. **UI é requisito.** Toda página usa os componentes de `static/css/ui.css`
   (`page-head`, `section-head`, `card`, `alert`, `btn`, `table-wrap`, `tag`,
   `form-grid`). Não crie estilo local para o mesmo papel.
9. **Nunca comite `.env`, `data/`, `services.ini` real ou segredos.**
10. **Pi-safe**: recursos que dependem do Credenciais/Gitea não devem gerar
    alerta falso quando o app não existe no host.
11. **Containers**: só `start`, `stop`, `restart` e logs. Nunca `rm`, `exec`,
    `prune` ou comando livre; o agente valida o nome contra a lista real.
12. **Firewall**: só operações UFW explícitas (`enable`, `disable`, `add`,
    `delete`); nunca comando livre. Preserve SSH e as portas essenciais antes de
    ativar e audite toda ação.

## Mapa rápido

- `agent/homelab-storage-agent.py` — operações root (usuários, Samba, snapshots,
  discos, restic, Gitea, arquivos, saúde e rede).
- `core/` — dashboard, rede, usuários, shares, snapshots, cliente do agente,
  login pelo Credenciais.
- `backups/` — wizard de disco, jobs restic, snapshots, cópia fria, Gitea e
  backup local de arquivos.
- `storage/` — discos, SMART e RAID/Btrfs.
- `history/` — navegador read-only de arquivos e versões.
- `templates/` + `static/css/ui.css` — UI.
- `deploy/pi/` — units e exemplos do Pi.

## Convenções

- Português nos textos de UI e mensagens.
- Views baseadas em classe para páginas; `View` explícita nos fluxos críticos.
- Validação e confirmação ficam no fluxo, não escondidas em base class.
- Commits em Conventional Commits, assunto no imperativo.
- Ao mudar comportamento, atualize `README.md` e `docs/CONTEXTO.md` no mesmo commit.

## Testes mínimos

- páginas renderizam sem capabilities opcionais;
- gating Pi-safe (sem Credenciais/Gitea não aparece alerta falso);
- backup: agendamento, retenção, restore e falha abortando;
- confirmações e auditoria das ações;
- UI: nenhuma página nova sem os componentes padrão.

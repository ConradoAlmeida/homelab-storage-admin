# Bancada de VM por perfil (homelab e moya)

## Objetivo

Trocar a bancada atual (uma VM suja, alternância manual) por um ciclo
determinístico: **revert → perfil → testes → revert**, com um script de
entrada por lado (host e convidado) e estado final sempre igual ao inicial.

## Escopo

- VM `linux2024` (`qemu:///system`, Ubuntu 26.04, x86_64, qcow2 sem backing).
- Não cobre arm64, hardware real do Pi, nem o E2E de identidade do repo
  Credenciais (continua em `moya_credenciais_app/docs/E2E_VM.md`).

## Decisões

1. **Um script por lado, não um por ambiente.** `bench.sh` (host, com
   `--perfil homelab|moya`) substitui os wrappers `setup-*.sh` /
   `*-vm-test.sh`. Os perfis ficam em `perfil-*.sh`, que rodam como root
   dentro da VM.
2. **"Dar load no snapshot" é do host.** `snapshot-revert` exige a VM
   desligada e só existe no libvirt; por isso a camada é separada.
3. **Invariante:** toda execução começa e termina no mesmo snapshot
   (`homelab-pronto` / `moya-pronto`). Sem isso o "sempre limpo" não vale.
4. **Dois snapshots por perfil:** `base-limpo` (só origem, nunca testado) e
   `*-pronto` (ponto de partida da bancada).
5. **`clean.sh` só em bench comprovado:** exige `/etc/homelab-vm-bench`
   (criado pelo `setup-ubuntu-2604.sh`), usa allowlist + manifesto e termina
   com autoverificação. Nunca `docker system prune`, `rm -rf /mnt/*` ou
   `ufw reset` sem guard.
6. **Nada de script solto:** entram 4 arquivos novos; `run-unit-tests.sh` e
   `run-lab-tests.sh` continuam sendo os executores.

## Passos

### Fase 0 — fechar o `deploy.sh` (antes de limpar)

- [x] 0.1 Restaurar `homelab-storage-metrics.service` divergida no host e
      confirmar que o aviso de agente **desaparece**.
- [x] 0.2 `entrypoint.sh`: superusuário criado com e sem
      `DJANGO_SUPERUSER_EMAIL`; falha aparece no log, container continua.
- [x] 0.3 `pytest` no clone do worktree e commit único
      `fix(deploy): exigir .env, docker e agente completo` (`f326e01`, já em
      `main`; 453 passed, 8 skipped).
- [x] 0.4 Fechar `docs/plans/2026-11-14-verificacao-deploy-vm.md`.

### Fase 1 — scripts (sem tocar na VM)

- [x] 1.1 `scripts/vm/clean.sh` — `--dry-run` padrão, `--apply`,
      marker, manifesto, allowlist, autoverificação no fim.
- [x] 1.2 `scripts/vm/perfil-homelab.sh` e `perfil-moya.sh` — idempotentes:
      paths (`/mnt/nas`, `/mnt/jellyfin`), `host.env`, overlay, `install-agent`,
      Mailpit (moya).
- [x] 1.3 `scripts/vm/bench.sh` — host: `snapshot criar|listar|apagar`,
      `preparar|testar|limpar --perfil`, `shutdown` com fallback `destroy`,
      IP por `virsh domifaddr --source agent`, domínio em `VM=` (default
      `linux2024`), confirmação para operação destrutiva.
- [x] 1.4 `bash -n` nos quatro (shellcheck não instalado neste host).

### Fase 2 — limpar a VM atual (fresh)

- [x] 2.1 Arquivar `git diff` do clone sujo em patch antes de removê-lo
      (também os 3 diretórios sem `.git`), fora da VM.
- [x] 2.2 `clean.sh --dry-run`, revisar a lista, então `--apply`
      (`setup-ubuntu-2604.sh` recriou o marker e o baseline do Samba).
- [x] 2.3 Autoverificação: sem units, binários, containers, sockets,
      `/etc/homelab-*` e scheduled jobs do projeto (`CLEAN_OK`).
- [x] 2.4 Sem resíduo ambíguo: só saíram `/mnt/nas` e `/mnt/gitea-usb`
      (artefatos de teste) e os clones obsoletos; `Samba`/`UFW` limpos pelo
      `clean.sh`, sem precisar reinstalar a VM.
- [x] 2.5 VM desligada → `snapshot criar base-limpo`.

### Fase 3 — perfil homelab

- [x] 3.1 `bench.sh preparar --perfil homelab` (revert `base-limpo` → start →
      perfil → shutdown) e snapshot `homelab-pronto`.
- [x] 3.2 `bench.sh testar --perfil homelab --smoke`: 453/8 no pytest, 8 lab,
      `deploy.sh` real e 7 rotas em 200.
- [x] 3.3 Rodei de novo: mesmo resultado, ciclo começa limpo.

### Fase 4 — perfil moya

- [x] 4.1 `bench.sh preparar --perfil moya` e snapshot `moya-pronto`.
- [x] 4.2 `bench.sh testar --perfil moya --smoke`: 138 do Credenciais, 453 do
      Storage (3.12), Mailpit ativo, 7 rotas em 200.
- [x] 4.3 Ida e volta homelab → moya → homelab sem resíduo (3 snapshots
      intactos no fim).

### Fase 5 — documentação e commit

- [x] 5.1 `docs/VM_TESTES.md` reescrito em torno do `bench.sh` (392 → 165
      linhas).
- [x] 5.2 `docs/CONTEXTO.md` e `AGENTS.md` com o novo fluxo e o estado da VM.

## Verificação

- `clean.sh` sem `--apply` não altera nada; com `--apply` deixa zero artefato
  do projeto (verificação automática).
- `bench.sh testar` duas vezes seguidas: mesmo resultado, sem estado herdado.
- Alternância homelab → moya → homelab sem resíduo.
- `pytest` 453/8 e lab 8 no perfil homelab; suítes verdes no perfil moya.
- Nenhum script removendo dado fora do manifesto (revisão manual do diff).

## Estado

Concluído em 2026-11-15. Tudo em `main` (`c3984e3`), CI pendente de leitura
(sem `gh` autenticado).

Resultado: VM `linux2024` limpa (`CLEAN_OK`) e com três snapshots —
`base-limpo`, `homelab-pronto` e `moya-pronto`, todos criados com a VM
desligada e os dois últimos refeitos a partir de `main` no fim. Bancada
rodada em `main`: homelab 453 passed/8 skipped + 8 lab + 7 rotas 200;
moya 138 (Credenciais) + 453 + 7 rotas 200. Alternância
homelab → moya → homelab repetida sem resíduo.

Desvios do plano:

- os dois wrappers `setup-*.sh`/`*-vm-test.sh` não existiram: `bench.sh
  --perfil` cobre os quatro casos (decisão 1);
- `--smoke` passou a esperar o app responder; sem isso o primeiro acesso
  pegava o container ainda migrando (`000`);
- o `clean.sh` também remove a rede docker `moya` e a imagem do container,
  que o dry-run inicial deixava passar;
- `feat/bancada-vm` foi mergeada em `main` (fast-forward) e apagada.

Pendências fora do escopo: arm64/Pi real, E2E de identidade (repo do
Credenciais), CI de `main`.

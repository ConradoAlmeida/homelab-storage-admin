# Testes de integracao na VM Ubuntu 26.04

Roteiro para validar o ecossistema Moya em uma VM descartavel, com Ubuntu
Server 26.04 LTS. A VM e o ambiente recomendado para testes de host; o WSL2
nao serve para Samba/UFW reais.

## Resultados da primeira execucao (2026-10-30)

VM usada: Ubuntu 26.04.1, 4 vCPU, 7,2 GB RAM, 9,8 GB de disco, IP
`192.168.122.26` (libvirt `linux2024`).

- Credenciais: **115 testes OK** dentro da VM.
- Storage Admin: **201 passed, 5 skips** de laboratorio/hardware
  (Python 3.12, Linux; no Windows a mesma suite roda 180 e pula os POSIX).
- E2E de identidade/Samba: **OK** — criacao, ativacao, Samba real, `smbclient`,
  login, troca de senha, `/api/verificar` com `storage` e exclusao limpa.
- Mailpit: **OK** — envio SMTP real e mensagem encontrada na API.
- UFW: **OK** — ativacao, portas essenciais, SSH, bloqueio da ultima regra de
  SSH e desativacao.
- Docker: **OK** — `nginx:alpine` com start/stop/restart e logs pelo agente.
- Laboratório (`tests/lab`): **5 passed** — restic copy/check/restore, mdadm
  RAID1, Btrfs subvolume/snapshot, share/snapshot do agente e grupo real.
- Ainda pendente: hardware real de disco/USB de copia fria/SMART/RAID, Graph,
  login web cruzado e hardware do RPi5.
- Gitea dump + pendrive: **validado manualmente** em teste anterior; o fluxo
  nuclear nao mudou desde entao e nao foi repetido aqui por falta do pendrive.

## Estrategia de testes

- **Windows/local:** testes unitarios e de contrato, rapidos, com agente mock.
  Nao exigem host real.
- **VM Ubuntu 26.04 no Fedora:** testes server-like:
  suites dos dois apps, `tests/lab`, E2E de identidade/Samba, Mailpit, UFW,
  Docker e backups em loop/virtual disk.
- **moyaserver:** apenas smoke read-only (`scripts/vm/smoke-moyaserver.sh`).
- **WSL2:** nao usar para Samba/UFW; a porta 445 conflita com o Windows e a
  rede nao representa o host real. As distros WSL de teste foram removidas.

Ajustes descobertos nessa execucao:

- caminhos legados do backup do agente foram isolados no conftest;
- Mailpit passou a aceitar AUTH no setup;
- o script de e-mail ganhou a raiz do projeto no `sys.path` e credenciais
  dummy para o Mailpit;
- comandos do roteiro passaram de `sudo -E` para `sudo env`.

Para testar restic/backups, aumente o disco da VM; 10 GB e pouco para
repositorios e pacotes de teste.

## 1. Preparar a VM

Sugestao: 4 vCPU, 4 GB RAM, 40 GB de disco, rede bridgeada ou host-only com IP
fixo, SSH habilitado.

1. Instale o Ubuntu Server 26.04 e atualize:
   ```bash
   sudo apt update && sudo apt full-upgrade -y
   ```
2. Tire um snapshot **base-limpo** no hipervisor.
3. Copie os dois repositorios para `/home/conrado`:
   - `moya_credenciais_app`
   - `homelab-storage-admin`
4. Rode o setup do host:
   ```bash
   cd /home/conrado/homelab-storage-admin
   sudo INSTALL_DOCKER=1 bash scripts/vm/setup-ubuntu-2604.sh
   ```
   Ele instala Samba, Mailpit, uv, grupos, share `e2e`, ferramentas de disco e
   deixa o UFW **inativo**.

## 2. Testes de codigo, sem host real

### Credenciais

```bash
cd /home/conrado/moya_credenciais_app
uv sync --frozen
uv run python manage.py test --verbosity 0
```

Esperado: **115 testes OK**.

### Storage Admin

O projeto fixa Django 5.2; use Python 3.12, igual ao container de producao:

```bash
cd /home/conrado/homelab-storage-admin
uv python install 3.12
uv sync --dev --python 3.12 --frozen
uv run --python 3.12 pytest -q
```

Esperado: **201 testes passando no Linux** (5 skips de laboratório/hardware).
No Windows, a mesma suíte roda 180 e pula os testes POSIX.

### Laboratório server-like

```bash
cd /home/conrado/homelab-storage-admin
sudo bash scripts/vm/run-lab-tests.sh
```

Equivalente a:

```bash
sudo env HOMELAB_LAB=1 /usr/local/bin/uv run --python 3.12 pytest tests/lab -q
```

Esperado: **5 passed** — restic, mdadm RAID1, Btrfs, snapshot do agente e grupo
real. Esses testes criam loop devices, montam filesystems e apagam tudo no
final; rode somente na VM descartável, como root.

## 3. Perfil moyaserver

1. Copie o perfil:
   ```bash
   sudo mkdir -p /etc/homelab-storage-admin
   sudo cp host.env.moya.example /etc/homelab-storage-admin/host.env
   sudo nano /etc/homelab-storage-admin/host.env
   ```
   Ajuste para a VM:
   - `BIND_ADDR=0.0.0.0` (ou o IP da VM)
   - `CREDENTIALS_URL=http://127.0.0.1:8080`
   - `CREDENTIALS_APP=storage`
   - `FIREWALL_SAFE_PORTS` com as portas que a VM usa
2. Instale os agentes:
   ```bash
   cd /home/conrado/homelab-storage-admin
   sudo ./install-agent.sh
   systemctl status homelab-storage-agent

   cd /home/conrado/moya_credenciais_app
   sudo ./install-agent.sh
   systemctl status moya-credenciais-agent
   ```
3. Suba o Credenciais em modo de teste:
   ```bash
   cd /home/conrado/moya_credenciais_app
   cp .env.example .env
   # edite DJANGO_SECRET_KEY, AGENTE_SOCKET, SITE_URL, CREDENTIALS_API_TOKEN
   uv run python manage.py migrate
   uv run python manage.py setup_servicos
   uv run python manage.py createsuperuser
   uv run python manage.py runserver 0.0.0.0:8080
   ```
4. Suba o Storage Admin:
   ```bash
   cd /home/conrado/homelab-storage-admin
   cp .env.example .env
   # CREDENTIALS_URL=http://127.0.0.1:8080
   # CREDENTIALS_API_TOKEN=<mesmo token>
   # CREDENTIALS_APP=storage
   uv run --python 3.12 python manage.py migrate
   uv run --python 3.12 python manage.py runserver 0.0.0.0:8060
   ```
5. Ajuste `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL` para o IP da VM.

## 4. E2E de identidade e Samba

O teste cria um usuario real e apaga no final. Ele recusa o hostname
`moyaserver`.

```bash
cd /home/conrado/moya_credenciais_app
sudo env \
  MOYA_E2E=1 \
  MOYA_E2E_HOST="$(hostname)" \
  AGENTE_SOCKET=/run/moya-credenciais/agent.sock \
  DATA_DIR=/home/conrado/e2e-data \
  /usr/local/bin/uv run python manage.py test contas.e2e_vm.E2EIdentidadeTests -v 2
```

Ele valida:

- criacao sem senha/Samba;
- link de ativacao;
- senha e usuario Samba reais;
- login SMB no share `e2e`;
- login no Credenciais;
- troca de senha e recusa da antiga;
- `/api/verificar` com o app `storage`;
- exclusao de Linux, Samba e home.

Limpeza de emergencia, somente para o usuario `it-...`:

```bash
sudo smbpasswd -x it-XXXXXXXXXX
sudo userdel -r it-XXXXXXXXXX
```

## 5. E-mail com Mailpit

O setup instala o Mailpit em `127.0.0.1:1025` e UI/API em `127.0.0.1:8025`.

```bash
cd /home/conrado/moya_credenciais_app
sudo env \
  MOYA_E2E=1 \
  MOYA_E2E_HOST="$(hostname)" \
  DATA_DIR=/home/conrado/e2e-data \
  /usr/local/bin/uv run python scripts/vm/email_mailpit.py
```

Esperado: `MAILPIT_OK ...` e a configuracao anterior restaurada.

## 6. Login cruzado Credenciais -> Storage Admin

1. No Credenciais, crie uma pessoa com acesso `storage` e ative.
2. Confirme a API:
   ```bash
   curl -s -X POST http://127.0.0.1:8080/api/verificar \
     -H 'Authorization: Bearer <token>' \
     -H 'Content-Type: application/json' \
     -d '{"username":"it-...","password":"..."}'
   ```
   A resposta deve conter `"apps": [..., "storage"]`.
3. Abra `http://<ip-da-vm>:8060/` e entre com a mesma pessoa.
4. Confirme que uma pessoa sem acesso `storage` recebe a recusa correta.

## 7. UFW real

**Tire um snapshot antes.** Mantenha o console da VM aberto.

1. Verifique o estado:
   ```bash
   sudo ufw status verbose
   sudo ufw show added
   ```
2. Confirme que SSH esta liberado:
   ```bash
   sudo ufw allow 22/tcp
   ```
3. Ative:
   ```bash
   sudo ufw --force enable
   ```
4. Do Fedora, teste:
   - SSH na VM;
   - `http://<ip-da-vm>:8080/`;
   - `http://<ip-da-vm>:8060/`;
   - Samba, se estiver testando;
   - e-mail/Mailpit, se precisar.
5. Adicione e remova uma regra de teste pela UI do Storage Admin.
6. Teste a trava da ultima regra de SSH: o agente deve recusar a remocao.
7. Se perder acesso, pelo console:
   ```bash
   sudo ufw disable
   ```
8. Reverta o snapshot no fim.

Nao use a VM para concluir que o UFW do Pi ou do moya esta perfeito; ela valida
o comportamento do agente e das regras, nao a topologia real de cada host.

## 8. Containers

Com `INSTALL_DOCKER=1`:

```bash
docker run -d --name e2e-web -p 127.0.0.1:18080:80 nginx:alpine
```

No Storage Admin:

- veja o container em `/containers/`;
- teste iniciar, parar, reiniciar e logs;
- confirme a auditoria;
- remova:
  ```bash
  docker rm -f e2e-web
  ```

## 9. Backups e restic

O ideal e anexar um disco virtual secundario a VM (ex.: `/dev/vdb`) e usar o
wizard de disco do Storage Admin. Se nao for possivel:

- teste o backup local de arquivos em `/home/conrado`;
- teste um repositorio restic em um disco virtual/loop;
- faca um restore de um arquivo;
- nao valide SMART de disco virtual como se fosse hardware real.

## 10. Perfil homelab/RPi5

1. Reverta para o snapshot `base-limpo`.
2. Copie `host.env.example` para `/etc/homelab-storage-admin/host.env`.
3. Ajuste:
   - `BIND_ADDR=0.0.0.0` ou IP da VM;
   - `BIND_PORT=8060`;
   - `COMPOSE_OVERLAY=docker-compose.homelab.yml`;
   - `FIREWALL_SAFE_PORTS` incluindo `5001/tcp` e `8080/tcp`, se usar Dockge e
     a web do Pi-hole;
   - `CREDENTIALS_MANAGE_USERS=0`.
4. Repita setup, testes do Storage Admin, UFW e containers.
5. Se quiser, suba Caddy/Pi-hole/Dockge na VM; lembre que a rede e o hardware
   nao sao os do RPi5.

## 11. O que nao da para validar na VM

- SMART real, USB fisico, RAID fisico e falha de disco;
- hardware/desempenho do RPi5;
- Graph/Exchange e caixas compartilhadas;
- rotacao real do Gmail;
- carga e disponibilidade de producao.

## 12. Limpeza

- Excluir qualquer usuario `it-...` restante.
- Remover containers de teste.
- Desmontar discos virtuais.
- Desativar o UFW se necessario.
- Reverter snapshots.
- Nao copiar `.env` de producao para a VM.

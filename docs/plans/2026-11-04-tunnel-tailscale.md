# Tunnel Cloudflare e Tailscale no Pi

## Objetivo

Um endereço `https://*.conradhub.com` para a gestão do homelab (Pi), em casa e fora, com HTTPS de verdade e sem script de `hosts`. O Tailscale faz o papel do ZeroTier. O túnel Cloudflare é a porta extra para um navegador sem o app.

Antes de DNS, certificado, túnel e Tailscale, o painel deixa de segurar o HTTP até o fim do trabalho: o botão só dispara e a página consulta o andamento até terminar.

## Escopo

**Agora (bloqueia o resto):** ações longas do app viram gatilho + consulta de status.

**Depois, só no Pi:** Pi-hole, Caddy com Let's Encrypt, `cloudflared`, Access, `.env` do Django, Tailscale. O moya e o ZeroTier não mudam.

Fora deste plano: publicar porta no roteador, SMB ou vídeo pela Cloudflare, play do Jellyfin fora da LAN.

## Decisões

- A refatoração dos jobs termina e sobe no Pi antes de qualquer passo de rede.
- O POST devolve na hora. O agente grava o status e segue o trabalho. A página consulta em intervalo até `ok` ou `failed`. O modelo é **Rodar agora** (`op_backup_job_run`).
- Entram: wizard de disco (`backup_disk_setup`), cópia fria (`cold_prepare`, `cold_copy`), restore e check restic, restore do Gitea, restore/verificação/cópia USB dos backups de arquivos, snapshot criar/restaurar/salvar política.
- Download, busca no snapshot e cálculo de tamanho continuam sendo a própria resposta. Upload acima de 100 MB segue no limite da borda.
- Confirmação das ações destrutivas permanece.
- O timeout do Gunicorn (`--timeout 900` no `Dockerfile`) desce para cobrir leitura, não formatação.
- Nomes do dia a dia: `https://homelab.conradhub.com` (painel), `https://cockpit.conradhub.com`, `https://dockge.conradhub.com`, `https://jellyfin.conradhub.com`, `smb://homelab.conradhub.com/`. `https://pihole.conradhub.com` só no Pi-hole, sem DNS público.
- Em casa e no Tailscale o Pi-hole responde esses nomes com `192.168.0.150`. Sem Tailscale, fora de casa, o DNS público cai no túnel e no Access.
- Play do Jellyfin só na faixa `192.168.0.0/24`. Origem `100.64.0.0/10` ou cabeçalho `CF-Connecting-IP` recebe 403 em stream e download. A UI abre.
- `DJANGO_SECURE_COOKIES=1` quando os dois caminhos forem HTTPS no mesmo nome.
- Credencial do túnel e token DNS-01 ficam no Pi, fora do Git.
- Tailscale: subnet router `192.168.0.0/24`, split DNS de `conradhub.com` para o IP `100.x` do Pi, sem override global, chave do nó sem expiração, sem Tailscale SSH.

## Comportamento

O túnel roda no Pi. O aparelho não instala `cloudflared`. Com o Tailscale ligado, o tráfego desse aparelho vai ao Pi-hole e à rota da LAN.

- **A.** PC fora da LAN, com Tailscale: mesmos `https://` e as mesmas pastas. Sem PIN do Access. Jellyfin abre e o play responde 403. Wi-Fi de terceiro em `192.168.0.0/24` colide; o Samba usa o IP `100.x`.
- **B.** PC na LAN, com ou sem Tailscale: iguais ao A, e o play funciona.
- **C.** Celular sem Tailscale: os quatro `https://` depois do Access. Sem pastas. Play em 403. Pi-hole sem nome público.
- **D.** Celular com Tailscale: igual ao A. No iOS o endereço SMB é o mesmo, sem letra de unidade.

Criar usuário Samba, share, snapshot, regra de firewall e operar container continuam sendo HTTP para o Django. O agente no Pi executa.

## Passos

- [x] Gatilhos: POST imediato, status no agente, página consulta até terminar, timeout do Gunicorn ajustado, testes verdes.
- [x] Deploy desse app no Pi e conferência manual do disparo.
- [x] Marca Conradhub e menu no conceito 3 (áreas Visão geral, Dados e Sistema). O moya permanece Moya. Rede só depois disso.
- [ ] Docs e exemplos do nome único (`cloudflared`, `SEGURANCA`, `REDE`, `TROUBLESHOOTING`, `.env.example`, `services.ini.example`, `CONTEXTO`).
- [ ] Pi-hole: `homelab`, `cockpit`, `dockge`, `pihole` e `jellyfin.conradhub.com` → `192.168.0.150`.
- [ ] Caddy: TLS DNS-01, redireciona `*.conradhub.lan` para o `.com`, Jellyfin sem stream fora da LAN.
- [ ] Túnel `homelab`, DNS público dos quatro hostnames, unit `homelab-cloudflared`.
- [ ] Access nos quatro hostnames, policy no e-mail do dono.
- [ ] `.env` do Pi (`ALLOWED_HOSTS`, `CSRF`, `SECURE_COOKIES=1`) e `./deploy.sh`.
- [ ] Tailscale: rota `192.168.0.0/24`, split DNS, UFW 53 em `tailscale0`, chave sem expiração.
- [ ] Casos A–D conferidos.

## Verificação

- Cada ação longa responde rápido e a tela acompanha até `ok` ou `failed`, sem conexão aberta.
- `uv run pytest` verde. VM de laboratório só se o fluxo de storage/Samba/restic mudar de verdade.
- Em casa: `https://homelab.conradhub.com/login/` sem Access, `dig` no Pi-hole devolve `192.168.0.150`, play do Jellyfin funciona.
- Fora, sem Tailscale: Access nos quatro nomes, play em 403, `pihole.conradhub.com` não resolve.
- Com Tailscale: o mesmo HTTPS sem Access, `smb://homelab.conradhub.com/` abre, play em 403.

## Estado

Gatilhos feitos em 2026-11-04. `manage.py check` sem pendências. Na VM `linux2024`: `pytest` 288 passed, 6 skipped; `tests/lab` 6 passed. No demo, Verificar repo voltou na hora para `?tarefa=` e a página passou de em andamento a concluído. Gunicorn em 660 s. Deploy no Pi em `966185c`: container no ar, agente ativo, login em `192.168.0.150:8060` responde 200. Marca Conradhub Homelab e o menu do conceito 3 estão no código: `manage.py check` limpo e `pytest` 288 passed, 6 skipped. No demo local, a barra do homelab mostra os três grupos e o contador 4 em Containers; o login mostra o wordmark. O moya segue no teste com wordmark e favicon próprios. DNS, Caddy, cloudflared, Access e Tailscale seguem parados.

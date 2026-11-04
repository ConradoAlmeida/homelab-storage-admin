# Tunnel Cloudflare e Tailscale no Pi

## Objetivo

Um endereço `https://homelab.conradhub.com` em casa e fora, com HTTPS de verdade e sem script de `hosts`. O Tailscale faz o papel do ZeroTier para o painel e para o resto (Cockpit, Dockge, Jellyfin, Samba, Pi-hole). O túnel Cloudflare fica de fora: aparelho sem Tailscale não abre o homelab.

## Escopo

Só no Pi. O moya e o ZeroTier não mudam.

Fora deste plano: publicar porta no roteador, SMB ou vídeo pela Cloudflare, play do Jellyfin fora da LAN.

**Fechado em 2026-11-04.** Rota, split DNS, chave e firewall do Tailscale prontos. Zero Trust fica sem aplicação. Não publicar `homelab.conradhub.com` na Cloudflare.

## Decisões

- Nomes do dia a dia: `https://homelab.conradhub.com` (painel), `https://cockpit.conradhub.com`, `https://dockge.conradhub.com`, `https://jellyfin.conradhub.com`, `smb://homelab.conradhub.com/`. `https://pihole.conradhub.com` só no Pi-hole, sem DNS público.
- Nenhum nome `.com` ganha DNS público. Em casa o Pi-hole responde. Fora, o split DNS do Tailscale manda `conradhub.com` para o `100.84.34.25`, e o Pi-hole devolve `192.168.0.150`. O certificado já emitido no Caddy cobre esse HTTPS.
- Os nomes `.lan` saíram do Pi-hole, do Caddy e do Django. Um pedido que ainda chegue neles recebe 410. `homelab.local` permanece. Em casa o SSH é `conrado@homelab.local`.
- Em casa o Pi-hole responde os cinco `.com` com `192.168.0.150`. O Pi-hole está em `dns.listeningMode = ALL`.
- HTTPS termina no Caddy do Pi (Let's Encrypt, DNS-01). A imagem é `homelab-caddy:2`, com o módulo `caddy-dns/cloudflare`, no stack `/opt/stacks/caddy`. O token de conta (Zone DNS Edit, só `conradhub.com`) está em `/opt/stacks/caddy/cloudflare.token`, modo `600`, root, fora do Git.
- Play do Jellyfin só na faixa `192.168.0.0/24`. Origem `100.64.0.0/10` ou cabeçalho `CF-Connecting-IP` recebe 403 em stream e download. A UI abre.
- `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS` do Pi já incluem `homelab.conradhub.com`. `DJANGO_SECURE_COOKIES=1` está no `.env` do Pi e no container desde o `./deploy.sh` de 2026-11-04. O login em `https://homelab.conradhub.com` grava cookie `Secure`. `http://192.168.0.150:8060` abre a página e não mantém sessão.
- Sem túnel e sem Access na frente do painel. O Zero Trust Free e o One-time PIN ficam criados na conta, sem aplicação publicada. Publicar o nome sem essa decisão reabre a internet.
- Tailscale: nó `homelab`, `100.84.34.25`, MagicDNS `homelab.tail1a4ccb.ts.net`, SSH desligado, chave sem expiração. Rota `192.168.0.0/24` aprovada. Split DNS de `conradhub.com` para `100.84.34.25`. UFW aceita `100.64.0.0/10` nas portas dos apps e no DNS. Sem override global de DNS.

## Comportamento

Com o Tailscale ligado, o tráfego vai ao Pi-hole e à rota da LAN. Sem o app, os nomes `.com` não resolvem.

- **A.** PC fora da LAN, com Tailscale: mesmos `https://` e as mesmas pastas. Jellyfin abre e o play responde 403. Wi-Fi de terceiro em `192.168.0.0/24` colide; o Samba usa o IP `100.x`.
- **B.** PC na LAN, com ou sem Tailscale: iguais ao A, e o play funciona.
- **C.** Aparelho sem Tailscale e fora de casa: os nomes não abrem.
- **D.** Celular com Tailscale: igual ao A. No iOS o endereço SMB é o mesmo, sem letra de unidade.

## Passos

- [x] Gatilhos, marca Conradhub, docs dos nomes públicos, tamanhos de share sem travar a navegação.
- [x] Pi-hole: os cinco `.com` → `192.168.0.150`. Nomes `.lan` removidos. `homelab.local` mantido.
- [x] Caddy: certificado DNS-01 nos cinco `.com`, bloqueio de play do Jellyfin fora da LAN, `.lan` em 410.
- [x] Django no Pi aceita `https://homelab.conradhub.com`. Cookies seguros ligados depois do deploy.
- [x] Tailscale instalado e na rede (`100.84.34.25`). Rota anunciada, SSH do Tailscale desligado.
- [x] Zero Trust Free ativado e One-time PIN criado. Nenhuma aplicação pública.
- [x] Túnel dispensado. O HTTPS fora de casa é o certificado do Caddy, via split DNS.
- [x] `DJANGO_SECURE_COOKIES=1` no `.env` do Pi e `./deploy.sh` em 2026-11-04. O login em `https://homelab.conradhub.com` devolve o cookie `Secure`.
- [x] Tailscale: rota `192.168.0.0/24` aprovada, split DNS de `conradhub.com` → `100.84.34.25`, chave sem expiração. UFW aceita `100.64.0.0/10` nas portas dos apps e no DNS.
- [x] Casos A–D conferidos em 2026-11-04 no celular. Com Tailscale e sem Wi-Fi: painel, Jellyfin, Cockpit, Dockge, Pi-hole e Samba. Play do Jellyfin no 5G em 403 e na LAN reproduzindo. Sem Tailscale e fora da LAN, o nome não resolve.

## Verificação

- Em casa: `https://homelab.conradhub.com/login/` abre sem Access e o `dig` no Pi-hole devolve `192.168.0.150`. `homelab.local` responde. Um nome `.lan` não resolve.
- Fora, sem Tailscale: nenhum nome `.com` resolve.
- Com Tailscale: o mesmo HTTPS sem Access, `smb://homelab.conradhub.com/` abre, play em 403.

## Estado

Encerrado em 2026-11-04. Código em `0778bfc`. Não há túnel: os nomes `.com` não estão no DNS público e fora de casa só o Tailscale. Zero Trust Free está na conta, sem aplicação. Rota, split DNS, chave sem expiração e firewall feitos nesse dia. `DJANGO_SECURE_COOKIES=1` está no `.env` do Pi e no container depois do `./deploy.sh`. O login em `https://homelab.conradhub.com` grava cookie `Secure`. Um celular em 5G com Tailscale e sem Wi-Fi abriu o painel, o Jellyfin, o Cockpit, o Dockge, o Pi-hole e o Samba pelo nome. Os atalhos do painel passaram de `*.homelab.lan` para `https://*.conradhub.com` em `data/services.ini` do Pi. O play do Jellyfin no 5G recebe 403 e na LAN reproduz. No mesmo celular, em 5G e sem Tailscale, o nome não resolve.

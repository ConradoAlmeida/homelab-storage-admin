# Rede, saúde e containers

[← Voltar ao README](../README.md) · [Contexto](CONTEXTO.md) · [Segurança e acesso remoto](SEGURANCA.md)

> Saúde do host, rede e firewall UFW, e o mini Portainer de containers.

---

## Saúde e rede

### Saúde do host

O card **Saúde** do Dashboard usa `health_overview` e resume, em uma lista única:

- alertas de disco (SMART, uso, standby) e de volume;
- resultado dos jobs de backup (restic e arquivos) e repositórios sem check;
- containers que deveriam estar rodando;
- pendências de configuração (por exemplo, firewall inativo).

Cada alerta tem nível (`info`, `warn`, `red`). O card mostra “tudo ok” quando não
há alertas. Os dados vêm do agente; a UI não faz probe próprio nem aciona discos.

### Rede e firewall (UFW)

`/rede/` mostra e, para administradores, gerencia o firewall UFW:

- firewall: estado, políticas padrão, regras salvas, ativar/desativar;
- adicionar regra de entrada por ação (permitir/bloquear/rejeitar/limitar),
  porta, protocolo e origem (IP/CIDR ou qualquer);
- remover regra pela assinatura exata; a tabela mostra o comando `ufw` salvo;
- interfaces, rotas, portas ouvindo e containers publicados.

Travas de segurança:

- ao ativar, o agente garante SSH (22/tcp) e libera as portas essenciais que
  estiverem em uso público (SSH, DNS, HTTP/HTTPS e o próprio painel) para não
  perder o acesso; a lista é configurável em `FIREWALL_SAFE_PORTS`;
- a última regra que libera SSH não pode ser removida com o firewall ativo;
- bloquear ou rejeitar a porta 22 é recusado pelo agente;
- toda ação vai para a auditoria (`firewall.enable`, `.disable`, `.add`, `.delete`);
- `FIREWALL_MANAGE=0` deixa a página somente leitura.

Docker publica portas via iptables e pode furar o UFW; o modelo recomendado é
publicar em `127.0.0.1` e deixar o Caddy expor.

### Nomes

O domínio `conradhub.com` (zona na Cloudflare, NS cameron/hera) existe para o
nome e para o certificado Let's Encrypt (DNS-01). `homelab`, `cockpit`,
`dockge`, `jellyfin` e `pihole` não têm A nem CNAME público. `dig @1.1.1.1`
volta vazio. A Cloudflare não resolve a navegação.

Em casa o Pi-hole escuta em todas as interfaces e responde esses cinco nomes
com `192.168.0.150`. Fora de casa só o Tailscale. No 5G o app manda só
`conradhub.com` para `100.84.34.25`; o Pi-hole responde; o tráfego a
`192.168.0.150` volta pela rota. Sem Tailscale e fora da LAN, o nome não
resolve.

| Uso | Endereço |
|---|---|
| Painel | `https://homelab.conradhub.com` |
| Cockpit | `https://cockpit.conradhub.com` |
| Dockge | `https://dockge.conradhub.com` |
| Jellyfin | `https://jellyfin.conradhub.com` |
| Pi-hole (só em casa ou com Tailscale) | `https://pihole.conradhub.com` |
| Arquivos | `smb://homelab.conradhub.com/` |

SSH em casa: `conrado@homelab.local`. O hostname Linux segue `homelab`. Os
nomes `.lan` saíram do Pi-hole, do Caddy e do Django. Pedido HTTP antigo
recebe 410.

HTTPS termina no Caddy do Pi, imagem `homelab-caddy:2` (caddy +
`caddy-dns/cloudflare`), stack `/opt/stacks/caddy`, network host. O token de
API (Zone DNS Edit, só a zona) fica em `/opt/stacks/caddy/cloudflare.token`,
modo 600, root, fora do Git. O token só cria o TXT do desafio.

**Tailscale, só no Pi.** Nó `homelab`, `100.84.34.25`, MagicDNS
`homelab.tail1a4ccb.ts.net`. SSH do Tailscale desligado. Chave sem expiração.
Rota `192.168.0.0/24` aprovada. Split DNS: `conradhub.com` → `100.84.34.25`,
restrito a esse sufixo, sem override global de DNS. O UFW aceita
`100.64.0.0/10` em DNS, 80, 443, 8060, 9090, 5001, 8096 e nas portas Samba
445/139/137/138. O Samba escuta em `0.0.0.0:445`. O moya e o ZeroTier não
mudam. Não publique porta no roteador.

A UI do Jellyfin abre pelo Tailscale. Stream e download com origem
`100.64.0.0/10` ou cabeçalho `CF-Connecting-IP` recebem 403 ("Playback fora
da LAN"). Na LAN o vídeo toca. Em 2026-11-04 o 5G deu erro de playback; na
LAN reproduziu.

Wi-Fi de terceiro em `192.168.0.0/24` colide com a rota. Nesse caso o Samba
usa o IP `100.x` do Pi.

**Casos** (celular em 5G, 2026-11-04):

| Caso | Onde | Tailscale | Web | SMB | Jellyfin play |
|---|---|---|---|---|---|
| A | Fora da LAN | sim | os cinco `https://` | sim | 403 |
| B | LAN | opcional | igual ao A | sim | ok |
| C | Fora | não | o nome não resolve | não | — |
| D | Fora (celular) | sim | igual ao A | `smb://homelab.conradhub.com/` | 403 |

O celular abriu o Samba pela opção LAN do gerenciador de arquivos. Cookies e
o bloqueio de playback: [Segurança](SEGURANCA.md#acesso-remoto).

Samba, shares, snapshots, firewall e containers continuam sendo pedidos HTTP
ao Django; o agente no Pi executa. Confirmações destrutivas permanecem.

**Descoberta na LAN** (Pi e moya):

- **Nautilus / Rede no Linux:** Avahi, domínio `.local` (RFC 6762). Samba com
  `multicast dns register`.
- **Explorador / Rede no Windows:** `wsdd` (WS-Discovery). Hostname `HOMELAB` no
  Pi, `MOYASERVER` no moya. Portas `3702/udp` e `5357/tcp` (fora de
  `FIREWALL_SAFE_PORTS` até o UFW ser ligado).

---

## Containers (mini Portainer)

`/containers/` mostra e opera os containers do host, com **Docker ou Podman**
(o agente usa o runtime que encontrar).

- Lista nome, ID curto, imagem, estado, saúde, portas, projeto/serviço do Compose
  e contagem de reinícios.
- Ações: **iniciar**, **parar** e **reiniciar**, sempre com confirmação.
- **Logs** com seletor de 100, 200, 500 ou 1000 linhas, em modo leitura.
- Não cria, não remove, não executa comandos e não altera stacks.
- Toda ação é registrada na auditoria (`container.start/stop/restart`).
- O agente valida o nome contra a lista real e só aceita as três ações; não há
  shell livre.
- Sem Docker/Podman, a capability fica falsa, o item some do menu e a página
  mostra o motivo.
- Parar um container crítico (Caddy, Credenciais ou o próprio Storage Admin)
  derruba o serviço correspondente; a confirmação existe por isso.
- O container do próprio painel não mostra **Parar/Reiniciar**; para ele, use o host.

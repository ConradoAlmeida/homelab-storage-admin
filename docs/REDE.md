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

### Nomes públicos e LAN

Um nome em casa e fora (`*.conradhub.com`). O Pi-hole (em casa e com Tailscale)
responde `homelab`, `cockpit`, `dockge`, `jellyfin` e `pihole.conradhub.com`
com `192.168.0.150`. Sem Tailscale, fora de casa, o DNS público cai no túnel
Cloudflare e no Access (PIN por e-mail). O Pi-hole encaminha o resto da zona
(apex, MX). `https://pihole.conradhub.com` não tem registro público.

| Uso | Endereço |
|---|---|
| Painel Storage Admin | `https://homelab.conradhub.com` |
| Cockpit, Dockge, Jellyfin | `https://cockpit…`, `https://dockge…`, `https://jellyfin…` |
| Arquivos | `smb://homelab.conradhub.com/` |
| Pi-hole (só LAN / Tailscale) | `https://pihole.conradhub.com` |

Os `*.conradhub.lan` correspondentes (por exemplo `storage.conradhub.lan`) só
redirecionam para o `.com`. Aliases `*.homelab.lan` ainda resolvem onde existirem.
SSH continua `conrado@conradhub.lan` no Pi. Hostname Linux, Samba e Avahi
permanecem `homelab`.

HTTPS termina no Caddy do Pi (Let's Encrypt, DNS-01). O `cloudflared` roda só no
Pi: ingress dos quatro hostnames públicos para `https://192.168.0.150`; o resto
404. O aparelho cliente não instala `cloudflared`.

**Tailscale (só no Pi, no lugar do ZeroTier):** subnet router `192.168.0.0/24`,
split DNS de `conradhub.com` para o IP `100.x` do Pi (ali o Pi-hole escuta), sem override global de DNS, sem
Tailscale SSH, chave do nó sem expiração. O moya e o ZeroTier dele não mudam.
Detalhes em [Segurança e acesso remoto](SEGURANCA.md#acesso-remoto).

**Casos rápidos** (conferência manual após o deploy de rede):

| Caso | Onde | Tailscale | Web | SMB | Jellyfin play |
|---|---|---|---|---|---|
| A | Fora da LAN | sim | `https://` sem Access | sim (`100.x` se Wi-Fi colidir com `192.168.0.0/24`) | 403 |
| B | LAN | opcional | igual ao A | sim | ok |
| C | Fora | não | quatro `https://` com Access | não | 403 |
| D | Fora | sim (ex. celular) | igual ao A | sim (iOS: mesmo SMB, sem letra de unidade) | 403 |

Samba, shares, snapshots, firewall e containers continuam sendo pedidos HTTP
ao Django; o agente no Pi executa. Confirmações destrutivas permanecem.

**Descoberta na LAN** (Pi e moya):

- **Nautilus / Rede no Linux:** Avahi, domínio `.local` (RFC 6762; mDNS não vai
  em `.lan`). Samba com `multicast dns register`.
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

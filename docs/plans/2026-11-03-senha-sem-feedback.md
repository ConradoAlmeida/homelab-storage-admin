# Senha sem feedback (caio) + aviso HTTP no Chrome

## Objetivo

A tentativa de definir a senha Samba de `caio` em
`http://storage.homelab.lan/usuarios/senha/?username=caio` (user `conrado`)
não mostrou sucesso nem fracasso. Corrigir o feedback na UI e documentar o
aviso do Chrome sobre senha em HTTP.

## Diagnóstico (produção, Pi, 2026-11-03)

Evidência lida no host (`192.168.0.150`), sem alterar nada:

- `CREDENTIALS_MANAGE_USERS=0` — a tela de senha existe neste host.
- Linux user `caio` existe (`uid 1002`, shell `nologin`).
- **A troca não chegou ao agente.** Não há `SET_PASSWORD caio` em
  `/var/log/homelab-storage-agent.log`. Não há `user.password` / `caio` em
  `core_auditlog`. O único `SET_PASSWORD` no log é de `conrado` em 24-25/10.
- No mesmo minuto o painel **funcionou** para grupos: `SET_GROUPS caio` às
  19:56:22 (actor `conrado`). O agente e a sessão estavam ok.
- Gunicorn no container não grava access log — não dá para ver se o POST
  chegou ao Django.

O aviso no console do Chrome:

> Password fields present on an insecure (http://) page. This is a security
> risk that allows user login credentials to be stolen.

é o Chrome reclamando de `<input type="password">` em `http://`. Caddy publica
hoje `http://storage.homelab.lan` (sem `tls`). **Esse aviso não aborta o POST**
e **não é a mensagem de sucesso/fracasso do app**. É o único texto que o
navegador mostra sobre a senha, então parece “o feedback”.

Por que o app pode ficar mudo se o POST falhar na validação:

1. `username` é `HiddenInput`. Erro nesse campo (`Este campo é obrigatório`)
   não aparece: `form_field.html` não renderiza erro de hidden, e
   `form_alert.html` só mostra `non_field_errors`.
2. Erro de senha curta fica só no `ul.errorlist` dentro de `form.stack`, cujo
   CSS trata todo `ul` como lista de chips de grupo.
3. `PasswordInput` esvazia o campo no re-render (`render_value=False`) — a
   tela parece um GET novo.
4. Sucesso redireciona para `/usuarios/` com `.messages` fino (texto + linha),
   não o componente `alert`. Neste incidente o sucesso não ocorreu.
5. Não há teste de POST em `/usuarios/senha/`.

## Escopo

**Nesta sessão (este repo):**

- Feedback visível de sucesso e de fracasso na troca de senha.
- Username visível (readonly) na tela, para o hidden deixar de ser o único
  carregador do nome.
- Testes de POST (sucesso, AgentError, username ausente, senha curta).
- Lab na VM `linux2024` (já running, `192.168.122.26`): `op_set_password`
  real + fluxo da tela de senha no perfil Pi.
- Nota curta em `docs/CONTEXTO.md` e, se couber, `docs/TROUBLESHOOTING.md`.

**Fora desta sessão:** HTTPS. O aviso do Chrome em HTTP permanece.

Não alterar senha do `caio`. Não `deploy.sh` no Pi sem pedido.

## Decisões

- Manter redirect de sucesso para `/usuarios/` (igual grupos/criar usuário).
- Trocar `partials/messages.html` para o componente `alert` (`ok` / `danger`).
- `form_alert.html` lista todos os `form.errors` (campos, hidden, non-field).
- `PasswordForm.username`: campo visível readonly (entra no POST; tooltip
  HTML5 deixa de apontar para hidden).
- `form.stack ul:not(.errorlist)` para o errorlist não herdar layout de chips.
- Sem gunicorn access log neste passo.
- Sem mexer em `op_set_password` (só exercitar), Caddy ou CA.
- VM obrigatória neste desktop: `linux2024` no virt-manager. Sem exceção.

## Passos

- [x] Plano em `docs/plans/2026-11-03-senha-sem-feedback.md`.
- [x] `templates/partials/form_alert.html` — `form.errors` completo.
- [x] `templates/partials/messages.html` — `alert ok` / `alert danger`.
- [x] `core/forms.py` `PasswordForm` — username readonly + help_text da senha
      (mínimo 8, só Samba).
- [x] `static/css/app.css` — `form.stack ul:not(.errorlist)`.
- [x] `tests/test_views.py` — POST sucesso / AgentError / username ausente /
      senha curta.
- [x] `tests/lab/test_users.py` — `op_set_password` real.
- [x] `docs/CONTEXTO.md` + `docs/TROUBLESHOOTING.md`.
- [x] VM `linux2024`: pytest + lab + fluxo da UI (perfil Pi).
- [x] Commit Conventional Commits em pt-BR **depois** da VM verde.

## Verificação

Neste clone (Fedora):

```bash
uv run manage.py check
uv run pytest tests/test_views.py tests/test_compartilhado.py tests/test_ajuda.py
```

Na VM `linux2024` (`192.168.122.26`, `docs/VM_TESTES.md` seção 10). Não pular.

## Estado

Concluído. Commit `777e253` em `fix/senha-feedback`. Deploy no Pi não rodado.

- Clone Fedora: `manage.py check` ok; `282 passed, 6 skipped`.
- VM `linux2024`: pytest `282 passed, 6 skipped`; lab `6 passed` (inclui
  `test_set_password_real` + smbclient); fluxo UI `UI_SENHA_OK` (alerta de
  senha curta, username ausente, sucesso, usuário inexistente, senha nova
  aceita e antiga recusada).

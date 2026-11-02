# Senha Samba independente — corrigir textos e documentar propagação

## Objetivo

Alinhar UI, ajuda e docs com o que o código realmente faz: a senha definida no
painel é **apenas Samba**; a conta Linux é criada sem senha e com shell
`nologin`; e no moya a unificação com o Credenciais é feita por automação
externa (push), não pelo painel.

## Escopo

- Textos de UI e ajuda (`user_password`, `user_form`).
- Docs de área: armazenamento, arquitetura (contrato de propagação), segurança.
- `docs/CONTEXTO.md` no mesmo commit.
- Teste de regressão de texto.
- **Fora do escopo:** mudar `op_create_user`/`op_set_password`, mexer no gating
  `CREDENTIALS_MANAGE_USERS`, criar tela de "ver senha", alterar automação do
  Credenciais (vive fora deste repo).

## Decisões

- Texto neutro por host: a página só existe onde `CREDENTIALS_MANAGE_USERS=0`,
  mas o template é compartilhado — nada de "no Pi…".
- Não afirmar sincronização: no moya ela existe por push do Credenciais; no Pi
  não existe. O texto deve valer nos dois.
- Manter `usermod -L/-U` no toggle do usuário (inócuo sem senha Unix, mas
  correto se o dono definir uma) e registrar isso no doc.
- Nada de armazenar senha para "reaplicar" depois; reset é o fluxo.

## Passos

- [x] `templates/user_password.html:7` — trocar o lead por: vale só para o
      Samba; conta Linux sem senha e com `nologin`; SSH exige senha Unix
      definida à parte no servidor.
- [x] `templates/user_form.html:7` — trocar o lead por: cria conta Linux
      travada (sem senha, `nologin`), usuário Samba e home; a senha digitada é
      do Samba.
- [x] `core/ajuda.py:366` — capítulo "Onde a senha vale" com o mesmo conteúdo.
- [x] `core/ajuda.py:360` — summary "Troca a senha de uma conta Linux/Samba"
      → "Troca a senha Samba de uma conta".
- [x] `core/ajuda.py` — novo capítulo em `user_password`: não há como ver a
      senha; esquecida = definir outra (o app não guarda o texto).
- [x] `core/forms.py:15` — help_text da senha: deixar explícito "senha do
      Samba".
- [x] `docs/ARMAZENAMENTO.md:151` — nota: senha Linux e Samba são
      independentes; `passwd` manual cria senha Unix divergente; sem
      `unix password sync`; painel não guarda plaintext; reset é o único
      caminho.
- [x] `docs/ARQUITETURA.md` (seção "Login pelo Credenciais", após a linha 215) —
      documentar o contrato do push no moya: evento de criação (ativação),
      troca posterior, desativação/exclusão, idempotência (`smbpasswd -a` pode
      reexecutar), falha no push → conta só no Credenciais e retry, transporte
      (socket do agente vs rede) e o fato de que o painel não participa.
- [x] `docs/SEGURANCA.md` — nota curta: `passdb.tdb` guarda hash NT sem salt,
      `0600 root`; unificação não muda isso; o app não copia o arquivo em
      backup.
- [x] `tests/test_views.py` — teste de regressão: página `user_password`
      menciona Samba e não afirma "login no servidor".
- [x] `docs/CONTEXTO.md` — registrar a correção e o contrato do push.

## Verificação

```bash
uv run manage.py check
uv run pytest
uv run manage.py runserver 0.0.0.0:8000   # /usuarios/senha/ e /usuarios/novo/
```

- Abrir as duas páginas no perfil Pi e conferir o texto renderizado.
- VM (`docs/VM_TESTES.md`): alteração só de texto/doc; declarar a exceção no
  resumo em vez de rodar o laboratório, salvo pedido do dono.

## Estado

Concluído em 2026-11-02. Só texto de UI, ajuda, docs e um teste de regressão —
nenhuma mudança de comportamento.

- `uv run manage.py check`: sem issues.
- `uv run pytest`: 278 passed, 5 skipped (lab, sem `HOMELAB_LAB=1`).
- VM (`docs/VM_TESTES.md`) não rodada: alteração sem código de servidor; o teste
  de renderização cobre o texto. Declarada a exceção.

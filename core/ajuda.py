"""Ajuda contextual exibida no topo de cada página.

Cada rota nomeada tem um título e capítulos. Um capítulo corresponde a uma
funcionalidade da página: ``text`` explica o que ela faz e ``bullets`` lista
ações, cuidados ou resultados esperados. Rotas sem entrada simplesmente não
mostram o botão de ajuda.
"""
from __future__ import annotations

from typing import Any

AJUDA: dict[str, dict[str, Any]] = {
    "dashboard": {
        "title": "Dashboard",
        "summary": (
            "Visão consolidada do servidor: saúde, serviços, recursos, discos, "
            "backups e shares."
        ),
        "chapters": [
            {
                "title": "Saúde do sistema",
                "text": (
                    "A faixa no topo reúne os avisos coletados pelo agente. "
                    "Vermelho pede ação imediata; amarelo é atenção; verde "
                    "indica uma verificação concluída."
                ),
            },
            {
                "title": "Serviços",
                "text": (
                    "Mostra se os serviços gerenciados estão ativos. Um serviço "
                    "parado pode explicar shares ou backups indisponíveis."
                ),
            },
            {
                "title": "Sistema e rede",
                "text": (
                    "CPU, memória, carga e tráfego são atualizados "
                    "automaticamente. Consumo alto e constante indica gargalo "
                    "ou processo travado."
                ),
            },
            {
                "title": "Volumes e discos",
                "bullets": [
                    "Volumes mostram o uso das montagens do host.",
                    "A tabela de discos aponta modelo, papel e estado SMART.",
                    "O botão Detalhes abre a página Discos.",
                ],
            },
            {
                "title": "Backup de arquivos",
                "text": (
                    "Jobs locais que geram pacotes em disco. A tabela resume "
                    "agenda, retenção e o último resultado; Gerenciar jobs abre "
                    "a lista completa."
                ),
            },
            {
                "title": "Backups restic",
                "text": (
                    "Jobs incrementais com repositório restic. O status "
                    "'aguardando disco' aparece quando o destino não está montado."
                ),
            },
            {
                "title": "RAID e volumes",
                "text": (
                    "Exibe o estado dos arrays e volumes. Membro degradado ou "
                    "ausente deve ser resolvido antes de gravar novos dados."
                ),
            },
            {
                "title": "Shares",
                "text": (
                    "Resume cada share, o espaço usado pelos dados, pelos "
                    "snapshots e o total."
                ),
            },
        ],
    },
    "network_index": {
        "title": "Rede e firewall",
        "summary": (
            "Visão de rede do host: firewall UFW editável, interfaces, rotas, "
            "portas abertas e containers publicados."
        ),
        "chapters": [
            {
                "title": "Firewall (UFW)",
                "text": (
                    "Mostra o estado, as políticas padrão e as regras salvas. "
                    "Com a gestão habilitada, é possível ativar ou desativar o "
                    "firewall e adicionar ou remover regras."
                ),
            },
            {
                "title": "Ativar e desativar",
                "text": (
                    "Ao ativar, o painel garante uma regra de SSH (22/tcp) para "
                    "não perder o acesso. Desativar remove o filtro até que o "
                    "firewall seja ligado de novo."
                ),
            },
            {
                "title": "Regras",
                "text": (
                    "As regras são salvas no UFW mesmo com o firewall parado. "
                    "Adicione por porta, protocolo e origem; a remoção usa a "
                    "regra exata e é recusada se for a última liberação de SSH "
                    "com o firewall ativo."
                ),
            },
            {
                "title": "Interfaces",
                "text": (
                    "Mostra estado, endereço, velocidade, MAC e sinal das "
                    "interfaces. Interface sem endereço pode indicar cabo ou "
                    "DHCP com problema."
                ),
            },
            {
                "title": "Rotas",
                "text": (
                    "Tabela de rotas do sistema. A rota padrão define a saída "
                    "para redes externas."
                ),
            },
            {
                "title": "Portas ouvindo",
                "text": (
                    "Processos que escutam no host. Ajuda a descobrir conflito "
                    "de porta ou serviço exposto sem necessidade."
                ),
            },
            {
                "title": "Containers publicados",
                "text": (
                    "Portas publicadas por containers. O tráfego chega ao host "
                    "e é encaminhado para o container correspondente."
                ),
            },
        ],
    },
    "containers": {
        "title": "Containers",
        "summary": "Lista e controla os containers Docker ou Podman do servidor.",
        "chapters": [
            {
                "title": "Lista de containers",
                "text": "Mostra nome, imagem, estado e portas publicadas.",
            },
            {
                "title": "Iniciar",
                "text": "Sobe um container parado e o deixa disponível novamente.",
            },
            {
                "title": "Parar",
                "text": (
                    "Encerra o container. O serviço fica indisponível até ser "
                    "iniciado de novo."
                ),
            },
            {
                "title": "Reiniciar",
                "text": (
                    "Para e inicia em sequência. Use depois de mudar "
                    "configuração ou atualizar a imagem."
                ),
            },
            {
                "title": "Logs",
                "text": (
                    "Abre as últimas linhas do container para diagnosticar "
                    "erros de inicialização ou falhas em tempo real."
                ),
            },
            {
                "title": "Proteção do painel",
                "text": (
                    "O container que executa o próprio Storage Admin é "
                    "bloqueado para evitar perder o acesso ao painel."
                ),
            },
        ],
    },
    "container_logs": {
        "title": "Logs do container",
        "summary": "Últimas linhas de log de um container, apenas para leitura.",
        "chapters": [
            {
                "title": "Quantidade de linhas",
                "text": (
                    "Escolha quantas linhas carregar e confirme em Carregar. "
                    "Volumes maiores demoram mais para aparecer."
                ),
            },
            {
                "title": "Atualizar",
                "text": "Recarrega o log com a mesma quantidade de linhas.",
            },
            {
                "title": "Somente leitura",
                "text": (
                    "Nada é alterado no container; esta página apenas exibe o "
                    "log."
                ),
            },
        ],
    },
    "users": {
        "title": "Usuários Samba",
        "summary": "Contas Linux/Samba e grupos de share do servidor.",
        "chapters": [
            {
                "title": "Pessoas",
                "text": "Lista as contas, os grupos de cada uma e se estão ativas.",
            },
            {
                "title": "Gestão pelo Credenciais",
                "text": (
                    "Quando o Credenciais gerencia usuários, criar pessoa, "
                    "senha, grupos e exclusão são feitos lá. Esta página fica "
                    "em modo de consulta."
                ),
            },
            {
                "title": "Gestão local",
                "text": (
                    "Quando a gestão é local, use Novo usuário, Senha, Grupos, "
                    "Desativar e Excluir diretamente nesta página."
                ),
            },
            {
                "title": "Ativar e desativar",
                "text": (
                    "Desativar bloqueia o login Samba e Linux sem apagar os "
                    "dados. Ativar libera o acesso de novo."
                ),
            },
            {
                "title": "Excluir",
                "text": (
                    "Remove a conta Linux, o usuário Samba e a pasta home. A "
                    "ação é irreversível."
                ),
            },
            {
                "title": "Grupos de share",
                "text": (
                    "Grupos usados pelas pastas compartilhadas. O grupo privado "
                    "de cada pessoa é removido junto com a conta."
                ),
            },
        ],
    },
    "user_create": {
        "title": "Novo usuário Samba",
        "summary": "Cria uma conta Linux, um usuário Samba e a pasta home.",
        "chapters": [
            {
                "title": "Usuário e senha",
                "text": (
                    "Use minúsculas, de 3 a 32 caracteres (a-z, 0-9, ponto, "
                    "hífen e sublinhado). A senha precisa ter pelo menos 8 "
                    "caracteres."
                ),
            },
            {
                "title": "O que é criado",
                "text": (
                    "O agente cria a conta Linux, o usuário Samba e a pasta "
                    "home da pessoa."
                ),
            },
            {
                "title": "Grupos",
                "text": (
                    "Marque os grupos de share que a pessoa pode acessar. O "
                    "grupo privado é criado automaticamente."
                ),
            },
            {
                "title": "Depois de criar",
                "text": (
                    "A senha pode ser trocada em Senha e os grupos ajustados em "
                    "Grupos."
                ),
            },
        ],
    },
    "user_password": {
        "title": "Definir senha",
        "summary": "Troca a senha de uma conta Linux/Samba.",
        "chapters": [
            {
                "title": "Onde a senha vale",
                "text": "A nova senha vale para o login no servidor e para o Samba.",
            },
            {
                "title": "Regra",
                "text": "A senha precisa ter no mínimo 8 caracteres.",
            },
            {
                "title": "Escopo",
                "text": "A troca afeta apenas a conta selecionada e vale na hora.",
            },
        ],
    },
    "user_groups": {
        "title": "Grupos do usuário",
        "summary": "Define quais grupos de share uma conta pode acessar.",
        "chapters": [
            {
                "title": "Grupos de share",
                "text": (
                    "Marque os grupos que liberam acesso às pastas "
                    "compartilhadas correspondentes."
                ),
            },
            {
                "title": "Grupo privado",
                "text": (
                    "O grupo privado da pessoa é gerenciado automaticamente e "
                    "não aparece para escolha."
                ),
            },
            {
                "title": "Efeito de salvar",
                "text": (
                    "Salvar atualiza o acesso da pessoa aos shares na hora, sem "
                    "precisar reiniciar o Samba."
                ),
            },
        ],
    },
    "group_create": {
        "title": "Novo grupo",
        "summary": "Cria um grupo Linux usado para liberar acesso a um share.",
        "chapters": [
            {
                "title": "Nome",
                "text": (
                    "Use minúsculas, de 2 a 32 caracteres (a-z, 0-9, ponto, "
                    "hífen e sublinhado)."
                ),
            },
            {
                "title": "GID",
                "text": (
                    "Opcional. Se ficar vazio, o sistema escolhe um GID livre "
                    "maior ou igual a 1000."
                ),
            },
            {
                "title": "Uso",
                "text": (
                    "Depois de criar, associe o grupo ao share e inclua as "
                    "pessoas em Grupos."
                ),
            },
        ],
    },
    "shares": {
        "title": "Compartilhamentos",
        "summary": "Shares do Samba, uso em disco, snapshots e controle de acesso.",
        "chapters": [
            {
                "title": "Tabela de shares",
                "text": (
                    "Mostra caminho, política de snapshot, espaço de dados, "
                    "espaço dos snapshots e total."
                ),
            },
            {
                "title": "Política de snapshot",
                "text": (
                    "keep N é quantos snapshots a política mantém. 'Não "
                    "configurado' significa que o share não tem política de "
                    "versões."
                ),
            },
            {
                "title": "Acesso",
                "text": (
                    "Mostra os usuários ou grupos liberados e se o share é "
                    "leitura/escrita ou somente leitura."
                ),
            },
            {
                "title": "Share privado",
                "text": (
                    "O share fica oculto na listagem da rede, mas continua "
                    "restrito pelos grupos de acesso."
                ),
            },
            {
                "title": "Novo share",
                "text": (
                    "Cria o diretório, os grupos de acesso e recarrega o Samba "
                    "depois de validar a configuração."
                ),
            },
        ],
    },
    "share_create": {
        "title": "Novo compartilhamento",
        "summary": "Cria um share, seus grupos e a política de snapshots.",
        "chapters": [
            {
                "title": "Nome e caminho",
                "text": (
                    "O nome aceita de 1 a 32 caracteres (A-Z, a-z, 0-9, hífen "
                    "e sublinhado). O caminho é o diretório usado pelo share."
                ),
            },
            {
                "title": "Snapshot",
                "text": (
                    "Ao marcar, o share já nasce com política de versões. Btrfs "
                    "usa subvolume; ext4 usa snapshots rsync com hardlinks."
                ),
            },
            {
                "title": "Versões a manter",
                "text": "Define quantos snapshots a política preserva.",
            },
            {
                "title": "Privado",
                "text": "Oculta o share da listagem da rede; o acesso continua restrito.",
            },
            {
                "title": "Grupos criados",
                "text": (
                    "O agente cria <nome>_ro, <nome>_rw e <nome>, valida com "
                    "testparm e recarrega o Samba."
                ),
            },
        ],
    },
    "snapshots": {
        "title": "Snapshots",
        "summary": "Políticas, criação e remoção de snapshots por share.",
        "chapters": [
            {
                "title": "Resumo",
                "text": (
                    "Mostra quantos shares têm política, o total de snapshots e "
                    "o tamanho aproximado."
                ),
            },
            {
                "title": "Criar snapshot agora",
                "text": "Gera um snapshot imediato do share selecionado.",
            },
            {
                "title": "Navegar",
                "text": "Abre o snapshot no explorador de arquivos para consulta e download.",
            },
            {
                "title": "Remover",
                "text": (
                    "Apaga o snapshot escolhido. Os dados atuais do share não "
                    "são afetados."
                ),
            },
            {
                "title": "Tamanho aproximado",
                "text": (
                    "Blocos compartilhados entre snapshots contam uma única vez, "
                    "por isso o total é aproximado."
                ),
            },
        ],
    },
    "history_index": {
        "title": "Arquivos e versões",
        "summary": "Explora os snapshots dos shares para consultar e baixar arquivos.",
        "chapters": [
            {
                "title": "Shares",
                "text": "Lista os shares que possuem snapshots disponíveis.",
            },
            {
                "title": "Versões",
                "text": "Mostra quantos snapshots existem e a data do mais recente.",
            },
            {
                "title": "Navegar",
                "text": "Abre o share para explorar pastas, baixar arquivos e ver versões.",
            },
        ],
    },
    "history_share": {
        "title": "Explorar share",
        "summary": "Navega pelos arquivos de um share em um snapshot.",
        "chapters": [
            {
                "title": "Pastas e arquivos",
                "text": "Abrir entra na pasta; Baixar salva o arquivo selecionado.",
            },
            {
                "title": "Snapshots",
                "text": "Escolha o snapshot na lista lateral. O mais recente reflete o estado atual.",
            },
            {
                "title": "Versões",
                "text": "Mostra as versões anteriores de um arquivo nos outros snapshots.",
            },
            {
                "title": "Navegação",
                "text": "Subir retorna um nível; Anterior e Próxima mudam a página da listagem.",
            },
            {
                "title": "Somente leitura",
                "text": "Nada é alterado no share ao navegar ou baixar arquivos.",
            },
        ],
    },
    "history_browse": {
        "title": "Explorar snapshot",
        "summary": "Navega pelos arquivos de um share dentro de um snapshot.",
        "chapters": [
            {
                "title": "Pastas e arquivos",
                "text": "Abrir entra na pasta; Baixar salva o arquivo selecionado.",
            },
            {
                "title": "Snapshots",
                "text": "Escolha outro snapshot na lista lateral para comparar estados.",
            },
            {
                "title": "Versões",
                "text": "Mostra as versões anteriores do arquivo nos outros snapshots.",
            },
            {
                "title": "Navegação",
                "text": "Subir retorna um nível; Anterior e Próxima mudam a página.",
            },
            {
                "title": "Somente leitura",
                "text": "Nada é alterado no share ao navegar ou baixar arquivos.",
            },
        ],
    },
    "history_browse_root": {
        "title": "Explorar snapshot",
        "summary": "Navega pelos arquivos de um share dentro de um snapshot.",
        "chapters": [
            {
                "title": "Pastas e arquivos",
                "text": "Abrir entra na pasta; Baixar salva o arquivo selecionado.",
            },
            {
                "title": "Snapshots",
                "text": "Escolha outro snapshot na lista lateral para comparar estados.",
            },
            {
                "title": "Versões",
                "text": "Mostra as versões anteriores do arquivo nos outros snapshots.",
            },
            {
                "title": "Navegação",
                "text": "Subir retorna um nível; Anterior e Próxima mudam a página.",
            },
            {
                "title": "Somente leitura",
                "text": "Nada é alterado no share ao navegar ou baixar arquivos.",
            },
        ],
    },
    "history_versions": {
        "title": "Versões do arquivo",
        "summary": "Lista as versões de um arquivo encontradas nos snapshots.",
        "chapters": [
            {
                "title": "Lista de versões",
                "text": "As versões aparecem da mais nova para a mais antiga, com data e tamanho.",
            },
            {
                "title": "Baixar",
                "text": "Baixa a versão escolhida sem alterar o arquivo atual.",
            },
            {
                "title": "Voltar à pasta",
                "text": "Retorna ao diretório de origem no snapshot selecionado.",
            },
        ],
    },
    "storage_index": {
        "title": "Discos",
        "summary": "Identificação, estado e SMART dos discos físicos do host.",
        "chapters": [
            {
                "title": "Discos físicos",
                "text": (
                    "Mostra modelo, serial, tamanho, estado, temperatura e "
                    "resumo SMART de cada disco."
                ),
            },
            {
                "title": "Atualizar agora",
                "text": (
                    "Força uma coleta imediata. A rotina normal é diária e não "
                    "acorda discos em standby."
                ),
            },
            {
                "title": "Ler SMART",
                "text": (
                    "Consulta os atributos sob demanda. Em standby o botão fica "
                    "desabilitado para não acordar o disco."
                ),
            },
            {
                "title": "Teste curto",
                "text": "Teste rápido de integridade; pode ocupar o disco por alguns minutos.",
            },
            {
                "title": "Teste longo",
                "text": "Pode levar horas e ocupar o disco. Use com cautela.",
            },
            {
                "title": "Diagnóstico",
                "text": "Resume alertas e problemas detectados nos discos.",
            },
        ],
    },
    "storage_smart": {
        "title": "SMART do disco",
        "summary": "Atributos SMART lidos sob demanda de um disco.",
        "chapters": [
            {
                "title": "Tabela de atributos",
                "text": "Mostra ID, atributo, valor, pior valor, limite e valor bruto.",
            },
            {
                "title": "Leitura apenas",
                "text": "Esta página não inicia testes; ela apenas exibe a leitura atual.",
            },
            {
                "title": "Interpretação",
                "text": (
                    "Compare o valor com o limite e observe crescimento de "
                    "setores realocados ou erros."
                ),
            },
        ],
    },
    "backup_index": {
        "title": "Backups",
        "summary": "Backups locais, do Gitea e repositórios restic.",
        "chapters": [
            {
                "title": "Atalhos",
                "text": "Levam para backup de arquivos, Gitea, snapshots, cópia fria e senha do repositório.",
            },
            {
                "title": "Discos",
                "text": (
                    "Prepara ou reconfigura um disco externo. A formatação exige "
                    "senha do app e a frase de confirmação."
                ),
            },
            {
                "title": "Jobs restic",
                "text": "Mostra destino, fontes, agenda, retenção, status e próxima execução.",
            },
            {
                "title": "Rodar agora",
                "text": "Dispara o job imediatamente, sem esperar o timer.",
            },
            {
                "title": "Editar",
                "text": "Altera fontes, agenda, retenção e ativação do job.",
            },
            {
                "title": "Avisos",
                "text": (
                    "Sem restic ou sem disco configurado, os jobs ficam "
                    "aguardando; o backup local de arquivos continua funcionando."
                ),
            },
        ],
    },
    "backup_snapshots": {
        "title": "Snapshots restic",
        "summary": "Pontos de restauração disponíveis no repositório.",
        "chapters": [
            {
                "title": "Lista de snapshots",
                "text": "Mostra disco, identificador, data, arquivos, tamanho e fontes.",
            },
            {
                "title": "Navegar",
                "text": "Abre o conteúdo do snapshot para consultar e baixar arquivos.",
            },
            {
                "title": "Snapshot vazio",
                "text": "Um snapshot sem arquivos ainda não contém dados para restaurar.",
            },
        ],
    },
    "backup_snapshot_browse": {
        "title": "Navegar no snapshot",
        "summary": "Explora o conteúdo de um snapshot restic.",
        "chapters": [
            {
                "title": "Pastas e arquivos",
                "text": "Mostra nome, tipo, tamanho, data e permissões de cada item.",
            },
            {
                "title": "Baixar",
                "text": "Baixa o arquivo selecionado sem alterar o repositório.",
            },
            {
                "title": "Subir",
                "text": "Retorna um nível na árvore do snapshot.",
            },
            {
                "title": "Somente leitura",
                "text": "A navegação não modifica o snapshot nem os dados atuais.",
            },
        ],
    },
    "backup_disk_wizard": {
        "title": "Preparar disco",
        "summary": "Formata um disco externo como ext4 e cria o repositório restic.",
        "chapters": [
            {
                "title": "Disco selecionado",
                "text": "Confira dispositivo, modelo, serial e tamanho antes de continuar.",
            },
            {
                "title": "Formatação",
                "text": (
                    "O disco será formatado e todo o conteúdo atual será "
                    "apagado. Disco com filesystem ou já configurado pede "
                    "confirmação extra."
                ),
            },
            {
                "title": "Label",
                "text": "Nome curto usado no ponto de montagem e no caminho do repositório.",
            },
            {
                "title": "Confirmação",
                "text": (
                    "Marque o aviso, digite a frase pedida e informe a senha do "
                    "app para liberar o botão."
                ),
            },
            {
                "title": "Depois de preparar",
                "text": "O disco é montado e o repositório restic fica pronto para os jobs.",
            },
        ],
    },
    "backup_credentials": {
        "title": "Credenciais do restic",
        "summary": "Consulta a senha do repositório restic de um disco.",
        "chapters": [
            {
                "title": "Consultar senha",
                "text": "Escolha o disco/repositório e informe a senha do app.",
            },
            {
                "title": "Senha do restic",
                "text": (
                    "A senha fica em arquivo root-only no host. Ela é necessária "
                    "para restaurar backups fora deste painel."
                ),
            },
            {
                "title": "Copiar",
                "text": "Copia a senha para a área de transferência.",
            },
            {
                "title": "Cuidado",
                "text": "Não armazene a senha em locais compartilhados ou sem proteção.",
            },
        ],
    },
    "gitea_backup": {
        "title": "Backup do Gitea",
        "summary": "Dump consistente do Gitea e cópia manual para um drive USB.",
        "chapters": [
            {
                "title": "Estado",
                "text": "Mostra se o container está ativo, o volume, a retenção e a etapa atual.",
            },
            {
                "title": "Dump no servidor",
                "text": (
                    "Roda gitea dump sem parar o container e mantém os últimos "
                    "dumps no servidor."
                ),
            },
            {
                "title": "Backup para USB",
                "text": (
                    "Monta o drive, copia o dump, confere o hash e desmonta no "
                    "final."
                ),
            },
            {
                "title": "Drives USB",
                "text": (
                    "Apenas drives com filesystem aparecem como destino. Os "
                    "arquivos existentes no drive não são apagados."
                ),
            },
            {
                "title": "Dumps no servidor",
                "text": "Lista os arquivos disponíveis com data e tamanho.",
            },
            {
                "title": "Cuidado",
                "text": "Não desconecte o drive durante a cópia ou a verificação do hash.",
            },
        ],
    },
    "arquivos_backup_index": {
        "title": "Backup local de arquivos",
        "summary": "Jobs que geram pacotes locais de pastas e configurações.",
        "chapters": [
            {
                "title": "Jobs",
                "text": "Lista os jobs com fontes, agenda, retenção e último resultado.",
            },
            {
                "title": "Novo job",
                "text": "Cria um job com fontes, periodicidade e retenção próprias.",
            },
            {
                "title": "Novo job de apps",
                "text": "Abre um modelo pronto para os dados dos aplicativos.",
            },
            {
                "title": "Abrir",
                "text": "Mostra detalhes, pacotes gerados, verificação e restore.",
            },
        ],
    },
    "arquivos_job_new": {
        "title": "Novo job de backup",
        "summary": "Cria um job local de backup de arquivos.",
        "chapters": [
            {
                "title": "Nome e rótulo",
                "text": "O nome identifica o job; o rótulo aparece na interface.",
            },
            {
                "title": "Fontes",
                "text": "Informe uma pasta ou arquivo por linha.",
            },
            {
                "title": "Periodicidade",
                "text": "Escolha diária, semanal ou mensal e o horário de execução.",
            },
            {
                "title": "Retenção",
                "text": "Define por quantos dias os pacotes gerados são mantidos.",
            },
            {
                "title": "Job ativo",
                "text": "Somente jobs ativos entram na agenda automática.",
            },
        ],
    },
    "arquivos_job_edit": {
        "title": "Editar job de backup",
        "summary": "Altera fontes, agenda e retenção de um job local.",
        "chapters": [
            {
                "title": "Fontes",
                "text": "Informe uma pasta ou arquivo por linha.",
            },
            {
                "title": "Periodicidade",
                "text": "Escolha diária, semanal ou mensal e o horário de execução.",
            },
            {
                "title": "Retenção",
                "text": "Define por quantos dias os pacotes gerados são mantidos.",
            },
            {
                "title": "Job ativo",
                "text": "Desmarcar tira o job da agenda sem apagar os pacotes existentes.",
            },
        ],
    },
    "arquivos_job": {
        "title": "Job de backup de arquivos",
        "summary": "Detalhes, execução, pacotes e restore de um job local.",
        "chapters": [
            {
                "title": "Fontes",
                "text": "Mostra os itens incluídos no job e o estado de cada um.",
            },
            {
                "title": "Rodar agora",
                "text": "Gera um pacote imediatamente, sem esperar a agenda.",
            },
            {
                "title": "Backup para USB",
                "text": "Copia o pacote para um drive USB conectado.",
            },
            {
                "title": "Agenda",
                "text": "Mostra frequência, retenção e o próximo horário previsto.",
            },
            {
                "title": "Pacotes de backup",
                "bullets": [
                    "Verificar confere a integridade e o hash do pacote.",
                    "Baixar salva o pacote no computador.",
                    "Restaurar substitui os dados do job e exige digitar o nome do pacote.",
                ],
            },
            {
                "title": "Excluir job",
                "text": "Remove o job da agenda, mas mantém os pacotes já gerados no disco.",
            },
        ],
    },
    "cold_index": {
        "title": "Cópia fria (USB)",
        "summary": "Copia os snapshots do repositório primário para um drive USB offline.",
        "chapters": [
            {
                "title": "Origem e destino",
                "text": "Mostra o repositório primário e o drive frio configurado.",
            },
            {
                "title": "Drives USB",
                "text": "Prepare um drive para virar repositório frio e pronto para uso offline.",
            },
            {
                "title": "Copiar agora",
                "text": (
                    "Copia os snapshots, roda restic check e grava o status. A "
                    "cópia roda em segundo plano."
                ),
            },
            {
                "title": "Ejetar com segurança",
                "text": "Desmonta o drive para poder desconectá-lo sem risco.",
            },
            {
                "title": "Cuidado",
                "text": "Não ejete nem desconecte o drive durante a cópia.",
            },
        ],
    },
    "cold_prepare": {
        "title": "Preparar drive frio",
        "summary": "Formata o drive USB como ext4 e cria o repositório restic frio.",
        "chapters": [
            {
                "title": "Disco selecionado",
                "text": "Confira dispositivo, modelo, serial e tamanho antes de continuar.",
            },
            {
                "title": "Formatação",
                "text": "O drive será formatado em ext4 e todo o conteúdo atual será apagado.",
            },
            {
                "title": "Label",
                "text": "Nome curto do drive, usado no ponto de montagem.",
            },
            {
                "title": "Confirmação",
                "text": (
                    "Marque o aviso, digite a frase pedida e informe a senha do "
                    "app para liberar o botão."
                ),
            },
            {
                "title": "Depois de preparar",
                "text": "O repositório frio é criado e fica pronto para a próxima cópia.",
            },
        ],
    },
    "backup_job_new": {
        "title": "Novo job restic",
        "summary": "Cria um job de backup incremental com repositório restic.",
        "chapters": [
            {
                "title": "Nome e destino",
                "text": "Escolha um nome curto e o disco/repositório que receberá os snapshots.",
            },
            {
                "title": "Fontes",
                "text": "Selecione os shares que entram no backup.",
            },
            {
                "title": "Exclusões",
                "text": (
                    "Uma regra por linha. Restaurar lista padrão volta às "
                    "exclusões recomendadas."
                ),
            },
            {
                "title": "Periodicidade",
                "text": "Define frequência, horário e, conforme o caso, dia da semana ou do mês.",
            },
            {
                "title": "Retenção",
                "text": "Define quantos snapshots diários, semanais e mensais o restic preserva.",
            },
            {
                "title": "Job ativo",
                "text": "Cria ou atualiza o timer do systemd; sem marcar, o job não roda sozinho.",
            },
        ],
    },
    "backup_job_edit": {
        "title": "Editar job restic",
        "summary": "Altera fontes, agenda, retenção e ativação de um job restic.",
        "chapters": [
            {
                "title": "Fontes e exclusões",
                "text": "Ajuste os shares incluídos e as regras de exclusão do backup.",
            },
            {
                "title": "Periodicidade",
                "text": "Define frequência, horário e, conforme o caso, dia da semana ou do mês.",
            },
            {
                "title": "Retenção",
                "text": "Define quantos snapshots diários, semanais e mensais o restic preserva.",
            },
            {
                "title": "Job ativo",
                "text": "Desmarcar remove o timer e impede novas execuções automáticas.",
            },
            {
                "title": "Excluir job",
                "text": (
                    "Remove a configuração do job. Os snapshots já gravados no "
                    "repositório permanecem."
                ),
            },
        ],
    },
}


USE_CASES: dict[str, str] = {
    "dashboard": (
        "Use ao abrir o painel ou depois de um alerta para saber, em uma tela, "
        "se discos, serviços, backups e shares estão saudáveis. Exemplo: antes "
        "de copiar arquivos importantes, confira o espaço do volume e se o "
        "último backup restic terminou bem."
    ),
    "network_index": (
        "Use quando precisar liberar ou fechar uma porta e também para "
        "diagnosticar a rede. Exemplo: libere 8080/tcp apenas para "
        "192.168.0.0/24, ative o UFW com SSH garantido e, se um app parar, "
        "confira portas, rotas e regras antes de mexer no Caddy."
    ),
    "containers": (
        "Use no dia a dia para reiniciar um serviço travado e conferir o que "
        "está rodando. Exemplo: depois de atualizar uma imagem, reinicie o "
        "container e acompanhe pelos logs; o container do próprio painel fica "
        "protegido."
    ),
    "container_logs": (
        "Use quando um serviço para de responder ou reinicia sozinho. Exemplo: "
        "se o Gitea mostrar erro 502, veja as últimas linhas do container para "
        "identificar disco cheio, permissão ou configuração."
    ),
    "users": (
        "Use para conferir quem tem conta e quais pastas cada pessoa acessa. "
        "Exemplo: num chamado de 'não abro a pasta Projetos', verifique se a "
        "pessoa está ativa e no grupo certo; se o Credenciais gerencia "
        "usuários, o ajuste é feito lá."
    ),
    "user_create": (
        "Use ao cadastrar alguém que ainda não existe no servidor, quando a "
        "gestão é local. Exemplo: crie a conta, defina a senha inicial, marque "
        "os grupos das pastas e peça a troca no primeiro acesso."
    ),
    "user_password": (
        "Use quando alguém esqueceu a senha ou precisa de uma senha temporária. "
        "Exemplo: defina uma nova senha, informe à pessoa e oriente a troca no "
        "próximo login."
    ),
    "user_groups": (
        "Use para liberar ou retirar acesso a pastas sem excluir a conta. "
        "Exemplo: ao mudar alguém de setor, marque os grupos novos e desmarque "
        "os antigos; o acesso ao Samba muda na hora."
    ),
    "group_create": (
        "Use quando uma nova pasta compartilhada precisa de um grupo próprio. "
        "Exemplo: crie o grupo, associe ao share e inclua as pessoas que devem "
        "acessá-lo."
    ),
    "shares": (
        "Use para ver o que está compartilhado, quanto ocupa e quem acessa. "
        "Exemplo: antes de criar um share ou investigar espaço em disco, "
        "confira o uso dos dados e dos snapshots."
    ),
    "share_create": (
        "Use ao disponibilizar uma nova pasta na rede. Exemplo: crie o share "
        "com snapshot, defina quantas versões manter e libere os grupos certos; "
        "o Samba é validado e recarregado."
    ),
    "snapshots": (
        "Use para proteger uma pasta antes de uma mudança ou voltar a um estado "
        "anterior. Exemplo: antes de uma migração, crie um snapshot agora; se "
        "algo der errado, navegue pela versão anterior."
    ),
    "history_index": (
        "Use para recuperar um arquivo apagado ou comparar versões. Exemplo: "
        "alguém apagou uma planilha por engano; escolha o share e abra o "
        "snapshot de antes da exclusão."
    ),
    "history_share": (
        "Use para restaurar um arquivo sem alterar o share atual. Exemplo: "
        "encontre a pasta no snapshot, baixe a versão antiga e devolva ao share."
    ),
    "history_browse": (
        "Use para restaurar um arquivo sem alterar o share atual. Exemplo: "
        "encontre a pasta no snapshot, baixe a versão antiga e devolva ao share."
    ),
    "history_browse_root": (
        "Use para restaurar um arquivo sem alterar o share atual. Exemplo: "
        "encontre a pasta no snapshot, baixe a versão antiga e devolva ao share."
    ),
    "history_versions": (
        "Use quando o arquivo existe, mas o conteúdo mudou ou foi sobrescrito. "
        "Exemplo: compare as versões do contrato e baixe a que estava correta."
    ),
    "storage_index": (
        "Use para acompanhar a saúde dos discos e agir antes de uma falha. "
        "Exemplo: temperatura alta ou setores realocados aparecem aqui; rode um "
        "teste curto e planeje a troca."
    ),
    "storage_smart": (
        "Use quando precisar do detalhe técnico de um disco suspeito. Exemplo: "
        "antes de abrir RMA ou trocar o disco, leia os atributos SMART e guarde "
        "o diagnóstico."
    ),
    "backup_index": (
        "Use para conferir se as rotinas de backup estão acontecendo e agir "
        "quando um job falha. Exemplo: o backup diário do Credenciais falhou; "
        "abra o job, rode agora e confira o status."
    ),
    "backup_snapshots": (
        "Use quando precisar restaurar um arquivo de uma data específica. "
        "Exemplo: recupere uma configuração de duas semanas atrás sem depender "
        "do snapshot do share."
    ),
    "backup_snapshot_browse": (
        "Use para localizar e baixar um arquivo específico de um snapshot "
        "restic. Exemplo: encontre o .env antigo de um app e baixe para "
        "comparar com o atual."
    ),
    "backup_disk_wizard": (
        "Use quando chega um disco externo novo para backup. Exemplo: conecte o "
        "USB, prepare o disco, crie o repositório restic e depois aponte o job "
        "para ele."
    ),
    "backup_credentials": (
        "Use quando precisa restaurar fora do painel ou guardar a senha do "
        "repositório. Exemplo: num restore de emergência, consulte a senha e "
        "use com o restic no terminal."
    ),
    "gitea_backup": (
        "Use antes de atualizações do Gitea ou periodicamente para ter um dump "
        "fora do servidor. Exemplo: gere o dump e copie para o USB; se o "
        "container quebrar, você tem o arquivo e o hash."
    ),
    "arquivos_backup_index": (
        "Use para proteger pastas que não estão em um repositório restic. "
        "Exemplo: crie um job para documentos e configurações e rode antes de "
        "uma atualização."
    ),
    "arquivos_job_new": (
        "Use ao incluir uma nova pasta ou mudar a frequência do backup local. "
        "Exemplo: adicione /etc/... como fonte e ajuste a retenção para 30 dias."
    ),
    "arquivos_job_edit": (
        "Use ao ajustar um backup local existente. Exemplo: inclua uma pasta "
        "nova ou mude o horário e salve; o job passa a usar a nova agenda."
    ),
    "arquivos_job": (
        "Use para rodar um backup fora de hora, verificar um pacote ou "
        "restaurar dados. Exemplo: antes de mexer numa configuração, rode agora "
        "e, se precisar, restaure o pacote anterior."
    ),
    "cold_index": (
        "Use periodicamente para tirar uma cópia offline do backup. Exemplo: "
        "conecte o drive frio, copie os snapshots e ejete; guarde o drive fora "
        "do servidor."
    ),
    "cold_prepare": (
        "Use na primeira vez que um drive USB vira cópia fria. Exemplo: prepare "
        "o drive, copie o repositório e guarde-o desconectado."
    ),
    "backup_job_new": (
        "Use ao criar uma rotina restic. Exemplo: defina os shares, a agenda e "
        "a retenção; rode uma vez manualmente para validar antes de confiar no "
        "timer."
    ),
    "backup_job_edit": (
        "Use ao ajustar uma rotina restic existente. Exemplo: inclua um share "
        "novo ou mude o horário e rode uma vez para confirmar."
    ),
}

for _rota, _texto in USE_CASES.items():
    AJUDA[_rota]["use_case"] = _texto


def ajuda_para(url_name: str | None) -> dict[str, Any] | None:
    """Devolve a ajuda da rota ou ``None`` quando não há conteúdo."""
    if not url_name:
        return None
    return AJUDA.get(url_name)


def page_help(request) -> dict[str, Any | None]:
    """Context processor: ajuda correspondente à rota resolvida."""
    match = getattr(request, "resolver_match", None)
    url_name = getattr(match, "url_name", None) if match else None
    return {"page_help": ajuda_para(url_name)}

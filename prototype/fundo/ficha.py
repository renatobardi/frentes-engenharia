"""PROTÓTIPO DESCARTÁVEL (#13) — ficha do time: objetos, serviços e fornecedor de cada um dos 24 times.

Provisória, escrita à mão. O roteiro sorteia um objeto (texto livre) ou um serviço (log, webhook, banco)
da ficha do time junto com o cenário do fundo, para o texto carregar o time sem citar o nome dele.
A MESMA ficha vira o critério da pergunta de área do Jev, mas só em parte: o critério lista os 3 primeiros
objetos, os 2 primeiros serviços e o fornecedor (LISTADOS); os 2 últimos objetos e o 3º serviço são itens de fora.
Regra: nenhum item repete o objeto de uma história plantada (gravame no Detran, valor do boleto,
simulação/status/comissão no portal, esteira de propostas, assistente de IA, deploy do motor)."""

N_OBJ_LISTADOS, N_SVC_LISTADOS = 3, 2

FICHA = {
    # Originação
    'Simulação': dict(
        objetos=['o simulador de parcelas', 'a tabela de taxas e prazos', 'o cálculo do CET', 'a simulação de energia solar', 'o comparador de planos'],
        servicos=['simulador-api', 'tabela-taxas', 'cet-calculo'], fornecedor='o fornecedor da tabela de preços de veículos'),
    'Proposta': dict(
        objetos=['a tela de digitação da proposta', 'a fila de pendências de proposta', 'o checklist de documentos da proposta', 'o reenvio de proposta recusada', 'a cópia de proposta para outro veículo'],
        servicos=['proposta-digitacao', 'pendencias-worker', 'proposta-reenvio'], fornecedor='o fornecedor de OCR de documentos'),
    'Cadastro e KYC': dict(
        objetos=['a ficha cadastral do cliente', 'a validação de CPF e renda', 'a biometria facial do cadastro', 'a consulta à Receita Federal', 'a atualização cadastral periódica'],
        servicos=['cadastro-cliente', 'kyc-validador', 'receita-consulta'], fornecedor='o fornecedor de biometria facial'),
    # Crédito
    'Motor de Decisão': dict(
        objetos=['a fila de análise automática', 'o score interno', 'a mesa de crédito', 'o cálculo de limite do cliente', 'a reanálise de proposta negada'],
        servicos=['decisao-engine', 'score-calc', 'limite-calc'], fornecedor='o bureau de crédito'),
    'Políticas de Crédito': dict(
        objetos=['o cadastro de regras de política', 'as alçadas de aprovação', 'o simulador de impacto de política', 'a tabela de risco por produto', 'o comitê de exceções de crédito'],
        servicos=['politicas-regras', 'alcadas-api', 'risco-tabela'], fornecedor='a consultoria de modelagem de risco'),
    'Antifraude': dict(
        objetos=['a lista de bloqueio de CPFs', 'a análise de documentos suspeitos', 'os alertas de fraude da mesa', 'a validação de selfie com documento', 'o monitoramento de lojas suspeitas'],
        servicos=['fraude-score', 'lista-restritiva', 'lojas-monitor'], fornecedor='o fornecedor de score de fraude'),
    # Formalização
    'Contratos': dict(
        objetos=['a geração da CCB', 'a minuta do contrato', 'o aditivo contratual', 'o cálculo do IOF no contrato', 'o arquivo digital de contratos'],
        servicos=['contrato-gerador', 'ccb-emissor', 'contrato-arquivo'], fornecedor='o cartório parceiro de registro de contratos'),
    'Documentação e Assinatura': dict(
        objetos=['a assinatura eletrônica', 'o upload de documentos do cliente', 'a conferência de documentos', 'o envio do link de assinatura por SMS', 'a validade dos documentos enviados'],
        servicos=['assinatura-digital', 'docs-upload', 'docs-validade'], fornecedor='a plataforma de assinatura eletrônica'),
    'Gravame': dict(
        objetos=['a consulta de restrições do veículo', 'o cadastro de chassi e placa', 'a tabela de taxas dos Detrans', 'a vistoria do veículo', 'a transferência de propriedade do veículo'],
        servicos=['veiculo-consulta', 'chassi-cadastro', 'vistoria-agenda'], fornecedor='o despachante parceiro'),
    # Canal Parceiro
    'Portal do Lojista': dict(
        objetos=['o login e as permissões do lojista', 'o cadastro de lojas e vendedores', 'o material de campanha no portal', 'o treinamento online dos vendedores', 'os avisos e comunicados do portal'],
        servicos=['lojista-acesso', 'lojas-cadastro', 'portal-comunicados'], fornecedor='a agência que mantém o layout do portal'),
    'Correspondentes': dict(
        objetos=['o credenciamento de correspondentes', 'a certificação dos agentes', 'a agenda de visitas às lojas', 'o ranking de produção dos correspondentes', 'o contrato de correspondente'],
        servicos=['correspondente-cadastro', 'credenciamento-api', 'correspondente-ranking'], fornecedor='a certificadora de correspondentes'),
    'Comissionamento de Parceiros': dict(
        objetos=['a nota fiscal dos parceiros', 'o bônus de campanha', 'o cadastro bancário do parceiro', 'a retenção de impostos do parceiro', 'o informe de rendimentos do parceiro'],
        servicos=['parceiro-pagamentos', 'nf-parceiros', 'parceiro-impostos'], fornecedor='o banco pagador dos parceiros'),
    # Canal Digital
    'App': dict(
        objetos=['o login por biometria no app', 'as notificações push', 'a tela de parcelas do app', 'a atualização de versão do app', 'o cadastro de senha e PIN'],
        servicos=['app-bff', 'push-notificacoes', 'app-auth'], fornecedor='o provedor de push e SMS'),
    'Jornada Online': dict(
        objetos=['o funil de contratação pelo site', 'o formulário de pré-análise', 'a página de ofertas', 'o chat de vendas do site', 'a retomada de contratação abandonada'],
        servicos=['jornada-web', 'pre-analise-form', 'ofertas-vitrine'], fornecedor='a agência de mídia e SEO'),
    'Marketplace de Veículos': dict(
        objetos=['os anúncios de veículos', 'a busca do marketplace', 'as fotos e laudos dos veículos', 'o cadastro de vendedores particulares', 'a tabela de preços de referência'],
        servicos=['anuncios-catalogo', 'busca-veiculos', 'precos-referencia'], fornecedor='a empresa de laudo veicular'),
    # Pós-venda e Cobrança
    'Boletos e Carnês': dict(
        objetos=['a segunda via pelo WhatsApp', 'o débito automático', 'o envio de carnês pelos Correios', 'o registro de boletos no banco', 'o aviso de vencimento por e-mail'],
        servicos=['segunda-via', 'debito-automatico', 'aviso-vencimento'], fornecedor='a gráfica dos carnês'),
    'Renegociação': dict(
        objetos=['a proposta de acordo', 'a régua de cobrança', 'o cálculo de desconto do acordo', 'a negativação em órgãos de proteção ao crédito', 'o discador de cobrança'],
        servicos=['acordo-calculo', 'regua-cobranca', 'negativacao-envio'], fornecedor='o escritório de cobrança terceirizado'),
    'Quitação e Baixa': dict(
        objetos=['o saldo devedor para quitação antecipada', 'a carta de quitação', 'a baixa do contrato', 'a devolução de valores pagos a mais', 'o termo de liberação do veículo'],
        servicos=['saldo-devedor', 'baixa-contrato', 'devolucao-valores'], fornecedor='o banco liquidante'),
    # Plataforma e Sustentação
    'Infra e Cloud': dict(
        objetos=['os clusters de Kubernetes', 'a rede e a VPN', 'o backup dos bancos', 'o gerenciador de segredos', 'as contas e permissões da nuvem'],
        servicos=['cluster-ingress', 'backup-agendador', 'cofre-segredos'], fornecedor='o provedor de nuvem'),
    'Observabilidade': dict(
        objetos=['a ferramenta de dashboards', 'a coleta de logs', 'a central de alertas', 'o rastreamento distribuído', 'o painel de disponibilidade'],
        servicos=['log-coletor', 'alertas-central', 'tracing-coletor'], fornecedor='o fornecedor da ferramenta de APM'),
    'Suporte N2/N3': dict(
        objetos=['a fila de chamados de sustentação', 'a escala de plantão', 'a base de conhecimento do suporte', 'o relatório de incidentes', 'o catálogo de serviços de TI'],
        servicos=['chamados-fila', 'plantao-escala', 'incidentes-relatorio'], fornecedor='a empresa terceirizada de suporte N1'),
    # Dados e Regulatório
    'Engenharia de Dados': dict(
        objetos=['o data lake', 'as cargas do DW', 'o catálogo de dados', 'os pipelines de ingestão', 'a camada de indicadores dos painéis'],
        servicos=['dw-carga', 'lake-ingestao', 'indicadores-api'], fornecedor='o fornecedor da plataforma de dados'),
    'Relatórios Regulatórios': dict(
        objetos=['o envio do SCR ao Banco Central', 'o fechamento contábil mensal', 'o relatório de reclamações ao regulador', 'a base de risco de crédito para o regulador', 'o demonstrativo de limites operacionais'],
        servicos=['scr-gerador', 'regulatorio-envio', 'contabil-fechamento'], fornecedor='a auditoria externa'),
    'Privacidade (LGPD)': dict(
        objetos=['os pedidos de titulares', 'o registro de consentimento', 'o mapa de dados pessoais', 'o inventário de bases com dados sensíveis', 'a anonimização para ambientes de teste'],
        servicos=['consentimento-api', 'titulares-portal', 'anonimizador'], fornecedor='o escritório de advocacia de privacidade'),
}

# o que cada time faz, em uma frase: vira o critério da opção na pergunta de área do Jev (variante "frase")
FRASE = {
    "Simulação": "calcula parcelas, taxas e prazos de um financiamento antes de a proposta existir",
    "Proposta": "recebe e acompanha a proposta de financiamento, da digitação até o envio para análise",
    "Cadastro e KYC": "cadastra o cliente e confere a identidade, o CPF e a renda dele",
    "Motor de Decisão": "decide automaticamente se o crédito é aprovado, com score e consulta a bureaus",
    "Políticas de Crédito": "define e mantém as regras e as alçadas de aprovação de crédito",
    "Antifraude": "detecta fraude em propostas e documentos e mantém as listas de bloqueio",
    "Contratos": "gera o contrato de financiamento (a CCB), as minutas e os aditivos",
    "Documentação e Assinatura": "recebe e confere os documentos do cliente e colhe a assinatura eletrônica",
    "Gravame": "registra a alienação do veículo nos Detrans e mantém os dados do veículo financiado",
    "Portal do Lojista": "mantém o portal em que lojistas e concessionárias entram, cadastram vendedores e operam",
    "Correspondentes": "credencia, certifica e acompanha os correspondentes que visitam as lojas",
    "Comissionamento de Parceiros": "calcula e paga comissões e bônus a lojistas e correspondentes",
    "App": "mantém o aplicativo do cliente final: login, notificações, consulta de parcelas",
    "Jornada Online": "mantém a contratação pelo site: ofertas, pré-análise e funil de conversão",
    "Marketplace de Veículos": "mantém a vitrine de veículos à venda: anúncios, busca, fotos e laudos",
    "Boletos e Carnês": "emite e entrega boletos e carnês e cuida do débito automático das parcelas",
    "Renegociação": "cobra clientes em atraso e monta acordos e descontos de renegociação",
    "Quitação e Baixa": "calcula o saldo devedor, quita o financiamento e dá baixa no contrato",
    "Infra e Cloud": "opera a infraestrutura comum a todos os times: nuvem, clusters, rede e backup",
    "Observabilidade": "mantém as ferramentas comuns de monitoria: coleta de logs, dashboards e central de alertas",
    "Suporte N2/N3": "atende os chamados de sustentação e mantém a escala de plantão",
    "Engenharia de Dados": "mantém o data lake, o DW e as cargas de dados usadas por toda a empresa",
    "Relatórios Regulatórios": "gera e envia os relatórios obrigatórios ao Banco Central e o fechamento contábil",
    "Privacidade (LGPD)": "atende os pedidos de titulares de dados e controla consentimento e dados pessoais",
}
INSTRUCAO_AREA = ("Qual time de tecnologia é o DONO do sistema, da tela ou da rotina de que esta frente fala? "
                  "Escolha o time dono do que está com problema ou vai ser melhorado, mesmo que outro time (infraestrutura, dados, "
                  "segurança) seja quem conserta. Só escolha um time de plataforma quando o próprio objeto da frente for dele.")

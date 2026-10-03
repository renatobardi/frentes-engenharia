"""PROTÓTIPO DESCARTÁVEL (#13) — ficha do time: objetos, serviços e fornecedor de cada um dos 24 times.

Provisória, escrita à mão. O roteiro sorteia um objeto (texto livre) ou um serviço (log, webhook, banco)
da ficha do time junto com o cenário do fundo, para o texto carregar o time sem citar o nome dele.
Regra: nenhum item repete o objeto de uma história plantada (gravame no Detran, valor do boleto,
simulação/status/comissão no portal, esteira de propostas, assistente de IA, deploy do motor)."""

FICHA = {
    # Originação
    "Simulação": dict(objetos=["o simulador de parcelas", "a tabela de taxas e prazos", "o cálculo do CET"],
                      servicos=["simulador-api", "tabela-taxas"], fornecedor=None),
    "Proposta": dict(objetos=["a tela de digitação da proposta", "a fila de pendências de proposta", "o checklist de documentos da proposta"],
                     servicos=["proposta-digitacao", "pendencias-worker"], fornecedor=None),
    "Cadastro e KYC": dict(objetos=["a ficha cadastral do cliente", "a validação de CPF e renda", "a biometria facial do cadastro"],
                           servicos=["cadastro-cliente", "kyc-validador"], fornecedor="o fornecedor de biometria facial"),
    # Crédito
    "Motor de Decisão": dict(objetos=["a fila de análise automática", "o score interno", "a mesa de crédito"],
                             servicos=["decisao-engine", "score-calc"], fornecedor="o bureau de crédito"),
    "Políticas de Crédito": dict(objetos=["o cadastro de regras de política", "as alçadas de aprovação", "o simulador de impacto de política"],
                                 servicos=["politicas-regras", "alcadas-api"], fornecedor=None),
    "Antifraude": dict(objetos=["a lista de bloqueio de CPFs", "a análise de documentos suspeitos", "os alertas de fraude da mesa"],
                       servicos=["fraude-score", "lista-restritiva"], fornecedor="o fornecedor de score de fraude"),
    # Formalização
    "Contratos": dict(objetos=["a geração da CCB", "a minuta do contrato", "o aditivo contratual"],
                      servicos=["contrato-gerador", "ccb-emissor"], fornecedor=None),
    "Documentação e Assinatura": dict(objetos=["a assinatura eletrônica", "o upload de documentos do cliente", "a conferência de documentos"],
                                      servicos=["assinatura-digital", "docs-upload"], fornecedor="a plataforma de assinatura eletrônica"),
    "Gravame": dict(objetos=["a consulta de restrições do veículo", "o cadastro de chassi e placa", "a tabela de taxas dos Detrans"],
                    servicos=["veiculo-consulta", "chassi-cadastro"], fornecedor=None),
    # Canal Parceiro
    "Portal do Lojista": dict(objetos=["o login e as permissões do lojista", "o cadastro de lojas e vendedores", "o material de campanha no portal"],
                              servicos=["lojista-acesso", "lojas-cadastro"], fornecedor=None),
    "Correspondentes": dict(objetos=["o credenciamento de correspondentes", "a certificação dos agentes", "a agenda de visitas às lojas"],
                            servicos=["correspondente-cadastro", "credenciamento-api"], fornecedor="a certificadora de correspondentes"),
    "Comissionamento de Parceiros": dict(objetos=["a nota fiscal dos parceiros", "o bônus de campanha", "o cadastro bancário do parceiro"],
                                         servicos=["parceiro-pagamentos", "nf-parceiros"], fornecedor=None),
    # Canal Digital
    "App": dict(objetos=["o login por biometria no app", "as notificações push", "a tela de parcelas do app"],
                servicos=["app-bff", "push-notificacoes"], fornecedor="o provedor de push e SMS"),
    "Jornada Online": dict(objetos=["o funil de contratação pelo site", "o formulário de pré-análise", "a página de ofertas"],
                           servicos=["jornada-web", "pre-analise-form"], fornecedor=None),
    "Marketplace de Veículos": dict(objetos=["os anúncios de veículos", "a busca do marketplace", "as fotos e laudos dos veículos"],
                                    servicos=["anuncios-catalogo", "busca-veiculos"], fornecedor="a empresa de laudo veicular"),
    # Pós-venda e Cobrança
    "Boletos e Carnês": dict(objetos=["a segunda via pelo WhatsApp", "o débito automático", "o envio de carnês pelos Correios"],
                             servicos=["segunda-via", "debito-automatico"], fornecedor="a gráfica dos carnês"),
    "Renegociação": dict(objetos=["a proposta de acordo", "a régua de cobrança", "o cálculo de desconto do acordo"],
                         servicos=["acordo-calculo", "regua-cobranca"], fornecedor="o escritório de cobrança terceirizado"),
    "Quitação e Baixa": dict(objetos=["o saldo devedor para quitação antecipada", "a carta de quitação", "a baixa do contrato"],
                             servicos=["saldo-devedor", "baixa-contrato"], fornecedor=None),
    # Plataforma e Sustentação
    "Infra e Cloud": dict(objetos=["os clusters de Kubernetes", "a rede e a VPN", "o backup dos bancos"],
                          servicos=["cluster-ingress", "backup-agendador"], fornecedor="o provedor de nuvem"),
    "Observabilidade": dict(objetos=["a ferramenta de dashboards", "a coleta de logs", "a central de alertas"],
                            servicos=["log-coletor", "alertas-central"], fornecedor="o fornecedor da ferramenta de APM"),
    "Suporte N2/N3": dict(objetos=["a fila de chamados de sustentação", "a escala de plantão", "a base de conhecimento do suporte"],
                          servicos=["chamados-fila", "plantao-escala"], fornecedor=None),
    # Dados e Regulatório
    "Engenharia de Dados": dict(objetos=["o data lake", "as cargas do DW", "o catálogo de dados"],
                                servicos=["dw-carga", "lake-ingestao"], fornecedor=None),
    "Relatórios Regulatórios": dict(objetos=["o envio do SCR ao Banco Central", "o fechamento contábil mensal", "o relatório de reclamações ao regulador"],
                                    servicos=["scr-gerador", "regulatorio-envio"], fornecedor=None),
    "Privacidade (LGPD)": dict(objetos=["os pedidos de titulares", "o registro de consentimento", "o mapa de dados pessoais"],
                               servicos=["consentimento-api", "titulares-portal"], fornecedor=None),
}

# cenários do fundo que só fazem sentido em alguns times (o sorteio do time fica restrito a eles)
CENARIO_PRESO = {
    "fornecedor de bureau de crédito fora do SLA": ["Motor de Decisão", "Políticas de Crédito", "Antifraude", "Cadastro e KYC"],
    "prazo de envio de relatório ao regulador apertado": ["Relatórios Regulatórios", "Engenharia de Dados"],
    "pedido de titular LGPD atendido fora do prazo": ["Privacidade (LGPD)"],
    "cliente sem retorno sobre a proposta": ["Proposta", "Simulação", "Jornada Online", "Correspondentes", "Portal do Lojista"],
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

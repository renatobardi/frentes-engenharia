"""Os temas do fundo e os sintomas das histórias, com o texto de cada um para log, webhook e banco.

O fundo só tem espécie de queixa: nenhum sintoma daqui nomeia um objeto único da empresa. O
objeto ou o serviço entra no lugar de `{svc}`, vindo da ficha do time. Os sintomas das
histórias (H1–H7) são os únicos que nomeiam o objeto da história.

Cada sintoma é `(resumo, log, banco)`: o resumo vai no texto do webhook e da janela de log, o
`log` é a linha crua de log e o `banco` é o que a consulta de auditoria encontrou. Os
espaços reservados são `{svc}`, `{n}`, `{ms}`, `{pct}` e `{dias}`.
"""

from dataclasses import dataclass

Sintoma = tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class Tema:
    chave: str
    grupo: str  # "tecnico" ou "funcional"
    peso: float
    sintomas: tuple[Sintoma, ...]


TEMAS: tuple[Tema, ...] = (
    Tema(
        "divida-tecnica",
        "tecnico",
        1.0,
        (
            (
                "rotina de contorno antiga volta a falhar em {svc}",
                "contorno legado de {svc} excedeu {n} tentativas e foi abortado",
                "{n} registros de {svc} presos em estado intermediário por código legado",
            ),
            (
                "módulo sem manutenção em {svc} gera erro recorrente",
                "excecao em modulo legado de {svc}: tipo inesperado ({n} ocorrencias)",
                "{n} linhas de {svc} com formato antigo que o código atual não lê",
            ),
            (
                "correção emergencial em {svc} quebrou outra rotina",
                "regressao apos remendo em {svc}: {n} falhas em {ms} ms",
                "{n} lançamentos de {svc} divergentes depois de uma correção emergencial",
            ),
        ),
    ),
    Tema(
        "arquitetura",
        "tecnico",
        0.9,
        (
            (
                "acoplamento forte faz {svc} cair junto com os vizinhos",
                "{svc} sem resposta do vizinho há {ms} ms; cascata de erros iniciada",
                "{n} chamadas de {svc} presas esperando um serviço de outro time",
            ),
            (
                "{svc} não escala porque depende de um ponto único",
                "{svc} saturou o ponto único de dependência: fila em {n}",
                "tabela única de {svc} com {n} bloqueios simultâneos",
            ),
            (
                "mudança em {svc} exige alterar vários serviços ao mesmo tempo",
                "contrato de {svc} incompatível com {n} consumidores",
                "{n} consumidores de {svc} leem colunas que mudaram de significado",
            ),
        ),
    ),
    Tema(
        "observabilidade",
        "tecnico",
        0.9,
        (
            (
                "sem alerta quando {svc} degrada; descobrimos pelo cliente",
                "{svc} sem métrica de saúde nos últimos {n} minutos",
                "{n} intervalos sem nenhum registro de métrica de {svc}",
            ),
            (
                "logs de {svc} não permitem rastrear a requisição",
                "requisição em {svc} sem identificador de correlação ({n} casos)",
                "{n} eventos de {svc} sem identificador de correlação",
            ),
            (
                "painel de {svc} mostra dado atrasado",
                "coletor de {svc} atrasado {n} minutos",
                "painel de {svc} lendo uma carga {n} minutos defasada",
            ),
        ),
    ),
    Tema(
        "qualidade-de-dados",
        "tecnico",
        1.0,
        (
            (
                "dados duplicados em {svc} distorcem os números",
                "{svc} rejeitou carga: {n} chaves duplicadas",
                "{n} registros duplicados em {svc}",
            ),
            (
                "campos obrigatórios chegam vazios em {svc}",
                "validacao em {svc} falhou: {n} campos nulos",
                "{pct}% dos registros de {svc} com campo obrigatório vazio",
            ),
            (
                "valores de {svc} não batem com o sistema de origem",
                "conferencia de {svc} divergiu em {n} registros",
                "{n} diferenças entre {svc} e a origem na conferência diária",
            ),
        ),
    ),
    Tema(
        "performance",
        "tecnico",
        1.0,
        (
            (
                "{svc} está lento e estoura o tempo de resposta",
                "{svc} respondeu em {ms} ms, acima do limite combinado",
                "consulta de {svc} levou {ms} ms com {n} linhas varridas",
            ),
            (
                "{svc} consome memória até reiniciar",
                "{svc} reiniciado por falta de memória ({n} vezes na janela)",
                "{svc} com {n} conexões abertas sem uso",
            ),
            (
                "fila de {svc} cresce e não esvazia",
                "fila de {svc} chegou a {n} mensagens pendentes",
                "{n} itens parados na fila de {svc} há mais de {ms} ms",
            ),
        ),
    ),
    Tema(
        "custo-de-nuvem",
        "tecnico",
        0.8,
        (
            (
                "custo de {svc} na nuvem passou do orçamento do mês",
                "{svc} acima da cota de custo: {pct}% do orçamento consumido",
                "{n} recursos de {svc} sem dono e sem uso em {dias} dias",
            ),
            (
                "recursos de {svc} ficam ligados fora do horário",
                "{svc} sem desligamento programado há {dias} dias",
                "{n} instâncias de {svc} ativas sem tráfego",
            ),
            (
                "armazenamento de {svc} cresce sem política de descarte",
                "volume de {svc} em {pct}% da capacidade",
                "{n} arquivos antigos de {svc} sem política de descarte",
            ),
        ),
    ),
    Tema(
        "ambiente-de-dev",
        "tecnico",
        0.9,
        (
            (
                "ambiente de desenvolvimento de {svc} fora do ar",
                "ambiente de desenvolvimento de {svc} indisponível há {ms} ms",
                "{n} execuções de teste de {svc} abortadas no ambiente de desenvolvimento",
            ),
            (
                "dados de teste de {svc} desatualizados",
                "base de testes de {svc} com {dias} dias de defasagem",
                "{n} registros da base de testes de {svc} que não existem mais na origem",
            ),
            (
                "subir {svc} na máquina local leva horas",
                "preparação local de {svc} levou {ms} ms e falhou",
                "{n} dependências de {svc} sem versão fixada",
            ),
        ),
    ),
    Tema(
        "sdlc",
        "tecnico",
        0.25,
        (
            (
                "revisão de código de {svc} demora dias para começar",
                "pedido de revisão de {svc} aguardando há {dias} dias",
                "{n} pedidos de revisão de {svc} sem revisor",
            ),
            (
                "build de {svc} leva mais de meia hora",
                "build de {svc} terminou em {ms} ms, acima da meta",
                "{n} builds de {svc} acima da meta no período",
            ),
            (
                "histórico de versões de {svc} sem padrão de mensagem",
                "mensagem de versão de {svc} fora do padrão ({n} casos)",
                "{n} versões de {svc} sem descrição",
            ),
        ),
    ),
    Tema(
        "seguranca",
        "tecnico",
        0.25,
        (
            (
                "certificado de {svc} perto de vencer",
                "certificado de {svc} vence em {dias} dias",
                "{n} certificados de {svc} com vencimento em {dias} dias",
            ),
            (
                "senha fraca aceita em {svc}",
                "politica de senha de {svc} desativada ({n} contas afetadas)",
                "{n} contas de {svc} com senha abaixo da política",
            ),
            (
                "dado pessoal aparece em log de {svc}",
                "log de {svc} contem campo pessoal sem mascara ({n} linhas)",
                "{n} linhas de log de {svc} com dado pessoal sem máscara",
            ),
        ),
    ),
    Tema(
        "processo-manual",
        "funcional",
        1.2,
        (
            (
                "equipe refaz à mão uma etapa de {svc} todo dia",
                "etapa manual de {svc} pendente há {ms} ms; {n} itens na fila de revisão",
                "{n} itens de {svc} aguardando conferência manual",
            ),
            (
                "{svc} só fecha com conferência feita por fora, à mão, e ninguém confia",
                "conferencia por fora de {svc} rejeitou {n} linhas",
                "{n} linhas de {svc} só existem na conferência feita por fora",
            ),
            (
                "aprovação em {svc} depende de e-mail e atrasa",
                "aprovacao de {svc} sem resposta ha {dias} dias",
                "{n} aprovações de {svc} paradas aguardando resposta",
            ),
        ),
    ),
    Tema(
        "pessoas",
        "funcional",
        0.9,
        (
            (
                "falta quem conheça {svc} nas férias do responsável",
                "chamado de {svc} sem responsável designado ({n} em aberto)",
                "{n} itens de {svc} sem responsável atribuído",
            ),
            (
                "equipe de {svc} está no limite da capacidade",
                "fila de demandas de {svc} com {n} itens e {dias} dias de espera",
                "{n} demandas de {svc} sem previsão de atendimento",
            ),
            (
                "pouca documentação sobre {svc} para quem entra no time",
                "consulta ao manual de {svc} sem resultado ({n} buscas)",
                "{n} procedimentos de {svc} sem documento vinculado",
            ),
        ),
    ),
    Tema(
        "fornecedor",
        "funcional",
        1.0,
        (
            (
                "fornecedor {svc} fora do prazo combinado",
                "chamada ao fornecedor {svc} excedeu o prazo ({ms} ms)",
                "{n} solicitações ao fornecedor {svc} fora do prazo combinado",
            ),
            (
                "{svc} entrega dados com formato diferente do contrato",
                "retorno de {svc} fora do contrato em {n} chamadas",
                "{n} retornos do fornecedor {svc} com formato diferente do contrato",
            ),
            (
                "suporte do fornecedor {svc} não responde",
                "tentativa {n} de contato com o fornecedor {svc} sem retorno",
                "{n} chamados abertos com o fornecedor {svc} sem resposta há {dias} dias",
            ),
        ),
    ),
    Tema(
        "regulatorio",
        "funcional",
        0.8,
        (
            (
                "prazo de um relatório obrigatório de {svc} está em risco",
                "geracao de relatorio obrigatorio de {svc} atrasada {ms} ms",
                "{n} relatórios obrigatórios de {svc} com prazo em {dias} dias e dados incompletos",
            ),
            (
                "pedido de titular sobre dados de {svc} perto do prazo legal",
                "pedido de titular de {svc} aberto ha {dias} dias",
                "{n} pedidos de titulares de {svc} perto do prazo legal",
            ),
            (
                "evidência de controle exigida de {svc} não está guardada",
                "coleta de evidencia de {svc} falhou ({n} controles)",
                "{n} controles de {svc} sem evidência arquivada",
            ),
        ),
    ),
    Tema(
        "operacao-e-atendimento",
        "funcional",
        1.1,
        (
            (
                "atendimento recebe reclamação sobre {svc} sem resposta pronta",
                "{n} reclamacoes sobre {svc} sem roteiro de resposta",
                "{n} atendimentos de {svc} reabertos no período",
            ),
            (
                "fila de {svc} no suporte cresce a cada semana",
                "fila de suporte de {svc} em {n} chamados",
                "{n} chamados de {svc} acima do prazo de atendimento",
            ),
            (
                "operação de {svc} não sabe quem acionar de madrugada",
                "alerta de {svc} sem plantonista ({n} disparos sem resposta)",
                "{n} alertas de {svc} sem resposta na madrugada",
            ),
        ),
    ),
    Tema(
        "comunicacao-entre-areas",
        "funcional",
        0.9,
        (
            (
                "mudança em {svc} não foi avisada a quem depende dela",
                "consumidor de {svc} falhou após mudança sem aviso ({n} erros)",
                "{n} dependências de {svc} afetadas por uma mudança sem aviso",
            ),
            (
                "duas áreas mantêm regras diferentes para {svc}",
                "regra de {svc} divergente entre duas áreas ({n} casos)",
                "{n} registros de {svc} com regras conflitantes entre áreas",
            ),
            (
                "reunião de alinhamento sobre {svc} sempre adiada",
                "pendencia de alinhamento sobre {svc} aberta ha {dias} dias",
                "{n} decisões sobre {svc} aguardando alinhamento entre áreas",
            ),
        ),
    ),
)

# Os sintomas das histórias que usam template (a H4 só tem relato e mcp). Cada um cita o
# objeto da história.
HISTORIAS: dict[str, tuple[Sintoma, ...]] = {
    # Os quatro dizem a mesma coisa (a esteira cai ou fica lenta) e citam o serviço de infra
    # também no resumo, que é o texto do webhook: com "propostas travadas" e "falta de
    # capacidade" metade da história lia como fila, e o webhook sem o serviço ia para a área de
    # quem usa a esteira (#109).
    "H1": (
        (
            "esteira de propostas fora do ar no pico de fim de mês: {svc} não responde",
            "esteira de propostas sem resposta: {n} propostas afetadas, {svc} esgotado em {ms} ms",
            "",
        ),
        (
            "esteira de propostas lenta no pico de fim de mês: {svc} degradado",
            "esteira de propostas com tempo de etapa de {ms} ms; {n} propostas afetadas "
            "({svc} degradado)",
            "",
        ),
        (
            "esteira de propostas caiu depois do aumento de carga: {svc} reiniciou",
            "esteira de propostas indisponível: {svc} reiniciou {n} vezes desde a migração "
            "para a nuvem",
            "",
        ),
        (
            "esteira de propostas instável desde a migração para a nuvem: {svc} com erros",
            "esteira de propostas devolveu {n} erros; {svc} com {pct}% de falhas desde a migração",
            "",
        ),
    ),
    "H2": (
        (
            "registro de gravame recusado pelo órgão de trânsito",
            "registro de gravame recusado pelo órgão de trânsito em {svc}: {n} contratos parados",
            "{n} contratos com registro de gravame pendente há mais de {dias} dias",
        ),
        (
            "registro de gravame sem retorno do órgão de trânsito",
            "registro de gravame sem retorno em {svc} há {ms} ms; {n} contratos parados",
            "{n} contratos parados por registro de gravame sem retorno",
        ),
        (
            "registro de gravame refeito à mão por falha no envio",
            "falha ao enviar o registro de gravame em {svc}; {n} reenvios manuais",
            "{n} registros de gravame redigitados à mão no período",
        ),
    ),
    "H3": (
        (
            "boletos e carnês emitidos com valor errado",
            "emissao de boleto em {svc} com valor divergente do contrato ({n} documentos)",
            "{n} boletos e carnês com valor diferente do saldo do contrato",
        ),
        (
            "carnê com encargos calculados a mais",
            "calculo de encargos do carne em {svc} acima do devido ({n} parcelas)",
            "{n} carnês com encargos acima do devido",
        ),
        (
            "boleto reemitido com valor ainda errado",
            "reemissao de boleto em {svc} manteve o valor errado ({n} casos)",
            "{n} boletos reemitidos com o mesmo valor errado",
        ),
    ),
    # Cada sintoma traz a resposta do assistente e o efeito no atendimento: só "informou taxa
    # errada" lia como dado errado de um sistema qualquer, e o tema novo não aparecia como
    # encaixe fraco (#109).
    "H5": (
        (
            "assistente virtual do app respondeu ao cliente com taxa errada e a equipe de "
            "atendimento ficou sobrecarregada com as correções",
            "assistente virtual do app: {n} respostas com taxa errada; fila de correção no "
            "atendimento ({svc})",
            "",
        ),
        (
            "assistente virtual do app respondeu ao cliente com informação inventada e a equipe "
            "de atendimento ficou sobrecarregada com as reclamações",
            "assistente virtual do app: {n} respostas inventadas; fila de reclamações no "
            "atendimento ({svc})",
            "",
        ),
        (
            "assistente virtual do app deixou de responder e a equipe de atendimento ficou "
            "sobrecarregada com as conversas repassadas",
            "assistente virtual do app: {n} conversas ({pct}%) repassadas; fila no atendimento "
            "({svc})",
            "",
        ),
    ),
    "H6": (
        (
            "deploy manual falhou e precisou de nova tentativa",
            "deploy manual de {svc} interrompido na etapa {n}; refeito pelo time",
            "",
        ),
        (
            "testes instáveis bloquearam a entrega",
            "{n} testes instáveis reprovaram a entrega de {svc}; reexecução em {ms} ms",
            "",
        ),
        (
            "homologação compartilhada ocupada por outra entrega",
            "homologação compartilhada ocupada: {svc} aguardando há {ms} ms",
            "",
        ),
        (
            "rollback necessário depois de uma entrega",
            "rollback de {svc} executado após {n} erros na entrega",
            "",
        ),
    ),
    "H7": (
        (
            "dependências vulneráveis encontradas em {svc}",
            "varredura encontrou {n} dependências vulneráveis em {svc}",
            "",
        ),
        (
            "segredos em repositório detectados em {svc}",
            "varredura achou {n} segredos em repositório de {svc}",
            "",
        ),
        (
            "acesso de ex-colaborador ainda ativo em {svc}",
            "revisao de acessos: {n} contas de ex-colaborador ativas em {svc}",
            "",
        ),
        ("pentest vencido para {svc}", "pentest de {svc} vencido ha {dias} dias", ""),
    ),
}

TEMAS_POR_CHAVE = {t.chave: t for t in TEMAS}

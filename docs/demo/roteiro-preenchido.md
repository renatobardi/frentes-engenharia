Aviso da regra #481: sessão tratada como Haiku, sem revisão de Sonnet; a ferramenta `Agent` está indisponível.

# Roteiro preenchido: snapshot final da demo

O snapshot sustenta a abertura pela esteira, a oportunidade do portal e a coluna nova de IA. O ensaio com classificação nova permanece pendente.
As diferenças da tela estão registradas abaixo. Fontes: GETs deste documento, [PR #113][pr113] e [issue #114][i114].

## Estado conferido e limites do ensaio

Conferência em **05/10/2026**, com todas as origens, sem mudar a data entre versões.
O [GET `/healthz`][health] devolveu:

```json
{"commit":"3f681849ce3f249278ad8652ef75b59f1ca4cf00","versao_vigente":2,"dia_snapshot":"2026-10-05"}
```

O arquivo conferido é [`data/snapshot/eventos.sqlite.gz` em `3f68184`][snapshot]. A consulta Q1 encontra `snapshot_meta.commit_sha = 2ef79cb`.
Esse valor é o registro interno da gravação; o commit no ar é o informado por `/healthz`.
O carregador deslocou as datas em **−1 dia**, para o último dia dos eventos virar **04/10/2026**, ontem neste ensaio (Q1).
O `dia_snapshot` continua identificando o arquivo original, não o último dia após a carga.
Fonte: [carregador em `3f68184`][carregador] e Q1.

No servidor, todas as requisições desta sessão foram **GET**. Os envios ocorreram numa app local, com banco separado e sem chaves de modelos.
Não houve classificação nova, descoberta, revisão nem conferência contra serviço externo.
A conferência C1 lê respostas gravadas e gabarito local; [o comando não chama modelo][conferir-cli].
Os resultados de escrita são reproduzíveis pelo ensaio E1 abaixo.

Os links da aplicação usam endereço sem esquema. Use o esquema **`http`** na tailnet; o comando G1 explicita esse esquema.
Os links de escrita levam à tela, para leitura. **Não envie nada ao servidor durante esta conferência.**

## Os passos, com a tela que existe

As durações e a ordem vêm da [spec do roteiro][spec]. Os números da aplicação abaixo vêm dos GETs indicados.
Slide e página do pedido ficam fora da aplicação; nesses passos, o link serve como apoio, não como tela do slide.

| Passo | Minutos | Link e célula | O que o Bardi mostra e diz |
|---|---:|---|---|
| 0 | 1 | Slide de abertura. Apoio: [mapa na v2][dor]. Célula de abertura: **Plataforma e Sustentação × Disponibilidade e Performance**. | “Onde devo investir?” Apresentar os dados fictícios da Aurora Tech. O slide não foi produzido nesta entrega. |
| 1 | 2 | [Onde dói, v2, 90 dias][dor]. | Ler o Top 3: **Plataforma e Sustentação × Disponibilidade e Performance: 71, ↑31%**; **Canal Digital × Qualidade de IA e Atendimento: 42, ↑65%**; **Pós-venda e Cobrança × Integridade e Consistência de Dados: 22, ↓15%**, endereçada em **04/04**. Mostrar **“+4 incertas”** em Formalização × Integridade e Consistência de Dados. A H2 não está no Top 3. |
| 2 | 3 | [Painel da esteira, H1][h1]. Detalhe: [evento `ev-4689`, v2][fr-h1]. | Ler o porquê e a sugestão de fornecedor para arquitetura da esteira. Mostrar evolução, composição e os quatro problemas listados abaixo. Abrir o relato original de Nicolau Damasceno. O detalhe mostra **58%** de confiança na área e **100%** na frente. Dizer: “um modelo pequeno e barato, que diz o quanto tem certeza”; “o que ele não sabe, ele não pinta”. |
| 3 | 2 | [Onde há oportunidade][opo] e [painel do portal, H4][h4]. Apoio: [H6 em oportunidade][h6-opo] e [H6 em dor][h6-dor]. | Ler **Canal Parceiro × Processo Manual e Retrabalho: 21, ↑36%**. Mostrar a sugestão de automatizar comissões, status e simulações no portal. Plataforma e Sustentação × Processo Manual e Retrabalho tem **9,7, ↑42%** em oportunidade, mas **4,5, ↓29%** em dor. A frase “a mesma célula quente nas duas” precisa do aviso sobre H6 abaixo. |
| 4 | 2 | [Formulário de relato][relatar]. Célula histórica do texto preparado: [Canal Parceiro × Disponibilidade e Performance][relato-celula]. | Usar o texto preparado abaixo, sobre **tela inicial do lojista**, objeto listado. O envio local foi aceito, mas ficou aguardando classificação. O [detalhe gravado `ev-2343`][fr-relato] mostra **100%** na área e **99%** na frente. Essa resposta histórica não prova o resultado de um envio novo. O piscar da célula permanece não verificado neste ensaio. |
| 5 | 2 | [Mapa e painel da H1][h1]. | A rajada local aceitou **20 de 20** eventos. Sem chave, todas aguardaram classificação; o índice continuou **71** e a seta **↑31%**. O aumento observado foi **zero**, sem classificação. O [PR #113][pr113] registra **20 de 20** na célula da H1 num teste anterior do Jev, sem medir o salto na aplicação. |
| 6 | 3 | [Mapa na v1][v1] → [diff da revisão][diff] → [mapa na v2][dor]. Célula nova: **Canal Digital × Qualidade de IA e Atendimento**. | Na v1, mostrar **“Encaixe fraco 20% · limite 12%”**. No diff: **543** eventos na janela, **1 proposta, 1 aplicada, 0 descartadas**, com **16** evidências. Na v2, mostrar a coluna **Qualidade de IA e Atendimento**, marcada “nova”. As subfrentes são **Resposta de IA sem Fonte** e **Redirecionamento Excessivo para Atendente**. Mudar só a versão, mantendo **90 dias** e todas as origens. Não clicar em “Revisar a taxonomia agora”. |
| 7 | 2 | [H3, Onde dói, v2, 12 meses][h3]. Célula: **Pós-venda e Cobrança × Integridade e Consistência de Dados**. | Mostrar índice **137**, marcador **04/04/2026** e o mutirão de correção dos boletos e carnês. A tela informa **−35% desde 04/04, até 09/2026**. Dizer que o índice caiu depois da marca. A marca registra investimento; a curva não prova causalidade. Outubro é parcial. |
| 8 | 1 | [Top 1 e painel da H1][h1]. | “Endereçar com esta sugestão” abre um formulário; “Endereçar” confirma a decisão. Na cópia local, o selo **05/10** apareceu na célula e no Top 3. O índice permaneceu **71**, conforme a regra do endereçamento. Não repetir a escrita no servidor nesta sessão. |
| 9 | 2 | Página do pedido, fora da aplicação. Apoio: [oportunidade do portal][h4]. | Pedir um piloto com eventos reais de uma área, por tempo limitado. Mostrar as cinco linhas da spec. **8 semanas** são sugestão, sem medição; “poucos dólares” não é orçamento de produção. Usar o slide de reserva para explicar o custo histórico. |

### Os problemas que o painel mostra

| Célula e recorte | Problema, com o nome exato da tela | Eventos | Dias distintos | Fonte |
|---|---|---:|---:|---|
| H1, dor, 90 dias | balanceador-de-carga | 28 | 22 | [GET H1][h1] |
| H1, dor, 90 dias | Gerenciador de segredos de plataforma | 24 | 20 | [GET H1][h1] |
| H1, dor, 90 dias | Provisionador-de-ambientes | 22 | 16 | [GET H1][h1] |
| H1, dor, 90 dias | Esteira de propostas | 14 | 14 | [GET H1][h1] |
| H2, dor, 90 dias | Registro de gravame | 14 | 12 | [GET H2][h2] |
| H4, oportunidade, 90 dias | Portal do lojista | 42 | 32 | [GET H4][h4] |
| H4, oportunidade, 90 dias | Vitrine-de-tabelas-comerciais | 1 | 1 | [GET H4][h4] |
| H3, dor, 12 meses | Calculo-de-encargos | 162 | 128 | [GET H3][h3] |
| H3, dor, 12 meses | Esteira de propostas | 2 | 2 | [GET H3][h3] |

Os problemas não esgotam a célula. A H1 tem **115** eventos no recorte; a H4 lista **54**, incluindo **1 incerta** (GETs H1 e H4; Q2).
O selo de recorrência considera os dias do problema em todo o filtro, incluindo outras células e a outra visão.
Por isso, a tela marca como recorrentes também os itens com poucos dias nessa célula. Fonte: [cálculo da recorrência][recorrencia].

### Frentes e problemas do snapshot

A v1 tem **6 frentes**, **26 subfrentes** e **7 problemas**. A v2 tem **7 frentes**, **28 subfrentes** e **9 problemas** (Q3).
Na ordem das colunas, as frentes são:

1. Disponibilidade e Performance.
2. Integridade e Consistência de Dados.
3. Processo Manual e Retrabalho.
4. Segurança e Conformidade.
5. Capacidade e Recursos.
6. Governança e Comunicação.
7. Qualidade de IA e Atendimento, acrescentado na v2.

Fonte: [GET Taxonomia][diff] e Q3. A operação gravada da revisão é **criar frente** (Q4).
Os problemas da v1 são **Esteira de propostas**, **Registro de gravame**, **Gerenciador de segredos de plataforma**, **Portal do lojista**,
**Provisionador-de-ambientes**, **Calculo-de-encargos** e **Vitrine-de-tabelas-comerciais**.
A v2 acrescenta **assistente virtual do app** e **balanceador-de-carga** (Q3).

## Relato preparado e resultado local

Emissor: **Davi Damasceno**. Copiar sem mudar o texto:

> A build da tela inicial do lojista está demorando mais de meia hora, o que atrasa todo o ciclo de deploy.

Fonte: [GET `/eventos/ev-2343?versao=2`][fr-relato] e Q5.
O objeto **tela inicial do lojista** está listado na ficha do time **Portal do Lojista**, da área **Canal Parceiro**.
Fonte: [`seed/organograma.json:489@3f68184`][organograma] e Q5, que confere também o documento da taxonomia.
A célula histórica é **Canal Parceiro × Disponibilidade e Performance**, visão **Onde dói**. É diferente da célula da H1.
O snapshot registra confiança de **100%** na área, **99%** na frente e **100%** na natureza reativo (Q5 e GET do detalhe).

Na app local, `POST /eventos/relatar` respondeu **303**, com destino `/eventos/relatar/<id-novo>`.
O GET do destino mostrou: **“Recebida. O evento está aguardando classificação.”**
O motivo foi **“Jev: SemChave: TYPESAFE_API_KEY não está no ambiente”**.
A consulta do envio encontrou **zero classificações**. Não existe célula nem confiança nova para registrar (E1).
O texto está preparado e sua resposta histórica foi conferida. A classificação de um novo envio permanece pendente.

## Rajada: o que foi medido e o que falta

O arquivo [`seed/gerado/rajada.jsonl`][rajada] contém **20** eventos sobre a esteira, citando **balanceador-de-carga** (Q6).
O [PR #113][pr113] registra o resultado anterior no Jev: **20 de 20** na célula **Plataforma e Sustentação × Disponibilidade e Performance**.
Esse registro não informa a soma das severidades nem a variação da seta após o envio à aplicação.

O comando `python -m eventos rajada`, apontado somente à cópia local sem chaves, informou **“20 de 20 eventos aceitos”**.
Depois do relato e da rajada, o banco tinha **21** novos eventos aguardando e **zero** classificações novas (E1).
O índice bruto da H1 permaneceu **71,1466666667**; a tela continuou **71, ↑31%** (Q2 e E1).
O salto observado foi **0**, porque os eventos não foram classificadas. O salto com Jev real é **não medido nesta sessão**.
Não usar “mais 20” como aumento do índice: o índice soma severidade, não a quantidade de eventos ([definição do mapa][mapa-codigo]).

## Números para os slides de reserva

### Custo e velocidade

Os valores abaixo são do uso já gravado da seed inteira. Não representam custo de um piloto com dados reais.

| Medida | v1 | v2 | Fonte e comando |
|---|---:|---:|---|
| Eventos com classificação | 6.000 | 6.000 | Q7; C1 |
| Tokens de entrada do Jev | 40.163.438 | 42.227.438 | Q7; C1 |
| Tokens de saída do Jev | 6.316.414 | 6.665.878 | Q7; C1 |
| Custo do Jev, entrada × US$ 0,042 por milhão | US$ 1,69 | US$ 1,77 | Q7; [preço usado pela conferência][preco] |
| Tokens da LLM no desempate, entrada / saída | 279.968 / 11.546 | 258.760 / 10.651 | Q7; C1 |
| Soma das latências do Jev | 111,1 min | 86,0 min | Q7; C1 |
| Intervalo entre primeira e última classificação gravada | 30 min 29 s | 6 min 44 s | Q7 |

A soma das latências acumula chamadas concorrentes. O intervalo entre datas inclui etapas reaproveitadas e pausas; não mede velocidade contínua.
O [PR #113][pr113] registra **194 s** para as **4.411** eventos restantes da v1 e **114 s** para a classificação da v2.
Comando da fonte histórica: `gh pr view 113 --json body --jq .body`.
No exemplo preparado, o detalhe gravou **855 ms**, com **6.996 + 1.108 tokens** ([GET `ev-2343`][fr-relato]).
Latência de uma classificação nova nesta sessão: **não medida**, pois o envio ficou aguardando.

O Jev das duas versões soma **US$ 3,46** (Q7). O custo monetário do desempate da LLM não é calculado pela conferência.
O total histórico da calibração, incluindo tentativas e etapas fora da classificação, foi **US$ 5,11 pela conta de tokens**.
O autor também registra **US$ 4,69** usando o consumo da chave para a parcela da LLM. São contas diferentes, não dois totais do snapshot.
Fonte e comando: [corpo do PR #113][pr113], `gh pr view 113 --json body --jq .body`.

### Acerto contra o gabarito

A conferência **offline** da v2 encontrou **21 cortes aprovados**, **8 reprovados**, **25 só reportados** e **0 sem valor** (C1).
O comando saiu com código **1** pelos cortes reprovados. Não confundir essa saída com os gates de teste e lint.

| Medida para o slide | Resultado na v2 | Fonte |
|---|---|---|
| H1 numa mesma frente | 100%, 240 de 240 | C1 |
| H1 em dor | 1º de 51 células, 7,9× a mediana | C1 |
| H4 em oportunidade | 1º de 49 células, 7,4× a mediana | C1 |
| H5 na frente nova | 78,8%, 141 de 179; corte de 80% reprovado | C1 |
| Histórias H1–H5 com problema na lista | 5 de 5 | C1 |
| Cobertura dos problemas em H1–H5 | 76,1%, 685 de 900 | C1 |
| Área certa do fundo com objeto listado | 98,7%, 3.509 de 3.554 | C1 |
| Área certa do relato cruzado com objeto listado | 94,9%, 203 de 214 | C1 |
| Natureza igual ao gabarito | 89,3%, 5.144 de 5.758 | C1 |

C1 termina suas janelas em **04/10/2026**, último dia classificado. Os GETs do mapa usam **05/10/2026**, hoje neste ensaio.
Por isso, os múltiplos e posições de C1 não devem ser apresentados como números impressos na tela de hoje.
Fontes: [referência da conferência][conferencia-codigo], [referência do mapa][mapa-codigo] e Q1.

Os cortes reprovados foram: H2 numa mesma frente; H4 numa área aceita; H5 na frente nova; H6 numa área aceita;
intensidade da H2 em dor; intensidade da H5 em oportunidade; intensidade da H6 em dor; problema com maioria do fundo (C1).
O slide não deve reduzir esse resultado a um único “percentual de acerto”. Recomendação do autor, baseada nas medidas distintas de C1.

## Avisos ao Bardi: diferenças e pontos estranhos

| O que a tela mostra | O que diverge ou pede cuidado | Fonte |
|---|---|---|
| O Top 3 de dor é esteira, IA e boletos. | A leitura da H2 como parte do Top 3 não cabe. Sua célula é Formalização × Processo Manual e Retrabalho, com **12, ↑12%**. C1 mede apenas **37,8%** numa mesma frente e **1,2×** a mediana, em **16º de 51**. | [GET dor][dor], [GET H2][h2], C1; [#114][i114] |
| A H1 lista quatro problemas; Esteira de propostas vem por último. | A história não vira um único problema na tela. A infra ocupa as primeiras posições. O painel mostra **14** eventos de Esteira; a #114 registra **15**. A janela do mapa termina hoje; C1 usa ontem. | [GET H1][h1], [#114][i114], Q1 e Q2 |
| O cabeçalho da H1 mostra **71**, bruto **71,1467**. Seu porquê cita índice **73.26** e **58** eventos de capacidade insuficiente. | O texto gravado e os agregados divergem: a composição atual mostra **55** eventos dessa causa. O carregamento desloca datas; não reescreve o texto do painel. Não ler os números do porquê como valores atuais. | [GET H1][h1], Q2; [carregador][carregador] |
| O selo da v1 imprime **20%**, com limite **12%**. | O sinal gravado é **20,44198895%**, ou **20,4%**, em **543** eventos. O arredondamento esconde a casa decimal. O gatilho registrado é **botão**, não uma revisão automática pelo sinal. | [GET v1][v1], [GET diff][diff], Q4 |
| O limite permanece **12%**. | O PR #113 mede disparo em **145 de 152** janelas dos meses iniciais. A sugestão de **19%** depende da decisão registrada como pendente na #114. Este roteiro não troca o limite. | [PR #113][pr113], [#114][i114], Q4 |
| A v2 criou Qualidade de IA e Atendimento. | “Ganhou coluna própria” está sustentado. O corte de **80%** da H5 não passou: **78,8%**. A coluna existir não significa que toda H5 esteja nela. | [GET diff][diff], C1 |
| H6 aparece em frentes diferentes entre as visões. | C1 coloca a H6 reativo na célula da H1. A proativo está em Plataforma e Sustentação × Processo Manual e Retrabalho. Nessa última, dor tem **4,5, ↓29%** e oportunidade **9,7, ↑42%**. A frase “mesma célula quente nas duas” não representa a concentração da H6. | [GET H6 dor][h6-dor], [GET H6 oportunidade][h6-opo], C1 |
| Os nomes misturam redação natural, hífens, maiúsculas e falta de acento. | Exemplos: **Esteira de propostas**, **Provisionador-de-ambientes**, **Calculo-de-encargos**, **balanceador-de-carga**, **assistente virtual do app**. Preservar esses nomes no ensaio; a padronização está na #114. | Q3; [#114][i114] |
| H4 mostra “recorrente” junto de **1 eventos em 1 dias**; H3 mostra Esteira em **2 dias**. | O selo usa o problema no filtro inteiro; o contador usa a célula. O plural e a diferença de escopo ficam estranhos sem explicação. Não é prova de recorrência dentro daquela célula. | [GET H4][h4], [GET H3][h3], [cálculo da recorrência][recorrencia] |
| O porquê da H4 diz “42 eventos nos últimos 32 dias”. | O bloco calculado diz **42 eventos em 32 dias distintos**, dentro de **90 dias**. A frase do painel confunde dias distintos com tamanho da janela. | [GET H4][h4] |
| O gráfico da H3 termina em outubro com **0,7**. | Outubro é parcial. A queda declarada usa o último mês fechado: **−35% até setembro**, e não o ponto parcial final. | [GET H3][h3]; [cálculo da variação][variacao] |
| “Endereçar com esta sugestão” abre a decisão editável. | O selo só aparece depois de confirmar em “Endereçar”. O clique inicial não grava a marca. | [GET H1][h1]; E1 |

## O que o Bardi faz no ensaio

Lista derivada da [spec do roteiro][spec]. Os itens abaixo permanecem **não verificados nesta sessão**, salvo a escrita local descrita em E1.

- Repetir o relato preparado num desenvolvimento autorizado a chamar Jev; registrar célula e confiança novas.
- Rodar a rajada nesse desenvolvimento; registrar índice bruto, número exibido e seta antes e depois.
- Repetir relato e rajada no oute-server somente num ensaio posterior autorizado. Este é o critério **(ship)** da #66.
- Gravar o vídeo de reserva dos passos 4 e 5, usando o mesmo snapshot.
- Construir a imagem no Mac e conferir que a cópia local sobe do snapshot, sem rede.
- Conferir a leitura dos números e o salto da rajada a três metros.
- Conferir o serviço externo antes da reunião, conforme a spec; isso não foi feito nesta sessão.
- Recarregar o snapshot como último passo antes da reunião, num procedimento autorizado. A recarga desfaz as escritas do ensaio.
- Abrir o mapa uma vez com `?guia=0` no navegador e no endereço da demo, antes da reunião: isso desliga o passeio guiado ([#139][i139]) naquele navegador. Sem isso, o passeio abre sozinho sobre o mapa na primeira tela. Conferido só numa app local, não no oute-server.
- Preparar o slide de abertura, os slides de reserva e a página das cinco linhas do pedido; são entregas do Bardi.

## Fontes reproduzíveis

### G1 — GETs no servidor

Na raiz do repo, definir a base sem enviar credenciais:

```bash
DEMO_URL="$(printf '%s://%s' http 100.66.254.24:3790)"
curl --fail --silent --show-error "$DEMO_URL/healthz"
curl --fail --silent --show-error "$DEMO_URL/?visao=dor&periodo=90d&versao=2"
curl --fail --silent --show-error "$DEMO_URL/?visao=oportunidade&periodo=90d&versao=2"
curl --fail --silent --show-error "$DEMO_URL/?visao=dor&periodo=90d&versao=2&area=plataforma-e-sustentacao&frente=disponibilidade-e-performance"
curl --fail --silent --show-error "$DEMO_URL/?visao=dor&periodo=90d&versao=2&area=formalizacao&frente=processo-manual-e-retrabalho"
curl --fail --silent --show-error "$DEMO_URL/?visao=oportunidade&periodo=90d&versao=2&area=canal-parceiro&frente=processo-manual-e-retrabalho"
curl --fail --silent --show-error "$DEMO_URL/?visao=dor&periodo=12m&versao=2&area=pos-venda-e-cobranca&frente=integridade-e-consistencia-de-dados"
curl --fail --silent --show-error "$DEMO_URL/?visao=dor&periodo=90d&versao=1"
curl --fail --silent --show-error "$DEMO_URL/taxonomia?geracao=2&versao=2"
```

Os demais links do roteiro também foram abertos por GET. Os valores da tabela são os textos do HTML retornado.
Legibilidade no projetor, animação e atualização por polling não foram medidas.

### Q1–Q7 e C1 — cópia local, data fixada, sem chamadas externas

Este comando carrega o arquivo do repo em um diretório temporário. Não usa o banco do servidor nem altera o snapshot.
Ele recusa conexões de saída e usa configuração sem credenciais. C1 sai com código **1**, pelos cortes descritos acima.

```bash
uv run python - <<'PY'
import json
import socket
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from eventos import config, store
from eventos.conferencia import arquivo as gabarito
from eventos.conferencia.conferir import conferir
from eventos.contratos import Periodo, Visao
from eventos.mapa import agregados
from eventos.snapshot import arquivo
from eventos.store.conferencia import uso_por_versao

def sem_rede(*args, **kwargs):
    raise RuntimeError("Esta conferência não permite rede")

socket.socket.connect = sem_rede
socket.socket.connect_ex = sem_rede
socket.create_connection = sem_rede

with TemporaryDirectory() as pasta:
    banco = Path(pasta) / "eventos.sqlite"
    arquivo.carregar(banco, agora=datetime(2026, 10, 5, 12, tzinfo=UTC))
    con = store.abrir_existente(banco)
    cfg = config.carregar({})
    print("Q1", dict(con.execute(
        "SELECT dia_d,commit_sha,deslocamento_dias FROM snapshot_meta"
    ).fetchone()))
    print("Q1 último dia", con.execute(
        "SELECT MAX(substr(coalesce(ocorrido_em,recebido_em),1,10)) FROM evento"
    ).fetchone()[0])
    for versao in (1, 2):
        for visao in (Visao.DOR, Visao.OPORTUNIDADE):
            mapa = agregados.ler(con, versao=versao, visao=visao,
                periodo=Periodo.D90, referencia=date(2026, 10, 5))
            print("Q2", versao, visao.value, [asdict(c) for c in mapa.top3])
        valores = [dict(r) for r in con.execute(
            "SELECT dimensao,chave,nome,chave_pai FROM valor "
            "WHERE versao=? AND dimensao IN ('frente','problema') ORDER BY ordem,chave",
            (versao,))]
        print("Q3", versao, valores)
        print("Q3 contagens", {
            "frentes": sum(v["dimensao"] == "frente" and v["chave_pai"] is None for v in valores),
            "subfrentes": sum(v["dimensao"] == "frente" and v["chave_pai"] is not None for v in valores),
            "problemas": sum(v["dimensao"] == "problema" for v in valores)})
    print("Q4", [dict(r) for r in con.execute(
        "SELECT id,gatilho,sinal,operacoes FROM geracao WHERE frente='revisao'")])
    print("Q4 limite", cfg.limiares.sinal_de_encaixe.encaixe_fraco)
    print("Q5", dict(con.execute(
        "SELECT f.texto,f.emissor,c.area_final,c.frente_final,c.time_final,"
        "c.conf_area,c.conf_frente,c.conf_natureza,c.natureza_final "
        "FROM evento f JOIN classificacao c ON c.evento_id=f.id "
        "WHERE f.id='ev-2343' AND c.versao=2").fetchone()))
    documento = json.loads(con.execute(
        "SELECT documento FROM versao_taxonomia WHERE numero=2").fetchone()[0])
    print("Q5 ficha", [t for a in documento["organograma"] for t in a["times"]
        if t["chave"] == "portal-do-lojista"])
    rajada = [json.loads(l) for l in Path("seed/gerado/rajada.jsonl").read_text().splitlines() if l]
    print("Q6", len(rajada), all("balanceador-de-carga" in r["texto"] for r in rajada))
    custo = 0.0
    for uso in uso_por_versao(con):
        usd = uso.jev_entrada / 1_000_000 * 0.042
        custo += usd
        intervalo = datetime.fromisoformat(uso.ultima) - datetime.fromisoformat(uso.primeira)
        print("Q7", asdict(uso), "US$", round(usd, 2), "intervalo", intervalo)
    print("Q7 soma Jev US$", round(custo, 2))
    relatorio = conferir(con, gabarito.ler(gabarito.ARQUIVO_PADRAO), 2, cfg.limiares)
    print("C1", relatorio.texto())
    con.close()
    raise SystemExit(relatorio.codigo_de_saida)
PY
```

### E1 — repetir a escrita apenas numa app local sem chaves

O ensaio desta sessão subiu `python -m eventos servir` com `env -i`, banco separado e endereço de loopback.
O relato respondeu **303**; a rajada aceitou **20 de 20**; o endereçamento respondeu **303**.
O GET após confirmar mostrou **“◆ endereçada em 05/10”**, no Top 3 e na célula da H1.
O comando abaixo reproduz as mesmas rotas numa app local pelo `TestClient`, com outro banco e sem credenciais reais.
As datas do selo acompanham o dia em que o comando roda. Nenhuma resposta de modelo é injetada.

```bash
uv run python - <<'PY'
import json
import socket
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from eventos import config, store
from eventos.contratos import Visao
from eventos.mapa import agregados
from eventos.snapshot import arquivo
from eventos.web.app import criar_app

def sem_rede(*args, **kwargs):
    raise RuntimeError("Este ensaio não permite conexões externas")

socket.socket.connect = sem_rede
socket.socket.connect_ex = sem_rede
socket.create_connection = sem_rede

with TemporaryDirectory() as pasta:
    banco = Path(pasta) / "eventos.sqlite"
    cfg = config.carregar({"EVENTOS_DB": str(banco)})
    arquivo.carregar(banco)
    con = store.abrir_existente(banco)
    texto, emissor = con.execute("SELECT texto,emissor FROM evento WHERE id='ev-2343'").fetchone()
    def indice():
        return next(c.indice for c in agregados.ler(con, visao=Visao.DOR).celulas
            if c.area == "plataforma-e-sustentacao" and c.frente == "disponibilidade-e-performance")
    antes = indice()
    app = criar_app(cfg)
    with TestClient(app, follow_redirects=False) as client:
        resposta = client.post("/eventos/relatar", data={"texto": texto, "emissor": emissor})
        destino = resposta.headers["location"]
        print("E1 relato", resposta.status_code, destino)
        # Espera só as tarefas da fila local, que recusam a falta de chave.
        client.portal.call(app.state.fila.varrer)
        print("E1 gaveta", client.get(destino).text)
        # O webhook exige token: usar um valor temporário apenas nesta app local.
        from dataclasses import replace
        app.state.config = replace(cfg, webhook_token="ensaio-local")
        registros = [json.loads(l) for l in Path("seed/gerado/rajada.jsonl").read_text().splitlines() if l]
        from datetime import UTC, datetime
        from eventos.seed.rajada import corpo
        aceitas = 0
        for r in registros:
            resposta = client.post("/eventos", content=corpo(r, datetime.now(UTC), "ensaio66"),
                headers={"Authorization": "Bearer ensaio-local", "Content-Type": "application/json"})
            aceitas += resposta.status_code == 202
        client.portal.call(app.state.fila.varrer)
        print("E1 rajada", aceitas, "de", len(registros), "aceitas")
        print("E1 índice", antes, indice(), "salto", indice() - antes)
        print("E1 novas", [dict(r) for r in con.execute(
            "SELECT origem,COUNT(*) AS n FROM evento WHERE id NOT LIKE 'fr-%' GROUP BY origem")])
        print("E1 classificações novas", con.execute(
            "SELECT COUNT(*) FROM classificacao WHERE evento_id NOT LIKE 'fr-%'").fetchone()[0])
        resposta = client.post("/mapa/enderecar", data={
            "area": "plataforma-e-sustentacao", "frente": "disponibilidade-e-performance",
            "visao": "dor", "periodo": "90d", "versao": "2", "n": "0",
            "tipo_solucao": "fornecedor", "texto": "Ensaio local da decisão", "quem_decidiu": "Ensaio #66"})
        print("E1 endereçar", resposta.status_code)
        print("E1 selo", "◆ endereçada em" in client.get(resposta.headers["location"]).text)
    con.close()
PY
```

[spec]: ../spec/11-demo-e-roteiro.md
[pr113]: https://github.com/renatobardi/frentes-engenharia/pull/113
[i114]: https://github.com/renatobardi/frentes-engenharia/issues/114
[i139]: https://github.com/renatobardi/frentes-engenharia/issues/139
[snapshot]: https://github.com/renatobardi/frentes-engenharia/blob/3f68184/data/snapshot/eventos.sqlite.gz
[carregador]: https://github.com/renatobardi/frentes-engenharia/blob/3f68184/eventos/snapshot/arquivo.py#L127
[conferir-cli]: https://github.com/renatobardi/frentes-engenharia/blob/3f68184/eventos/conferencia/cli.py
[conferencia-codigo]: https://github.com/renatobardi/frentes-engenharia/blob/3f68184/eventos/conferencia/conferir.py#L22
[mapa-codigo]: https://github.com/renatobardi/frentes-engenharia/blob/3f68184/eventos/mapa/agregados.py#L97
[recorrencia]: https://github.com/renatobardi/frentes-engenharia/blob/3f68184/eventos/mapa/celula.py#L95
[variacao]: https://github.com/renatobardi/frentes-engenharia/blob/3f68184/eventos/web/mapa/painel.py#L186
[organograma]: https://github.com/renatobardi/frentes-engenharia/blob/3f68184/seed/organograma.json#L489
[rajada]: https://github.com/renatobardi/frentes-engenharia/blob/3f68184/seed/gerado/rajada.jsonl
[preco]: https://github.com/renatobardi/frentes-engenharia/blob/3f68184/eventos/conferencia/cortes.py#L27
[health]: //100.66.254.24:3790/healthz
[dor]: //100.66.254.24:3790/?visao=dor&periodo=90d&versao=2
[opo]: //100.66.254.24:3790/?visao=oportunidade&periodo=90d&versao=2
[v1]: //100.66.254.24:3790/?visao=dor&periodo=90d&versao=1
[diff]: //100.66.254.24:3790/taxonomia?geracao=2&versao=2
[h1]: //100.66.254.24:3790/?visao=dor&periodo=90d&versao=2&area=plataforma-e-sustentacao&frente=disponibilidade-e-performance
[h2]: //100.66.254.24:3790/?visao=dor&periodo=90d&versao=2&area=formalizacao&frente=processo-manual-e-retrabalho
[h3]: //100.66.254.24:3790/?visao=dor&periodo=12m&versao=2&area=pos-venda-e-cobranca&frente=integridade-e-consistencia-de-dados
[h4]: //100.66.254.24:3790/?visao=oportunidade&periodo=90d&versao=2&area=canal-parceiro&frente=processo-manual-e-retrabalho
[h6-dor]: //100.66.254.24:3790/?visao=dor&periodo=90d&versao=2&area=plataforma-e-sustentacao&frente=processo-manual-e-retrabalho
[h6-opo]: //100.66.254.24:3790/?visao=oportunidade&periodo=90d&versao=2&area=plataforma-e-sustentacao&frente=processo-manual-e-retrabalho
[relatar]: //100.66.254.24:3790/eventos/relatar
[relato-celula]: //100.66.254.24:3790/?visao=dor&periodo=90d&versao=2&area=canal-parceiro&frente=disponibilidade-e-performance
[fr-relato]: //100.66.254.24:3790/eventos/ev-2343?versao=2
[fr-h1]: //100.66.254.24:3790/eventos/ev-4689?versao=2

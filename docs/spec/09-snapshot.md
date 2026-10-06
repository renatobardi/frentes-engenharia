# 09 · Snapshot

O estado gravado de que a demo sobe.

## O que é

- O estado inteiro gravado depois de: **carga da seed → descoberta da v1 → classificação → revisão → v2 → painéis**. [R20]
- A classificação é gravada uma vez; a demo não reclassifica o histórico. [R5] [R7]

## O que contém

- Eventos, emissores, v1 e v2 com seus valores, as classificações da seed inteira **nas duas versões**, a descoberta e a revisão gravadas (`geracao`), os painéis das duas versões, os endereçamentos da seed e o `snapshot_meta`. [R19] [R20]
- **Fora**: `rajada.jsonl` (enviada ao vivo) e o **gabarito** (a conferência usa um banco à parte, que não vai para o servidor). [R20] [R23]
- `snapshot_meta` (linha única): dia D, data da geração, commit, cópia da configuração de limiares usada. [R20] [R23]
- O antes e depois da revisão é ler o mapa na v1 e na v2. Nada é chamado ao vivo. [R9] [R20]

## Formato

- **O arquivo SQLite, compactado, versionado no repo**: `data/snapshot/eventos.sqlite.gz`. O deploy é um `git checkout` e o snapshot vem junto. [R23]
- **Tamanho não medido.** Se passar de **50 MB** compactado, muda para anexo de release. O snapshot é regravado poucas vezes e de propósito. [R23]
- Sem migrações: mudou o esquema, regrava-se o snapshot. [R23]

## Carga e deslocamento de datas

- O snapshot guarda datas absolutas que terminam no dia D. O carregador restaura e desloca **todas** as colunas de data, e os timestamps em `metadados`, para D virar **ontem**: as do evento, `criada_em` e `ativada_em` das versões, `disparada_em`, `classificada_em`, `gerado_em` e a data do endereçamento. [R7] [R19] [R20]
- **O container sobe e, se não há banco no volume, carrega o snapshot sozinho.** Subir do zero já dá a demo pronta. [R23]
- Comandos: `python -m eventos snapshot gravar` e `python -m eventos snapshot carregar`. [R23]
- Rota `POST /admin/snapshot/carregar`, protegida pelo mesmo token de demo, para recarregar com um `curl`. A troca do arquivo é atômica (carrega num arquivo ao lado e renomeia). [R23]
- Recarregar desfaz o que foi feito na tela: eventos ao vivo e endereçamentos marcados. [R19] [R21]
- Recarregar é um comando só e rápido; é o último passo antes de entrar na sala. [R21]

## `GET /healthz`

Devolve o commit, a versão vigente e o dia do snapshot. É o que o deploy confere. [R23]

## Custo de produzir

Duas classificações da seed inteira no Jev (v1 e v2), entre ~US$1,45 e ~US$2,20 cada [R11]; descoberta ~US$0,06, revisão menos de US$0,01 [R9]; painéis ~US$0,01 [R6].

## Contradições anotadas

- [R20] deixou o formato do arquivo e o lugar da configuração de limiares para [R23], que os fixou (SQLite compactado no repo; `config/limiares.toml`).
- [R20] avisa que o "antes" mostra na v1 também os eventos dos meses depois da revisão (a seed inteira é classificada nas duas versões). É a regra; a alternativa (v1 só até a data da revisão) não foi adotada.

[R2]: https://github.com/renatobardi/frentes-engenharia/issues/2#issuecomment-5963209961 "Métrica de onde investir e eixos do mapa de calor"
[R3]: https://github.com/renatobardi/frentes-engenharia/issues/3#issuecomment-5963699217 "Taxonomia das frentes"
[R3a]: https://github.com/renatobardi/frentes-engenharia/issues/3#issuecomment-5963730296 "Taxonomia das frentes: adendo das facetas secundárias"
[R4]: https://github.com/renatobardi/frentes-engenharia/issues/4#issuecomment-5963257760 "Fontes de entrada do PoC"
[R5]: https://github.com/renatobardi/frentes-engenharia/issues/5#issuecomment-5963392669 "Chamar o Jev pelo OpenRouter com saída tipada e confiança"
[R6]: https://github.com/renatobardi/frentes-engenharia/issues/6#issuecomment-5963886450 "Divisão de trabalho Jev × LLM"
[R7]: https://github.com/renatobardi/frentes-engenharia/issues/7#issuecomment-5968605004 "Seed monstra de frentes fictícias"
[R8]: https://github.com/renatobardi/frentes-engenharia/issues/8#issuecomment-5973534977 "Detecção de recorrência entre frentes"
[R9]: https://github.com/renatobardi/frentes-engenharia/issues/9#issuecomment-5974240632 "Descoberta e revisão da taxonomia pela LLM"
[R11]: https://github.com/renatobardi/frentes-engenharia/issues/11#issuecomment-5975418258 "Problema como dimensão: lista e atribuição contra o gabarito"
[R13]: https://github.com/renatobardi/frentes-engenharia/issues/13#issuecomment-5975046164 "Fundo da seed: área no texto e serviços nos logs"
[R14]: https://github.com/renatobardi/frentes-engenharia/issues/14#issuecomment-5974728715 "Pergunta de controle texto vago: corte e redação"
[R19]: https://github.com/renatobardi/frentes-engenharia/issues/19#issuecomment-5975483920 "Ciclo de vida da frente depois de classificada"
[R20]: https://github.com/renatobardi/frentes-engenharia/issues/20#issuecomment-5975493388 "Modelo de dados do PoC"
[R21]: https://github.com/renatobardi/frentes-engenharia/issues/21#issuecomment-5975529180 "Roteiro da demo para o diretor"
[R22]: https://github.com/renatobardi/frentes-engenharia/issues/22#issuecomment-5975630924 "Telas do PoC além do mapa de calor"
[R23]: https://github.com/renatobardi/frentes-engenharia/issues/23#issuecomment-5975570909 "Stack e onde o PoC roda"
[R24]: https://github.com/renatobardi/frentes-engenharia/issues/24#issuecomment-5975617171 "Área quando quem relata não é o dono do objeto"

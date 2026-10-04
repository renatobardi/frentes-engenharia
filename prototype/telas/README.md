# PROTÓTIPO DESCARTÁVEL — telas do PoC além do mapa de calor (#22)

Não é código de produção. Vive só no branch `prototype/22-telas`, sem PR e sem merge.
Responde ao ticket [Telas do PoC além do mapa de calor](https://github.com/renatobardi/frentes-engenharia/issues/22).

**Pergunta.** Quais são as telas do PoC além do mapa de calor, como cada uma se parece e como se navega entre elas?

**Plano.** Três variantes de navegação sobre as mesmas telas, trocadas por `?variant=A|B|C` e pela barra preta no pé da página
(setas do teclado também trocam). A barra também percorre os passos 1 a 8 do roteiro da demo (#21).

| Variante | Navegação mapa → célula → frente |
|---|---|
| **A — Mapa fixo + painel ao lado** | o mapa nunca sai da tela; o painel da célula abre à direita; a frente e o formulário de relato abrem em gaveta |
| **B — Páginas com trilha** | mapa, célula e frente são páginas inteiras, com trilha de volta; o relato é uma página |
| **C — Painel embaixo do mapa** | o mapa fica inteiro em cima; o painel da célula abre embaixo, em três colunas; a frente e o relato abrem em janela |

## Abrir

`telas.html` é um arquivo único (dados e código dentro). Baixe e abra com dois cliques, sem servidor:

```bash
git fetch origin prototype/22-telas
git show origin/prototype/22-telas:prototype/telas/telas.html > ~/Downloads/telas-22.html && open ~/Downloads/telas-22.html
```

Ou, com o branch em disco: `python3 -m http.server 8022 --directory prototype/telas` e abrir `http://localhost:8022/?variant=A`.

## Arquivos

| arquivo | o quê |
|---|---|
| `montar.py` | lê a amostra dos branches `prototype/9-descoberta`, `prototype/14-texto-vago` e `prototype/7-seed` por `git show`, grava `dados.js` e `telas.html`. Sem rede e sem modelo |
| `index.html`, `app.css`, `app.js` | as telas e as três cascas |
| `dados.js`, `telas.html` | gerados por `python3 prototype/telas/montar.py` |

## O que é dado de verdade e o que é dublê

- **De verdade (gravado nos outros protótipos):** 240 frentes com a resposta do Jev na v1 e na v2 (confiança, top 3, desempate da LLM),
  27 frentes de texto vago com a resposta da pergunta de controle, a revisão v1 → v2 com a frase da LLM e as operações, a rajada da seed.
- **Peso.** A amostra não é proporcional (50 frentes dos meses 1–6, 160 dos meses 7–12, 30 de reforço do tema novo). Cada frente leva um
  peso (60, 19 ou 4,5) para o índice ficar na ordem de grandeza da seed inteira (~6 mil frentes). Frente que entra ao vivo vale 1.
  Os números das células **não são** os do snapshot final, e o Top 3 da amostra não é o do roteiro.
- **Dublê:** a classificação do relato e da rajada ao vivo (regra de palavra-chave em `classificaDuble`, sem Jev); os textos do
  painel da célula (escritos à mão para 8 células, montados dos dados nas outras); as datas do histórico de versões.
- **Sem persistência:** recarregar a página desfaz relatos, rajada e endereçamentos feitos na tela. O botão "Zerar" faz o mesmo.

## Como foi conferido

Sem navegador no container da sessão: o protótipo foi exercitado em jsdom (as três variantes, os passos do roteiro, relato, relato vago,
rajada, endereçar, lista e filtros), sem erro de script. **O layout não foi visto renderizado**; ajuste de espaçamento e quebra de
texto pode ser necessário ao abrir.

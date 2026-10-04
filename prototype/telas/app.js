// PROTÓTIPO DESCARTÁVEL (#22) — telas do PoC além do mapa de calor.
// Três variantes de navegação (?variant=A|B|C) sobre as mesmas telas. Estado só em memória.
// Nada aqui chama o Jev nem a LLM: a classificação ao vivo é um dublê (ver classificaDuble).
(function () {
  'use strict';
  const D = window.DADOS;
  const DIA = 86400000;
  const CFG = { limiar: 0.5, causa: 0.3, problema: 0.5, vago: 0.5, fraco: 0.7, recorrencia: 3, urgente: 0.7, sinal: 12 };
  const VARIANTES = { A: 'Mapa fixo + painel ao lado', B: 'Páginas com trilha', C: 'Painel embaixo do mapa' };
  const VISOES = { dor: 'Onde dói', op: 'Onde há oportunidade' };
  const PERIODOS = { 30: '30 dias', 90: '90 dias', 180: '180 dias', 365: '12 meses' };
  const ORIGENS = ['relato', 'webhook', 'log', 'banco', 'mcp'];
  const ESTADOS = { classificada: 'Classificada pelo Jev', via_llm: 'Classificada via LLM', incerta: 'Incerta', texto_vago: 'Texto vago', nao_classificada: 'Não classificada', aguardando: 'Aguardando classificação' };
  const RAMPA = { dor: ['#fdebdc', '#fbd3b3', '#f7b585', '#ef9255', '#e06f2f', '#bd5119', '#8f3a0f'], op: ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'] };
  const NC = 'Nenhum destes';

  // ---- carga: como o snapshot, desloca as datas para o último dia da amostra virar ontem
  const HOJE = new Date(); HOJE.setHours(23, 59, 59, 0);
  const ultimo = Math.max(...D.frentes.map(f => +new Date(f.ocorrido_em)));
  const desloca = Math.floor((+HOJE - DIA - ultimo) / DIA) * DIA;
  D.frentes.forEach(f => { f.t = +new Date(f.ocorrido_em) + desloca; });
  D.enderecamentos.forEach(e => { e.t = +new Date(e.data) + desloca; });
  D.revisao.t = +new Date(D.revisao.data) + desloca;
  const PORID = {}; D.frentes.forEach(f => { PORID[f.id] = f; });

  // ---- estado
  const S = { rota: 'mapa', visao: 'dor', periodo: 90, v: 2, origens: [], cel: null, frente: null, vf: null,
    lista: { periodo: 90, origem: '', natureza: '', estado: '', cel: null, problema: '', busca: '', ordem: 'data' },
    tax: 'diff', pisca: {}, atualizando: {}, relato: null, endForm: null, passo: 0 };
  let variante = (new URLSearchParams(location.search).get('variant') || 'A').toUpperCase();
  if (!VARIANTES[variante]) variante = 'A';

  // ---- utilidades
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const n0 = x => Math.round(x).toLocaleString('pt-BR');
  const n2 = x => (x == null ? '—' : x.toFixed(2).replace('.', ','));
  const dma = t => new Date(t).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
  const dmaa = t => new Date(t).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const chave = (a, t) => a + '|' + t;
  const cls = (f, v) => f.c[v || S.v] || null;
  const pinta = c => c && (c.estado === 'classificada' || c.estado === 'via_llm');
  const medida = (c, visao) => (visao === 'dor' ? c.sev : c.imp);
  const daVisao = (c, visao) => (c.natureza === 'reativa') === (visao === 'dor');
  const noPeriodo = (f, dias, atras) => { const d = (+HOJE - f.t) / DIA; return d >= (atras || 0) * dias && d < ((atras || 0) + 1) * dias; };
  const origemOk = f => !S.origens.length || S.origens.includes(f.origem);
  const estadoDe = c => !c ? 'aguardando' : c.estado === 'aguardando_llm' ? 'aguardando' : c.motivo === 'texto_vago' ? 'texto_vago' : c.estado;
  const tipos = v => Object.keys(D.tax[v || S.v].tipos);

  // ---- agregados, calculados na leitura (como no modelo de dados)
  function agrega(v, visao, dias, comOrigem) {
    const cels = {}; let vagos = 0, aguard = 0, incertas = 0;
    const pega = k => (cels[k] = cels[k] || { idx: 0, ant: 0, n: 0, am: 0, inc: 0 });
    D.frentes.forEach(f => {
      if (comOrigem && !origemOk(f)) return;
      const c = f.c[v]; const agora = noPeriodo(f, dias, 0), antes = noPeriodo(f, dias, 1);
      if (!agora && !antes) return;
      const e = estadoDe(c);
      if (e === 'aguardando') { if (agora) aguard += f.peso; return; }
      if (e === 'texto_vago') { if (agora) vagos += f.peso; return; }
      const k = chave(c.area, c.tipo);
      if (e === 'incerta') { if (agora && daVisao(c, visao)) { pega(k).inc += f.peso; incertas += f.peso; } return; }
      if (e === 'nao_classificada') { if (agora) { const x = pega(k); x.n += f.peso; x.am++; } return; }
      if (!daVisao(c, visao)) return;
      const x = pega(k);
      if (agora) { x.idx += medida(c, visao) * f.peso; x.n += f.peso; x.am++; } else x.ant += medida(c, visao) * f.peso;
    });
    const quentes = Object.entries(cels).filter(([k, x]) => x.idx > 0 && !k.includes(NC)).sort((a, b) => b[1].idx - a[1].idx);
    return { cels, vagos, aguard, incertas, top: quentes.slice(0, 3), max: quentes.length ? quentes[0][1].idx : 1 };
  }
  function tendencia(x, dias) {
    if (dias >= 365 || !x.ant) return null; // 12 meses: a seed não tem período anterior
    return (x.idx - x.ant) / x.ant;
  }
  const tendHtml = (x, dias) => { const t = tendencia(x, dias); if (t == null) return ''; const p = Math.round(t * 100); return `<span class="cel-tend">${p > 2 ? '↑' : p < -2 ? '↓' : '→'}${Math.abs(p)}%</span>`; };
  function frentesDaCelula(area, tipo, visao, dias, v) {
    return D.frentes.filter(f => { const c = f.c[v]; return c && c.area === area && c.tipo === tipo && noPeriodo(f, dias, 0) && estadoDe(c) !== 'texto_vago' && estadoDe(c) !== 'aguardando' && daVisao(c, visao); });
  }
  function serieMensal(area, tipo, visao, v) {
    const m = Array.from({ length: 12 }, (_, i) => ({ i, idx: 0, ini: +HOJE - (12 - i) * 30.4 * DIA }));
    D.frentes.forEach(f => { const c = f.c[v]; if (!pinta(c) || c.area !== area || c.tipo !== tipo || !daVisao(c, visao)) return;
      const i = 11 - Math.floor((+HOJE - f.t) / (30.4 * DIA)); if (i >= 0 && i < 12) m[i].idx += medida(c, visao) * f.peso; });
    return m;
  }
  function tipoDoEnderecamento(e, v) { // o arquivo da seed não cita tipo: vale o mais frequente das frentes de referência
    if (e.tipo) return e.tipo;
    const cont = {}; (e.frentes_ref || []).forEach(id => { const c = PORID[id] && PORID[id].c[v]; if (c) cont[c.tipo] = (cont[c.tipo] || 0) + 1; });
    return (Object.entries(cont).sort((a, b) => b[1] - a[1])[0] || [])[0];
  }
  const enderecamento = (area, tipo, visao, v) => D.enderecamentos.find(e => e.ativo && e.area === area && e.visao === visao && tipoDoEnderecamento(e, v) === tipo);
  function problemasDaCelula(fs, dias, v) {
    const nomes = {}; fs.forEach(f => { const c = f.c[v]; if (c.problema && c.problema !== NC && c.conf_problema >= CFG.problema) nomes[c.problema] = (nomes[c.problema] || 0) + 1; });
    return Object.keys(nomes).map(nome => {
      const todas = D.frentes.filter(f => { const c = f.c[v]; return c && c.problema === nome && c.conf_problema >= CFG.problema && noPeriodo(f, dias, 0); });
      const dias_ = new Set(todas.map(f => new Date(f.t).toDateString())).size;
      const fora = new Set(todas.map(f => chave(f.c[v].area, f.c[v].tipo))).size - 1;
      return { nome, aqui: nomes[nome], total: todas.length, dias: dias_, fora, recorrente: dias_ >= CFG.recorrencia };
    }).sort((a, b) => b.dias - a.dias);
  }
  const encaixeFraco = c => c && (c.jev_tipo === NC || c.conf_tipo < CFG.fraco);

  // ---- textos do painel da célula. No PoC a LLM escreve e guarda; aqui são fixos (escritos à mão) ou montados dos dados.
  const PAINEL = {
    'dor|Originação|Disponibilidade e Performance': { porque: 'A esteira de propostas cai ou fica lenta nos picos de fim de mês desde a migração para a nuvem. Os erros de timeout em /propostas e os alertas de latência se repetem em dias diferentes, e os relatos falam de concessionárias que não conseguem enviar proposta. O número de episódios cresce a cada mês.',
      sug: [['ferramenta/automação', 'Rever o autoscaling e o dimensionamento da esteira de propostas para o pico de fim de mês, com teste de carga antes do próximo fechamento.'], ['pessoas', 'Dedicar dois engenheiros de plataforma à esteira de propostas por um trimestre, com meta de disponibilidade.'], ['processo', 'Criar um plantão de fechamento de mês, com alerta e dono definidos para a esteira.']] },
    'dor|Plataforma e Sustentação|Disponibilidade e Performance': { porque: 'Os mesmos serviços de infraestrutura que sustentam a esteira de propostas aparecem aqui: latência alta e taxa de erro em svc-infra-e-cloud, em dias diferentes. A célula sobe junto com a de Originação, o que indica uma causa comum na migração para a nuvem.',
      sug: [['ferramenta/automação', 'Ajustar capacidade e limites dos serviços migrados, e ligar alertas de saturação antes do pico.'], ['fornecedor', 'Rever com o provedor de nuvem o dimensionamento contratado para o fim de mês.']] },
    'dor|Formalização|Processo e Fluxo de Trabalho': { porque: 'O registro de gravame no Detran falha ou atrasa, e os contratos ficam parados dias a fio. O time redigita à mão o que a integração rejeita. É uma dor crônica: aparece em quase todos os meses, sem pico.',
      sug: [['fornecedor', 'Renegociar o SLA com o registrador de gravame e exigir retorno estruturado das rejeições.'], ['ferramenta/automação', 'Automatizar o reenvio das rejeições e avisar o time quando a fila de pendências passar de um limite.']] },
    'dor|Pós-venda e Cobrança|Integridade e Consistência de Dados': { porque: 'Boletos e carnês saíam com valor ou vencimento diferente do contrato. Foi o maior ponto de dor da área no primeiro semestre; depois do mutirão de correção as frentes caíram.',
      sug: [['ferramenta/automação', 'Manter a conferência automática do lote contra o contrato e alertar quando houver divergência.']] },
    'op|Canal Parceiro|Experiência do Parceiro e do Cliente': { porque: 'Lojistas e concessionárias pedem para simular e acompanhar a proposta direto no portal. Hoje isso passa por WhatsApp e por ligação ao correspondente. Os pedidos chegam por relato e pelo resumo dos chats, com impacto esperado alto.',
      sug: [['ferramenta/automação', 'Levar simulação e status da proposta para o portal do lojista, com upload de documentos pelo celular.'], ['processo', 'Definir um canal oficial com o lojista enquanto o portal não cobre o fluxo.']] },
    'op|Canal Parceiro|Processo e Fluxo de Trabalho': { porque: 'A comissão dos parceiros é calculada em planilha, o que gera contestação e retrabalho. Os pedidos são por um cálculo automático e um painel onde o lojista veja o valor e a data do pagamento.',
      sug: [['ferramenta/automação', 'Automatizar o cálculo da comissão e publicar o extrato no portal do lojista.']] },
    'dor|Canal Digital|IA e Assistentes Virtuais': { porque: 'O assistente de IA do app informa taxa errada, inventa respostas e encaminha conversas demais para o atendimento humano. O tema apareceu no meio do ano e não cabia em nenhum tipo da versão anterior da taxonomia.',
      sug: [['ferramenta/automação', 'Restringir o assistente à base de taxas e regras oficiais e medir a taxa de escalonamento por assunto.'], ['processo', 'Aprovar uma política de uso de IA antes que outros times adotem assistentes.']] },
    'op|Plataforma e Sustentação|Infraestrutura e Operação': { porque: 'Os times pedem ambientes de homologação próprios, pipeline mais rápido e menos passos manuais no deploy. Nada está quebrado, mas a soma do impacto esperado é a maior da visão.',
      sug: [['ferramenta/automação', 'Padronizar o pipeline de deploy e criar ambientes de homologação por time.'], ['treinamento', 'Formar os times no uso do pipeline padrão, para tirar o deploy manual.']] },
  };
  const SOLUCAO_POR_CAUSA = { 'Falta de Automação': 'ferramenta/automação', 'Falta de Testes e Cobertura': 'treinamento', 'Dívida Técnica e Acoplamento': 'pessoas', 'Falha de Comunicação e Alinhamento': 'processo', 'Falta de Monitoramento e Observabilidade': 'ferramenta/automação', 'Erro de Configuração ou Capacidade': 'ferramenta/automação', 'Dependência Externa Instável': 'fornecedor' };
  const conta = (fs, fn) => { const m = {}; fs.forEach(f => { const k = fn(f); if (k && k !== NC) m[k] = (m[k] || 0) + f.peso; }); return Object.entries(m).sort((a, b) => b[1] - a[1]); };
  function textoPainel(area, tipo, visao, fs, v) {
    const p = PAINEL[chave(visao, chave(area, tipo))];
    if (p) return { porque: p.porque, sug: p.sug, fixo: true };
    const cl = fs.filter(f => pinta(f.c[v]));
    const sub = conta(cl, f => f.c[v].subtipo)[0], tm = conta(cl, f => f.c[v].time)[0], ca = conta(cl.filter(f => f.c[v].conf_causa >= CFG.causa), f => f.c[v].causa)[0];
    const porque = `O que mais aparece nesta célula é “${sub ? sub[0] : tipo}”, no time ${tm ? tm[0] : area}.` + (ca ? ` A causa raiz mais citada é “${ca[0]}”.` : '') + ' (Texto montado pelo protótipo a partir dos dados; no PoC é a LLM que escreve.)';
    const sol = ca ? SOLUCAO_POR_CAUSA[ca[0]] || 'processo' : 'processo';
    return { porque, sug: [[sol, `Atacar “${ca ? ca[0] : (sub ? sub[0] : tipo)}” no time ${tm ? tm[0] : area}.`]], fixo: false };
  }

  // ---- peças comuns
  const origemChip = o => `<span class="tag">${esc(o)}</span>`;
  function estadoTags(f, c) {
    const e = estadoDe(c); let h = '';
    if (f.aoVivo) h += '<span class="tag viv">ao vivo</span>';
    if (e === 'via_llm') h += '<span class="tag llm">via LLM</span>';
    if (e === 'incerta') h += '<span class="tag inc">incerta</span>';
    if (e === 'texto_vago') h += '<span class="tag inc">texto vago</span>';
    if (e === 'nao_classificada') h += '<span class="tag">não classificada</span>';
    if (e === 'aguardando') h += '<span class="tag">aguardando</span>';
    if (c && pinta(c) && c.urg >= CFG.urgente) h += '<span class="tag urg">urgente</span>';
    return h;
  }
  const confBarra = (x, corte) => x == null ? '<span class="mfraco">—</span>' : `<span class="conf ${x < (corte == null ? CFG.limiar : corte) ? 'baixa' : ''}"><span class="tr"><i style="width:${Math.round(x * 100)}%"></i></span><span class="num">${n2(x)}</span></span>`;
  const confGeral = c => Math.min(c.conf_area, c.conf_tipo, c.conf_natureza);
  function linhaFrente(f, v, visao) {
    const c = f.c[v];
    const med = c && pinta(c) ? `${c.natureza === 'reativa' ? 'sev' : 'imp'} <b class="num">${n2(c.natureza === 'reativa' ? c.sev : c.imp)}</b><br>conf ${n2(confGeral(c))}` : '';
    return `<div class="ln" data-frente="${esc(f.id)}"><span class="mfraco num">${dma(f.t)}</span><span>${origemChip(f.origem)}</span><span class="tx">${esc(f.texto)} ${estadoTags(f, c)}</span><span class="med">${med}</span></div>`;
  }

  // ---- tela: mapa de calor
  function telaMapa() {
    const A = agrega(S.v, S.visao, S.periodo, true), ts = tipos(S.v), novos = S.v === 2 ? ts.filter(t => !D.tax[1].tipos[t]) : [];
    const cor = idx => { const p = Math.min(6, Math.floor((idx / A.max) * 6.999)); return { bg: RAMPA[S.visao][p], fg: p >= 4 ? '#fff' : '#1d1c1a' }; };
    const celula = (a, t) => {
      const k = chave(a, t), x = A.cels[k], nc = a === NC || t === NC;
      if (!x || (!x.idx && !x.inc && !x.n)) return '<td class="vazia"></td>';
      const sel = S.cel === k ? ' sel' : '', pis = S.pisca[k] ? ' pisca' : '';
      if (nc) return `<td class="nc${sel}" data-lista-cel="${esc(k)}" data-dica="${esc(n0(x.n))} frentes não classificadas\nNão entram no índice.">${n0(x.n)}<div class="mfraco">frentes</div></td>`;
      const e = enderecamento(a, t, S.visao, S.v), c = x.idx ? cor(x.idx) : { bg: '#f3f2ee', fg: '#55534e' };
      const dica = `${a} × ${t}\n${VISOES[S.visao]}: ${n0(x.idx)} em ${n0(x.n)} frentes` + (x.inc ? `\n+${n0(x.inc)} incertas (não pintam)` : '') + (e ? `\nEndereçada em ${dmaa(e.t)}` : '');
      return `<td class="${sel}${pis}" style="background:${c.bg};color:${c.fg}" data-cel="${esc(k)}" data-dica="${esc(dica)}">` +
        (x.idx ? `<span class="cel-idx num" data-anima="${esc(k)}">${n0(x.idx)}</span>${tendHtml(x, S.periodo)}` : '') +
        (S.pisca[k] ? `<span class="cel-mais">+${S.pisca[k]}</span>` : '') +
        (x.inc ? `<span class="cel-inc">+${n0(x.inc)} incertas</span>` : '') + (e ? `<span class="cel-end">◆ ${dma(e.t)}</span>` : '') + '</td>';
    };
    const temNcLinha = Object.keys(A.cels).some(k => k.startsWith(NC + '|')), temNcCol = Object.keys(A.cels).some(k => k.endsWith('|' + NC));
    const cols = ts.concat(temNcCol ? [NC] : []), lins = D.areas.concat(temNcLinha ? [NC] : []);
    const nomeNc = x => (x === NC ? 'Não classificadas' : x);
    const top = A.top.map(([k, x], i) => { const [a, t] = k.split('|'); const e = enderecamento(a, t, S.visao, S.v);
      return `<div class="cartao" data-cel="${esc(k)}"><span class="pos">${i + 1}</span><span class="nome">${esc(a)} × ${esc(t)}</span><span class="idx num">${n0(x.idx)}</span><span class="sub">${n0(x.n)} frentes ${tendHtml(x, S.periodo)} ${e ? `<span class="tag">◆ endereçada em ${dma(e.t)}</span>` : ''}</span></div>`; }).join('');
    const vivas = D.frentes.filter(f => f.aoVivo).slice(-5).reverse();
    const feed = vivas.length ? `<div class="aovivo"><div class="tit"><span class="ponto"></span> chegando agora · ${D.frentes.filter(f => f.aoVivo).length} frentes nesta sessão</div>` +
      vivas.map(f => { const c = f.c[S.v]; return `<div class="lin" data-frente="${esc(f.id)}"><span class="num">${new Date(f.t).toLocaleTimeString('pt-BR')}</span><span class="tx">${esc(f.texto)}</span><span class="ce">${c ? esc(c.area) + ' × ' + esc(c.tipo) + ' · ' + n2(confGeral(c)) : 'classificando…'}</span></div>`; }).join('') + '</div>' : '';
    const faixa = S.v === 1
      ? `<div class="faixa v1"><b>Versão 1 da taxonomia</b><span class="fraco">anterior à revisão de ${dmaa(D.revisao.t)} · mesmas frentes, mesma data de hoje</span><span class="selo-sinal" data-go="taxonomia">Sinal de encaixe: ${String(D.revisao.medidas.fraco_pct).replace('.', ',')}% de encaixe fraco (limite ${CFG.sinal}%)</span><a data-go="taxonomia">ver a revisão →</a></div>`
      : (novos.length ? `<div class="faixa v2"><b>Versão 2 (vigente)</b><span class="fraco">a revisão de ${dmaa(D.revisao.t)} criou ${novos.length === 1 ? 'a coluna' : 'as colunas'} “${esc(novos.join('”, “'))}”</span><a data-go="taxonomia">ver o que mudou →</a></div>` : '');
    return `<div class="controles">
        <span class="seg">${Object.entries(VISOES).map(([k, n]) => `<button class="${S.visao === k ? 'at' : ''}" data-set="visao=${k}">${n}</button>`).join('')}</span>
        <span><span class="rot">Período</span><span class="seg">${Object.entries(PERIODOS).map(([k, n]) => `<button class="${+S.periodo === +k ? 'at' : ''}" data-set="periodo=${k}">${n}</button>`).join('')}</span></span>
        <span><span class="rot">Origem</span>${ORIGENS.map(o => `<span class="chip ${S.origens.includes(o) ? 'at' : ''}" data-origem="${o}">${o}</span>`).join(' ')}</span>
        <span><span class="rot">Taxonomia</span><span class="seg"><button class="${S.v === 1 ? 'at' : ''}" data-set="v=1">v1</button><button class="${S.v === 2 ? 'at' : ''}" data-set="v=2">v2 vigente</button></span></span>
        <span class="contadores"><button class="contador" data-lista-estado="texto_vago" data-dica="Relatos sem nada concreto. Ficam fora das células.">Texto vago: <b class="num">${n0(A.vagos)}</b></button>
        <button class="contador" data-lista-estado="incerta" data-dica="Abaixo do limiar de confiança. Não pintam o mapa.">Incertas: <b class="num">${n0(A.incertas)}</b></button>
        ${A.aguard ? `<button class="contador" data-lista-estado="aguardando">Aguardando classificação: <b class="num">${n0(A.aguard)}</b></button>` : ''}</span>
      </div>${faixa}${feed}
      <h3>Top 3 onde investir · ${VISOES[S.visao]} · ${PERIODOS[S.periodo]}</h3><div class="top3">${top || '<span class="fraco">Sem frentes no período.</span>'}</div>
      <div class="grade-caixa"><table class="grade"><thead><tr><th class="lin"></th>${cols.map(t => `<th>${esc(nomeNc(t))}${novos.includes(t) ? '<span class="nova">nova</span>' : ''}</th>`).join('')}</tr></thead>
      <tbody>${lins.map(a => `<tr><th class="lin">${esc(nomeNc(a))}</th>${cols.map(t => celula(a, t)).join('')}</tr>`).join('')}</tbody></table>
      <div class="legenda"><span>${S.visao === 'dor' ? 'Índice de dor (soma da severidade das reativas)' : 'Soma do impacto esperado das proativas'}:</span><span>0</span><span class="rampa">${RAMPA[S.visao].map(c => `<i style="background:${c}"></i>`).join('')}</span><span class="num">${n0(A.max)}</span><span>· ↑↓ contra os ${PERIODOS[S.periodo]} anteriores · ◆ célula endereçada</span></div></div>`;
  }

  // ---- drill-down: painel da célula (não é tela nova; o lugar muda por variante)
  function painelCelula() {
    const [area, tipo] = S.cel.split('|'), v = S.v, visao = S.visao;
    const fs = frentesDaCelula(area, tipo, visao, S.periodo, v), cl = fs.filter(f => pinta(f.c[v]));
    const idx = cl.reduce((s, f) => s + medida(f.c[v], visao) * f.peso, 0), n = cl.reduce((s, f) => s + f.peso, 0);
    const A = agrega(v, visao, S.periodo, true).cels[S.cel] || { idx: 0, ant: 0 };
    const tx = textoPainel(area, tipo, visao, fs, v), e = enderecamento(area, tipo, visao, v), serie = serieMensal(area, tipo, visao, v);
    const mx = Math.max(1, ...serie.map(m => m.idx));
    const svg = `<svg viewBox="0 0 360 96" width="100%" style="max-width:520px">` + serie.map((m, i) => { const h = Math.round((m.idx / mx) * 64);
      return `<rect x="${i * 30 + 3}" y="${72 - h}" width="24" height="${h}" rx="3" fill="${RAMPA[visao][4]}" data-dica="${esc(new Date(m.ini + 15 * DIA).toLocaleDateString('pt-BR', { month: 'short', year: '2-digit' }) + ': ' + n0(m.idx))}"></rect><text x="${i * 30 + 15}" y="86" font-size="8" text-anchor="middle" fill="#8a877f">${new Date(m.ini + 15 * DIA).toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')}</text>`; }).join('') +
      (e ? (() => { const pos = 12 - (+HOJE - e.t) / (30.4 * DIA); if (pos < 0 || pos > 12) return ''; const x = Math.round(pos * 30); return `<line x1="${x}" y1="0" x2="${x}" y2="74" stroke="#1d1c1a" stroke-width="2" stroke-dasharray="3 2"></line><text x="${x + 4}" y="9" font-size="9" fill="#1d1c1a">◆ endereçada ${dma(e.t)}</text>`; })() : '') + '</svg>';
    let blocoEnd = '';
    if (e) {
      const dias = Math.max(1, Math.round((+HOJE - e.t) / DIA)); let dep = 0, ant = 0;
      D.frentes.forEach(f => { const c = f.c[v]; if (!pinta(c) || c.area !== area || c.tipo !== tipo || !daVisao(c, visao)) return; const d = (f.t - e.t) / DIA; if (d >= 0 && d < dias) dep += medida(c, visao) * f.peso; else if (d < 0 && d >= -dias) ant += medida(c, visao) * f.peso; });
      const vari = ant ? Math.round(((dep - ant) / ant) * 100) : null;
      blocoEnd = `<div class="bloco"><h3>Endereçamento</h3><div class="end-caixa"><p><b>◆ Decidido em ${dmaa(e.t)}</b>${e.quem ? ' · ' + esc(e.quem) : ''} <span class="tag sug">${esc(e.solucao)}</span>${e.procedencia === 'tela' ? '<span class="tag viv">marcado agora</span>' : ''}</p><p>${esc(e.texto)}</p>
        <p class="fraco">Desde a data: índice ${vari == null ? 'sem base de comparação' : `<b>${vari > 0 ? '+' : ''}${vari}%</b> (${n0(ant)} nos ${dias} dias antes, ${n0(dep)} nos ${dias} dias depois)`}. O endereçamento não tira nada do índice.</p>
        <button class="mini" data-act="desfazer">Desfazer</button></div></div>`;
    }
    const sugs = tx.sug.map((s, i) => `<div class="sug"><div><span class="tag sug">sugestão</span><span class="tag">${esc(s[0])}</span><br>${esc(s[1])}</div>${e ? '' : `<button class="mini" data-act="endform" data-i="${i}">Endereçar com esta sugestão</button>`}</div>` +
      (S.endForm === i && !e ? `<div class="end-form bloco"><label class="mfraco">Texto da decisão (pode editar)</label><textarea id="end-texto" rows="3">${esc(s[1])}</textarea><label class="mfraco">Quem decidiu (opcional)</label><input id="end-quem" placeholder="nome ou comitê"><p style="margin-top:8px"><button class="lig" data-act="enderecar" data-sol="${esc(s[0])}">Registrar o endereçamento</button> <button data-act="endcancel">Cancelar</button></p></div>` : '')).join('');
    const barras = (tit, itens) => `<div class="barras"><h3>${tit}</h3>${itens.slice(0, 4).map(([k, q]) => `<div class="ln"><span>${esc(k)}</span><span class="tr"><i style="width:${Math.round((q / itens[0][1]) * 100)}%"></i></span><span class="num">${n0(q)}</span></div>`).join('') || '<span class="mfraco">—</span>'}</div>`;
    const probs = problemasDaCelula(cl, S.periodo, v);
    const ordenadas = cl.slice().sort((a, b) => medida(b.c[v], visao) - medida(a.c[v], visao)).concat(fs.filter(f => !pinta(f.c[v])));
    const blocos = {
      porque: `<div class="bloco"><h3>Por que está quente ${S.atualizando[S.cel] ? '<span class="tag llm"><span class="gira"></span> atualizando</span>' : ''}</h3><p>${esc(tx.porque)}</p>
        <p class="mfraco">${tx.fixo ? 'Escrito pela LLM e guardado' : 'Montado pelo protótipo'} · sobre ${n0(n)} frentes${S.origens.length ? ` · <b>o texto considera todas as origens</b>; os números e a lista seguem o filtro (${S.origens.join(', ')})` : ''}</p></div>`,
      sug: `<div class="bloco"><h3>Sugestão de investimento</h3>${sugs}</div>`,
      evol: `<div class="bloco"><h3>Evolução · 12 meses</h3>${svg}</div>`,
      comp: `<div class="bloco"><div class="duas">${barras('Por time', conta(cl, f => f.c[v].time))}${barras('Por subtipo', conta(cl, f => f.c[v].subtipo))}${barras('Causa raiz', conta(cl.filter(f => f.c[v].conf_causa >= CFG.causa), f => f.c[v].causa))}</div></div>`,
      probs: `<div class="bloco"><h3>Problemas recorrentes</h3>${probs.length ? probs.map(p => `<p><a data-lista-problema="${esc(p.nome)}"><b>${esc(p.nome)}</b></a> ${p.recorrente ? `<span class="tag urg">recorrente · ${p.dias} dias diferentes</span>` : `<span class="tag">${p.dias} ${p.dias === 1 ? 'dia' : 'dias'}</span>`}<br><span class="mfraco">${p.aqui} frentes da amostra nesta célula${p.fora > 0 ? ` · também em ${p.fora} ${p.fora === 1 ? 'outra célula' : 'outras células'}` : ''}</span></p>`).join('') : `<span class="mfraco">${v === 1 ? 'A v1 desta amostra foi classificada antes de o problema virar dimensão.' : 'Nenhum problema da lista nas frentes desta célula.'}</span>`}</div>`,
      frentes: `<div class="bloco lista-f"><h3>Frentes da célula · ${n0(n)} <span class="mfraco" style="text-transform:none;letter-spacing:0">(a amostra do protótipo traz ${fs.length}; por ${visao === 'dor' ? 'severidade' : 'impacto esperado'})</span></h3>${ordenadas.slice(0, 8).map(f => linhaFrente(f, v, visao)).join('')}
        <p style="margin-top:8px"><a data-lista-cel="${esc(S.cel)}">ver todas na lista de frentes →</a></p></div>`,
    };
    const cab = `<div class="cab"><div><div class="mfraco">${VISOES[visao]} · ${PERIODOS[S.periodo]} · taxonomia v${v}</div><h2>${esc(area)} × ${esc(tipo)}</h2>${e ? `<span class="tag">◆ endereçada em ${dmaa(e.t)}</span>` : ''}</div>
      <div class="idx"><b class="num">${n0(idx)}</b> ${tendHtml(A, S.periodo)}<div class="mfraco">${n0(n)} frentes${fs.length - cl.length ? ` · +${fs.length - cl.length} incertas na amostra` : ''}</div></div></div>`;
    return { cab, blocos, blocoEnd };
  }

  // ---- tela: detalhe da frente
  function telaFrente() {
    const f = PORID[S.frente]; if (!f) return '<p>Frente não encontrada.</p>';
    const v = S.vf || S.v, c = f.c[v], e = estadoDe(c), T = D.tax[v];
    const meta = `<div class="meta"><b>${esc(f.id)}</b>${origemChip(f.origem)}<span>${esc(f.emissor || '—')}</span><span>ocorrida em ${dmaa(f.t)} ${new Date(f.t).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</span>${f.ref_externa ? `<span class="mfraco">ref ${esc(f.ref_externa)}</span>` : ''}${estadoTags(f, c)}</div>`;
    const textos = `<div class="texto">${esc(f.texto)}</div>` + (f.complemento ? `<div class="mfraco">Complemento, acrescentado em ${dmaa(f.complementado_em)}</div><div class="texto comp">${esc(f.complemento)}</div>` : '');
    if (e === 'aguardando' && !c) return `<div class="frente">${meta}${textos}<div class="bloco"><span class="gira"></span> Aguardando classificação. A frente já está gravada.</div></div>`;
    const motivo = e === 'texto_vago' ? `<div class="bloco"><b>Incerta: texto vago.</b> O texto não cita sistema, processo, número nem situação específica (pergunta de controle em ${n2(c.controle)}, corte ${n2(CFG.vago)}). Não foi à LLM, não aparece em nenhuma célula e não conta no sinal de encaixe.
        ${f.origem === 'relato' && !f.complemento ? `<div class="form"><label>Completar o relato (o texto original fica guardado)</label><textarea id="comp-texto" rows="3" placeholder="Qual sistema, tela ou rotina? Desde quando? Quantas vezes?"></textarea><p><button class="pri" data-act="completar">Completar e classificar de novo</button></p></div>` : ''}</div>`
      : e === 'incerta' ? `<div class="bloco"><b>Incerta: ${c.motivo === 'llm_sem_escolha' ? 'a LLM não escolheu entre as opções do Jev' : 'confiança abaixo do limiar'}</b>${c.motivo_dim && c.motivo_dim.length ? ` em ${c.motivo_dim.join(', ')}` : ''}. Não pinta o mapa; aparece como “+N incertas” em ${esc(c.area)} × ${esc(c.tipo)}.</div>`
      : e === 'nao_classificada' ? `<div class="bloco"><b>Não classificada:</b> a resposta em área ou tipo foi “Nenhum destes”. Aparece na linha ou coluna própria do mapa.</div>`
      : e === 'aguardando' ? `<div class="bloco"><span class="gira"></span> <b>Aguardando o desempate da LLM.</b> O Jev já respondeu; a confiança ficou abaixo do limiar.</div>` : '';
    const alt = top => (top || []).slice(1).filter(x => x[1] >= 0.05).map(x => `${esc(x[0])} ${n2(x[1])}`).join(' · ');
    const llmNota = d => c.llm && c.llm[d] ? `<div class="mfraco"><span class="tag llm">via LLM</span> o Jev ficou em ${esc(c['jev_' + d])} com ${n2(c['conf_' + d])}; a LLM escolheu no top 3.</div>` : '';
    const nivel = (regua, x) => regua[Math.min(regua.length - 1, Math.floor(x * regua.length))];
    const reativa = c.natureza === 'reativa';
    const lin = (dim, resp, conf, nota, apagada) => `<tr class="${apagada ? 'apagada' : ''}"><td><b>${dim}</b></td><td>${resp}</td><td>${conf}</td><td class="mfraco">${nota || ''}</td></tr>`;
    const dims = `<table class="dims"><thead><tr><th>Dimensão</th><th>Resposta</th><th>Confiança</th><th></th></tr></thead><tbody>` +
      lin('Área › time', `${esc(c.area)} › ${esc(c.time)}${llmNota('area')}`, confBarra(c.conf_area), alt(c.top_area) && 'outras: ' + alt(c.top_area)) +
      lin('Tipo › subtipo', `${esc(c.tipo)} › ${esc(c.subtipo)}${llmNota('tipo')}`, confBarra(c.conf_tipo), (alt(c.top_tipo) ? 'outras: ' + alt(c.top_tipo) : '') + (encaixeFraco(c) ? ' <span class="tag inc">encaixe fraco</span>' : '')) +
      lin('Natureza', esc(c.natureza), confBarra(c.conf_natureza), '') +
      lin('Severidade', `<b class="num">${n2(c.sev)}</b>`, '', reativa ? esc(nivel(T.regua_sev, c.sev)) : 'não conta: a frente é proativa', !reativa) +
      lin('Impacto esperado', `<b class="num">${n2(c.imp)}</b>`, '', !reativa ? esc(nivel(T.regua_imp, c.imp)) : 'não conta: a frente é reativa', reativa) +
      lin('Urgência', `<b class="num">${n2(c.urg)}</b> ${c.urg >= CFG.urgente ? '<span class="tag urg">urgente</span>' : ''}`, '', esc(T.urgencia)) +
      lin('Causa raiz', c.causa === NC ? '<span class="fraco">Nenhum destes</span>' : esc(c.causa) + (c.conf_causa < CFG.causa ? ' <span class="tag inc">causa incerta</span>' : ''), confBarra(c.conf_causa, CFG.causa), '') +
      lin('Problema', c.problema == null ? '<span class="fraco">—</span>' : c.problema === NC || c.conf_problema < CFG.problema ? '<span class="fraco">nenhum da lista</span>' : `<a data-lista-problema="${esc(c.problema)}">${esc(c.problema)}</a>`, c.problema == null ? '' : confBarra(c.conf_problema, CFG.problema), c.problema == null ? 'a v1 desta amostra não tem a dimensão' : '') +
      `</tbody></table><p class="mfraco" style="margin-top:8px">Pergunta de controle (“o texto cita algum sistema, processo, número ou situação específica?”): ${c.controle == null ? 'não medida nesta amostra' : `<b>${n2(c.controle)}</b>, corte ${n2(CFG.vago)}`}${c.llm && c.llm.porque ? `<br>Desempate da LLM: “${esc(c.llm.porque)}”` : ''}${c.modelo ? `<br>${esc(c.modelo)} · ${c.tok || '—'} tokens · ${c.lat ? n2(c.lat) + ' s' : '—'}` : ''}</p>`;
    const onde = pinta(c) ? `<p>Conta em <a data-abre-cel="${esc(chave(c.area, c.tipo))}" data-visao="${reativa ? 'dor' : 'op'}"><b>${esc(c.area)} × ${esc(c.tipo)}</b></a>, na visão “${VISOES[reativa ? 'dor' : 'op']}”, com ${reativa ? 'severidade' : 'impacto esperado'} ${n2(reativa ? c.sev : c.imp)}.</p>` : '';
    const seletor = f.c[1] && f.c[2] ? `<span class="seg" style="float:right"><button class="${v === 1 ? 'at' : ''}" data-set="vf=1">na v1</button><button class="${v === 2 ? 'at' : ''}" data-set="vf=2">na v2 vigente</button></span>` : '';
    return `<div class="frente">${meta}${textos}${motivo}<div class="bloco">${seletor}<h3>Classificação na versão ${v}</h3>${onde}${dims}</div></div>`;
  }

  // ---- tela: lista de frentes
  function filtraLista() {
    const L = S.lista, v = S.v;
    return D.frentes.filter(f => {
      const c = f.c[v], e = estadoDe(c);
      if (L.periodo && !noPeriodo(f, +L.periodo, 0)) return false;
      if (L.origem && f.origem !== L.origem) return false;
      if (L.natureza && (!c || c.natureza !== L.natureza)) return false;
      if (L.estado && e !== L.estado) return false;
      if (L.cel && (!c || chave(c.area, c.tipo) !== L.cel || e === 'texto_vago')) return false;
      if (L.problema && (!c || c.problema !== L.problema || c.conf_problema < CFG.problema)) return false;
      if (L.busca && !f.texto.toLowerCase().includes(L.busca.toLowerCase())) return false;
      return true;
    }).sort((a, b) => L.ordem === 'data' ? b.t - a.t : ((b.c[v] ? Math.max(b.c[v].sev, b.c[v].imp) : 0) - (a.c[v] ? Math.max(a.c[v].sev, a.c[v].imp) : 0)));
  }
  function telaLista() {
    const L = S.lista, fs = filtraLista(), v = S.v, total = fs.reduce((s, f) => s + f.peso, 0);
    const sel = (campo, ops, vazio) => `<select data-lista="${campo}"><option value="">${vazio}</option>${ops.map(([k, n]) => `<option value="${esc(k)}" ${String(L[campo]) === String(k) ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select>`;
    const linhas = fs.slice(0, 80).map(f => { const c = f.c[v], e = estadoDe(c), mostra = c && e !== 'texto_vago';
      return `<tr class="cl" data-frente="${esc(f.id)}"><td class="num">${dma(f.t)}</td><td>${origemChip(f.origem)}</td><td>${esc(f.emissor || '')}</td><td class="tx">${esc(f.texto.length > 150 ? f.texto.slice(0, 150) + '…' : f.texto)}</td>
        <td>${mostra ? esc(c.area) + '<br><span class="mfraco">' + esc(c.tipo) + '</span>' : '<span class="mfraco">—</span>'}</td><td>${mostra ? esc(c.natureza) : ''}</td><td class="num">${mostra ? n2(c.natureza === 'reativa' ? c.sev : c.imp) : ''}</td><td class="num">${mostra ? n2(confGeral(c)) : ''}</td><td>${estadoTags(f, c) || '<span class="tag ok">Jev</span>'}</td></tr>`; }).join('');
    return `<div class="controles form" style="max-width:none">
        <span><span class="rot">Período</span>${sel('periodo', Object.entries(PERIODOS), 'tudo')}</span><span><span class="rot">Origem</span>${sel('origem', ORIGENS.map(o => [o, o]), 'todas')}</span>
        <span><span class="rot">Natureza</span>${sel('natureza', [['reativa', 'reativa'], ['proativa', 'proativa']], 'as duas')}</span><span><span class="rot">Estado</span>${sel('estado', Object.entries(ESTADOS), 'todos')}</span>
        <span><span class="rot">Ordem</span>${sel('ordem', [['data', 'mais recentes'], ['medida', 'severidade ou impacto']], '')}</span>
        <span><input data-lista="busca" placeholder="buscar no texto" value="${esc(L.busca)}" style="width:180px"></span></div>
      <p>${L.cel ? `<span class="chip at" data-limpa="cel">célula: ${esc(L.cel.replace('|', ' × ').replace(NC, 'Não classificadas'))} ✕</span> ` : ''}${L.problema ? `<span class="chip at" data-limpa="problema">problema: ${esc(L.problema)} ✕</span> ` : ''}
        <b class="num">${n0(total)}</b> frentes <span class="mfraco">(a amostra do protótipo traz ${fs.length}${fs.length > 80 ? '; mostrando 80' : ''}) · taxonomia v${v}</span></p>
      <table class="tab"><thead><tr><th>Data</th><th>Origem</th><th>Emissor</th><th>Texto</th><th>Área · tipo</th><th>Natureza</th><th>Sev./imp.</th><th>Conf.</th><th>Estado</th></tr></thead><tbody>${linhas || '<tr><td colspan="9" class="fraco">Nenhuma frente com esses filtros.</td></tr>'}</tbody></table>`;
  }

  // ---- tela: formulário de relato (o Jev aqui é um dublê)
  const PREPARADO = 'A tela de renegociação trava quando o cliente tem mais de três contratos ativos. O atendente perde o acordo e precisa refazer do zero. Aconteceu 4 vezes só esta semana na central.';
  const VAGO = 'As coisas estão muito difíceis ultimamente, o time está cansado e ninguém resolve nada.';
  const PISTAS = [['renegocia', 'Pós-venda e Cobrança', 'Renegociação'], ['boleto', 'Pós-venda e Cobrança', 'Boletos e Carnês'], ['carnê', 'Pós-venda e Cobrança', 'Boletos e Carnês'], ['gravame', 'Formalização', 'Gravame'], ['detran', 'Formalização', 'Gravame'], ['contrato', 'Formalização', 'Contratos'], ['assinatura', 'Formalização', 'Documentação e Assinatura'], ['lojista', 'Canal Parceiro', 'Portal do Lojista'], ['portal', 'Canal Parceiro', 'Portal do Lojista'], ['comiss', 'Canal Parceiro', 'Comissionamento de Parceiros'], ['app', 'Canal Digital', 'App'], ['proposta', 'Originação', 'Proposta'], ['simula', 'Originação', 'Simulação'], ['cadastro', 'Originação', 'Cadastro e KYC'], ['fraude', 'Crédito', 'Antifraude'], ['política', 'Crédito', 'Políticas de Crédito'], ['motor', 'Crédito', 'Motor de Decisão'], ['deploy', 'Plataforma e Sustentação', 'Infra e Cloud'], ['nuvem', 'Plataforma e Sustentação', 'Infra e Cloud'], ['relatório', 'Dados e Regulatório', 'Relatórios Regulatórios'], ['lgpd', 'Dados e Regulatório', 'Privacidade (LGPD)']];
  function classificaDuble(texto, origem) {
    const t = texto.toLowerCase(), pista = PISTAS.find(p => t.includes(p[0]));
    const concreto = pista || /\d/.test(texto) || /svc-|sistema|tela|api|planilha/.test(t);
    const pro = /sugiro|gostaria|poder[ií]amos|seria bom|proponho|quer(o|emos) /.test(t);
    const base = { natureza: pro ? 'proativa' : 'reativa', conf_natureza: 0.97, causa: 'Dívida Técnica e Acoplamento', conf_causa: 0.44, sev: 0.58, imp: 0.61, urg: 0.62, problema: NC, conf_problema: 0.98, llm: null, tok: 3948, lat: 0.62, modelo: 'jev-1.13.0 (dublê do protótipo)', motivo: null, motivo_dim: [] };
    if (!concreto) return Object.assign(base, { estado: 'incerta', motivo: 'texto_vago', controle: 0.12, area: NC, time: NC, tipo: NC, subtipo: NC, jev_area: NC, jev_tipo: NC, conf_area: 0.4, conf_tipo: 0.4, top_area: [], top_tipo: [] });
    const [, area, time] = pista || [0, 'Plataforma e Sustentação', 'Suporte N2/N3'];
    const apm = origem === 'webhook';
    const tipo = apm && /ci-cd/.test(t) ? 'Infraestrutura e Operação' : pro ? 'Processo e Fluxo de Trabalho' : 'Disponibilidade e Performance';
    const subtipo = Object.keys(D.tax[2].tipos[tipo].subtipos)[apm ? 0 : 1] || '';
    const ca = apm ? 0.88 + Math.random() * 0.1 : 0.94, ct = apm ? 0.9 + Math.random() * 0.09 : 0.81;
    return Object.assign(base, { estado: 'classificada', controle: 0.96, area, time, tipo, subtipo, jev_area: area, jev_tipo: tipo, conf_area: ca, conf_tipo: ct, sev: apm ? 0.55 + Math.random() * 0.35 : 0.58,
      top_area: [[area, ca], ['Plataforma e Sustentação', 1 - ca]], top_tipo: [[tipo, ct], ['Integridade e Consistência de Dados', 1 - ct]] });
  }
  let seq = 0;
  function entraFrente(origem, emissor, texto, extra) {
    const f = Object.assign({ id: 'vivo' + String(++seq).padStart(3, '0'), origem, emissor, texto, t: Date.now(), peso: 1, aoVivo: true, c: {} }, extra || {});
    D.frentes.push(f); PORID[f.id] = f; return f;
  }
  function classificaEPisca(f) {
    const c = classificaDuble(f.texto + ' ' + (f.complemento || ''), f.origem); f.c = { 1: c, 2: c };
    if (pinta(c)) { const k = chave(c.area, c.tipo); S.pisca[k] = (S.pisca[k] || 0) + 1; S.atualizando[k] = true;
      setTimeout(() => { delete S.pisca[k]; }, 3200); setTimeout(() => { delete S.atualizando[k]; desenha(); }, 6000); }
    return c;
  }
  function telaRelato() {
    const R = S.relato; let res = '';
    if (R && R.fase === 'classificando') res = `<div class="resultado"><span class="gira"></span> Frente recebida e gravada. Classificando…</div>`;
    if (R && R.fase === 'pronta') { const f = PORID[R.id], c = f.c[S.v];
      res = estadoDe(c) === 'texto_vago'
        ? `<div class="resultado vago"><b>Recebemos o seu relato, mas ele ficou vago.</b><p>Ele já está gravado. Para entrar no mapa, diga algo concreto: qual sistema, tela ou rotina, desde quando, quantas vezes.</p><div class="texto fraco">“${esc(f.texto)}”</div>
           <label>Completar (o texto original fica guardado)</label><textarea id="comp-texto" rows="3"></textarea><p style="margin-top:8px"><button class="pri" data-act="completar" data-id="${esc(f.id)}">Completar e classificar de novo</button> <button data-act="novo-relato">Deixar assim</button></p></div>`
        : `<div class="resultado"><b>Frente classificada</b> <span class="mfraco">em ${n2(c.lat)} s</span>
           <table class="dims"><tbody><tr><td><b>Área › time</b></td><td>${esc(c.area)} › ${esc(c.time)}</td><td>${confBarra(c.conf_area)}</td></tr><tr><td><b>Tipo › subtipo</b></td><td>${esc(c.tipo)} › ${esc(c.subtipo)}</td><td>${confBarra(c.conf_tipo)}</td></tr>
           <tr><td><b>Natureza</b></td><td>${esc(c.natureza)}</td><td>${confBarra(c.conf_natureza)}</td></tr><tr><td><b>${c.natureza === 'reativa' ? 'Severidade' : 'Impacto esperado'}</b></td><td class="num"><b>${n2(c.natureza === 'reativa' ? c.sev : c.imp)}</b></td><td></td></tr></tbody></table>
           <p style="margin-top:10px"><button class="lig" data-abre-cel="${esc(chave(c.area, c.tipo))}" data-visao="${c.natureza === 'reativa' ? 'dor' : 'op'}" data-so-mapa="1">Ver no mapa</button> <button data-frente="${esc(f.id)}">Abrir a frente</button> <button data-act="novo-relato">Novo relato</button></p></div>`; }
    return `<div class="form"><h2>Relatar uma frente</h2><p class="fraco">Escreva como você fala. Um problema que está doendo ou uma ideia de melhoria.</p>
      <label>Quem relata</label><select id="rel-emissor">${D.emissores.slice(0, 12).map(p => `<option>${esc(p.nome)} — ${esc(p.cargo)}, ${esc(p.time)}</option>`).join('')}<option>Outra pessoa (digitar)</option></select>
      <label>O que está acontecendo, ou o que poderia melhorar</label><textarea id="rel-texto" placeholder="Qual sistema, tela ou rotina? Desde quando? Quantas vezes?">${esc(R && R.rascunho || '')}</textarea>
      <p style="margin-top:10px"><button class="pri" data-act="enviar-relato" ${R && R.fase === 'classificando' ? 'disabled' : ''}>Enviar</button></p>${res}</div>`;
  }

  // ---- tela: taxonomia (só leitura) e a revisão gravada
  function telaTaxonomia() {
    const R = D.revisao, novo = tipos(2).filter(t => !D.tax[1].tipos[t]);
    const moveram = {}; D.frentes.forEach(f => { if (f.c[1] && f.c[2] && novo.includes(f.c[2].tipo) && pinta(f.c[2])) moveram[f.c[1].tipo] = (moveram[f.c[1].tipo] || 0) + f.peso; });
    const evid = D.frentes.filter(f => f.c[1] && f.c[2] && novo.includes(f.c[2].tipo) && encaixeFraco(f.c[1]) && f.t <= R.t && f.t > R.t - 95 * DIA).slice(0, 5);
    const ops = R.operacoes.map(o => o.op === 'criar_tipo'
      ? `<div class="op"><b>+ Tipo novo: ${esc(o.nome)}</b> <span class="mfraco">${o.evidencias.length} frentes de evidência (mínimo 5)</span><p>${esc(o.descricao)}</p>${o.subtipos.map(s => `<p style="margin-left:14px"><b>+ ${esc(s.nome)}</b><br><span class="fraco">${esc(s.descricao)}</span></p>`).join('')}</div>`
      : `<div class="op mud"><b>~ ${o.op === 'reescrever_descricao' ? 'Descrição reescrita' : esc(o.op)}: ${esc(o.nome)}</b> <span class="mfraco">${o.evidencias.length} frentes de evidência</span><p>${esc(o.descricao)}</p></div>`).join('');
    const diff = `<div class="passos3"><span class="p" data-set="v=1" data-go="mapa">1 · mapa na v1, com o sinal</span>→<span class="p at">2 · o que a revisão mudou</span>→<span class="p" data-set="v=2" data-go="mapa">3 · mapa na v2</span></div>
      <h2>Revisão de ${dmaa(R.t)} · v1 → v2</h2>
      <div class="frase">${esc(R.resumo)}<div class="mfraco">Frase escrita pela LLM na revisão e guardada.</div></div>
      <div class="bloco"><h3>O sinal que disparou</h3><p><span class="selo-sinal">Encaixe fraco: ${String(R.medidas.fraco_pct).replace('.', ',')}%</span> das ${R.medidas.n} frentes da janela, contra o limite de ${CFG.sinal}%. Não classificadas: ${String(R.medidas.nenhum_pct).replace('.', ',')}% · incertas: ${String(R.medidas.incertas_pct).replace('.', ',')}%.</p>
        <p class="fraco">Encaixe fraco é a frente em que o Jev respondeu “Nenhum destes” no tipo ou ficou com confiança abaixo de ${n2(CFG.fraco)}, antes do desempate.</p></div>
      <div class="bloco"><h3>Operações aplicadas</h3>${ops}${R.descartadas.length ? `<p class="mfraco">${R.descartadas.length} operações descartadas por falta de evidência.</p>` : ''}</div>
      <div class="bloco lista-f"><h3>Frentes de evidência</h3>${evid.map(f => linhaFrente(f, 1, 'dor')).join('') || '<span class="mfraco">—</span>'}</div>
      <div class="bloco barras"><h3>De onde vieram as frentes da coluna nova (tipo que tinham na v1)</h3>${Object.entries(moveram).sort((a, b) => b[1] - a[1]).map(([k, q], i, arr) => `<div class="ln"><span>${esc(k)}</span><span class="tr"><i style="width:${Math.round((q / arr[0][1]) * 100)}%"></i></span><span class="num">${n0(q)}</span></div>`).join('')}<p class="mfraco" style="margin-top:6px">O histórico inteiro foi reclassificado na v2. A v1 continua guardada.</p></div>
      <p><button data-set="v=1" data-go="mapa">← mapa na v1</button> <button class="lig" data-set="v=2" data-go="mapa">Ver o mapa na v2 →</button></p>`;
    const T = D.tax[2];
    const vig = `<h2>Versão 2 (vigente) · só leitura</h2>
      <div class="bloco"><h3>Tipo › subtipo</h3>${Object.entries(T.tipos).map(([t, o]) => `<p><b>${esc(t)}</b>${novo.includes(t) ? ' <span class="tag llm">nova na v2</span>' : ''}<br><span class="fraco">${esc(o.descricao)}</span><br><span class="mfraco">${Object.keys(o.subtipos).map(esc).join(' · ')}</span></p>`).join('')}</div>
      <div class="bloco"><h3>Área › time (organograma, escrito por nós)</h3>${Object.entries(D.organograma).map(([a, ts]) => `<p><b>${esc(a)}</b> <span class="mfraco">${ts.map(esc).join(' · ')}</span></p>`).join('')}</div>
      <div class="bloco"><h3>Causa raiz</h3>${Object.entries(T.causas).map(([k, d]) => `<p><b>${esc(k)}</b> <span class="fraco">${esc(d)}</span></p>`).join('')}</div>
      <div class="bloco"><h3>Problemas</h3>${Object.entries(T.problemas).map(([k, d]) => `<p><a data-lista-problema="${esc(k)}"><b>${esc(k)}</b></a> <span class="fraco">${esc(d)}</span></p>`).join('')}</div>
      <div class="bloco"><h3>Régua de severidade</h3><ol>${T.regua_sev.map(x => `<li>${esc(x)}</li>`).join('')}</ol><h3>Régua de impacto esperado</h3><ol>${T.regua_imp.map(x => `<li>${esc(x)}</li>`).join('')}</ol><h3>Urgência</h3><p>${esc(T.urgencia)}</p></div>`;
    return `<div class="tax"><div class="hist"><h3>Histórico</h3>
        <div class="it ${S.tax === 'diff' ? 'at' : ''}" data-set="tax=diff"><b>Revisão → v2</b><div class="mfraco">${dmaa(R.t)} · gatilho: sinal de encaixe</div></div>
        <div class="it"><b>Revisão mensal</b><div class="mfraco">${dmaa(R.t - 30 * DIA)} · sem mudança</div></div>
        <div class="it"><b>Descoberta → v1</b><div class="mfraco">${dmaa(R.t - 91 * DIA)} · ${tipos(1).length} tipos</div></div>
        <h3 style="margin-top:14px">Versão</h3><div class="it ${S.tax === 'vigente' ? 'at' : ''}" data-set="tax=vigente"><b>v2 vigente</b><div class="mfraco">dimensões e valores</div></div>
        <p style="margin-top:14px"><button class="mini" data-dica="No PoC o botão chama a LLM (20 a 45 s). Fora do roteiro da demo." disabled>Revisar a taxonomia agora</button></p></div>
      <div>${S.tax === 'diff' ? diff : vig}</div></div>`;
  }

  // ---- cascas: é aqui que as variantes discordam
  function topo() {
    const it = (r, n) => `<a class="${S.rota === r ? 'at' : ''}" data-go="${r}">${n}</a>`;
    return `<div class="topo"><span class="marca">frentes-engenharia</span><nav>${it('mapa', 'Mapa de calor')}${it('frentes', 'Frentes')}${it('taxonomia', 'Taxonomia')}</nav>
      <div class="dir"><span class="mfraco">Aurora Tech · dados fictícios · taxonomia v${S.v}${S.v === 2 ? ' (vigente)' : ''}</span><button class="pri" data-go="relatar">Relatar uma frente</button></div></div>
      <div class="aviso-amostra">Protótipo: amostra de ${D.frentes.filter(f => !f.aoVivo).length} frentes com peso, para o índice ter a ordem de grandeza da seed inteira (~6 mil). Frente ao vivo vale 1. Textos do painel escritos à mão.</div>`;
  }
  function painelInteiro(P) { return P.cab + P.blocos.porque + P.blocos.sug + P.blocoEnd + P.blocos.evol + P.blocos.comp + P.blocos.probs + P.blocos.frentes; }
  function cascaA() {
    let corpo;
    if (S.rota === 'frentes') corpo = telaLista(); else if (S.rota === 'taxonomia') corpo = telaTaxonomia();
    else corpo = `<div class="dupla ${S.cel ? 'aberta' : ''}"><div>${telaMapa()}</div>${S.cel ? `<div class="lateral painel"><button class="mini fechar" data-act="fecha-cel">fechar ✕</button>${painelInteiro(painelCelula())}</div>` : ''}</div>`;
    const gav = S.frente ? `<div class="fundo-gaveta" data-act="fecha-frente"></div><div class="gaveta"><button class="mini fechar" data-act="fecha-frente">fechar ✕</button><h3>Frente</h3>${telaFrente()}</div>`
      : S.rota === 'relatar' ? `<div class="gaveta estreita"><button class="mini fechar" data-go="mapa">fechar ✕</button>${telaRelato()}</div>` : '';
    return topo() + `<div class="pagina">${corpo}</div>` + gav;
  }
  function cascaB() {
    let trilha = '', corpo;
    const base = S.rota === 'frentes' ? ['frentes', 'Frentes'] : S.rota === 'taxonomia' ? ['taxonomia', 'Taxonomia'] : S.rota === 'relatar' ? ['relatar', 'Relatar'] : ['mapa', 'Mapa de calor'];
    if (S.frente) { trilha = `<a data-act="fecha-frente-e-cel">${base[1]}</a>${S.cel && S.rota === 'mapa' ? ` › <a data-act="fecha-frente">${esc(S.cel.replace('|', ' × '))}</a>` : ''} › Frente ${esc(S.frente)}`; corpo = telaFrente(); }
    else if (S.rota === 'mapa' && S.cel) { trilha = `<a data-act="fecha-cel">Mapa de calor</a> › ${esc(S.cel.replace('|', ' × '))}`; const P = painelCelula(); corpo = `<div class="painel" style="max-width:980px">${painelInteiro(P)}</div>`; }
    else corpo = S.rota === 'frentes' ? telaLista() : S.rota === 'taxonomia' ? telaTaxonomia() : S.rota === 'relatar' ? telaRelato() : telaMapa();
    return topo() + `<div class="pagina">${trilha ? `<div class="trilha">${trilha}</div>` : ''}${corpo}</div>`;
  }
  function cascaC() {
    let corpo;
    if (S.rota === 'frentes') corpo = telaLista(); else if (S.rota === 'taxonomia') corpo = telaTaxonomia();
    else { let baixo = ''; if (S.cel) { const P = painelCelula();
        baixo = `<div class="painel painel-baixo" id="baixo"><button class="mini fechar" data-act="fecha-cel">fechar ✕</button>${P.cab}<div class="cols"><div>${P.blocos.porque}${P.blocos.sug}${P.blocoEnd}</div><div>${P.blocos.evol}${P.blocos.probs}${P.blocos.comp}</div><div>${P.blocos.frentes}</div></div></div>`; }
      corpo = telaMapa() + baixo; }
    const jan = S.frente ? `<div class="fundo-gaveta" data-act="fecha-frente"></div><div class="janela"><button class="mini fechar" data-act="fecha-frente">fechar ✕</button><h3>Frente</h3>${telaFrente()}</div>`
      : S.rota === 'relatar' ? `<div class="fundo-gaveta" data-go="mapa"></div><div class="janela"><button class="mini fechar" data-go="mapa">fechar ✕</button>${telaRelato()}</div>` : '';
    return topo() + `<div class="pagina">${corpo}</div>` + jan;
  }

  // ---- roteiro da demo (#21): cada passo leva à tela que ele usa
  const H1 = 'Originação|Disponibilidade e Performance', H3 = 'Pós-venda e Cobrança|Integridade e Consistência de Dados';
  const base = () => Object.assign(S, { rota: 'mapa', visao: 'dor', periodo: 90, v: 2, cel: null, frente: null, vf: null, endForm: null, origens: [] });
  const PASSOS = [
    ['livre', () => {}],
    ['1 · mapa, “Onde dói”, 90 dias', () => base()],
    ['2 · painel da célula da H1', () => { base(); S.cel = H1; }],
    ['3 · mapa, “Onde há oportunidade”', () => { base(); S.visao = 'op'; }],
    ['4 · formulário de relato', () => { base(); S.rota = 'relatar'; S.relato = { rascunho: PREPARADO }; }],
    ['5 · mapa + rajada (botão ao lado)', () => base()],
    ['6a · revisão: mapa na v1 com o selo', () => { base(); S.v = 1; }],
    ['6b · revisão: o diff', () => { base(); S.rota = 'taxonomia'; S.tax = 'diff'; }],
    ['6c · revisão: mapa na v2', () => base()],
    ['7 · 12 meses, célula da H3', () => { base(); S.periodo = 365; S.cel = H3; }],
    ['8 · Top 1, endereçar ao vivo', () => { base(); const t = agrega(2, 'dor', 90, true).top[0]; S.cel = t && t[0]; S.endForm = 0; }],
  ];
  function barra() {
    return `<div class="barra-proto"><span>PROTÓTIPO #22</span><span class="sep"></span><button data-var="-1">←</button><b>${variante} — ${VARIANTES[variante]}</b><button data-var="1">→</button><span class="sep"></span>
      <button data-passo="-1">◀</button><span class="pas">Roteiro: ${PASSOS[S.passo][0]}</span><button data-passo="1">▶</button><span class="sep"></span>
      <button data-act="rajada">Simular a rajada</button><button data-act="relato-vago" title="preenche um relato vago no formulário">Relato vago</button><button data-act="zerar">Zerar</button></div>`;
  }

  // ---- desenho e eventos
  const antes = {};
  function desenha() {
    const y = window.scrollY, lat = document.querySelector('.lateral, .gaveta, .janela'), ly = lat ? lat.scrollTop : 0;
    document.body.className = 'v' + variante;
    document.getElementById('app').innerHTML = (variante === 'A' ? cascaA : variante === 'B' ? cascaB : cascaC)() + barra();
    const lat2 = document.querySelector('.lateral, .gaveta, .janela'); if (lat2) lat2.scrollTop = ly;
    window.scrollTo(0, y);
    document.querySelectorAll('[data-anima]').forEach(el => { const k = S.visao + S.periodo + S.v + el.dataset.anima, fim = +el.textContent.replace(/\./g, ''), ini = antes[k];
      antes[k] = fim; if (ini == null || ini === fim || !S.pisca[el.dataset.anima]) return; const t0 = performance.now();
      (function passo(t) { const p = Math.min(1, (t - t0) / 700); el.textContent = n0(ini + (fim - ini) * p); if (p < 1) requestAnimationFrame(passo); })(t0); });
    const u = new URL(location.href); u.searchParams.set('variant', variante);
    u.hash = '#/' + S.rota + (S.cel ? '?cel=' + encodeURIComponent(S.cel) : ''); try { history.replaceState(null, '', u); } catch (e) { /* file:// em alguns navegadores */ }
  }
  function abreCel(k, visao) { S.rota = 'mapa'; S.cel = k; if (visao) S.visao = visao; S.endForm = null; S.frente = null; }
  function rajada() {
    S.rota = 'mapa'; S.frente = null; let i = 0;
    const iv = setInterval(() => { const r = D.rajada[i++]; if (!r) { clearInterval(iv); return; }
      const f = entraFrente('webhook', r.emissor, r.texto, { ref_externa: 'rajada:' + Date.now() + ':' + i });
      const c = classificaDuble(f.texto, 'webhook'); if (/propost|infra-e-cloud/.test(f.texto) && c.tipo === 'Disponibilidade e Performance') { c.area = c.jev_area = 'Originação'; c.time = 'Proposta'; }
      f.c = { 1: c, 2: c }; const k = chave(c.area, c.tipo); S.pisca[k] = (S.pisca[k] || 0) + 1; S.atualizando[k] = true;
      clearTimeout(rajada['t' + k]); rajada['t' + k] = setTimeout(() => { delete S.pisca[k]; delete S.atualizando[k]; desenha(); }, 5000); desenha(); }, 420);
  }
  document.addEventListener('click', ev => {
    const el = ev.target.closest('[data-go],[data-set],[data-cel],[data-frente],[data-act],[data-origem],[data-var],[data-passo],[data-lista-cel],[data-lista-estado],[data-lista-problema],[data-limpa],[data-abre-cel]');
    if (!el || el.disabled) return; const d = el.dataset;
    if (d.set) { const [k, val] = d.set.split('='); S[k] = /^\d+$/.test(val) ? +val : val; }
    if (d.go) { S.rota = d.go; S.frente = null; if (d.go !== 'mapa') S.cel = null; if (d.go === 'relatar' && !(S.relato && S.relato.fase)) S.relato = S.relato || null; }
    if (d.cel) { abreCel(d.cel); if (variante === 'C') setTimeout(() => { const b = document.getElementById('baixo'); if (b) b.scrollIntoView({ behavior: 'smooth' }); }, 30); }
    if (d.abreCel) { abreCel(d.soMapa ? null : d.abreCel, d.visao); if (d.soMapa) { S.pisca[d.abreCel] = S.pisca[d.abreCel] || 1; setTimeout(() => { delete S.pisca[d.abreCel]; }, 3200); } }
    if (d.frente) { S.frente = d.frente; S.vf = null; }
    if (d.origem) { S.origens = S.origens.includes(d.origem) ? S.origens.filter(o => o !== d.origem) : S.origens.concat(d.origem); }
    if (d.var) { const ks = Object.keys(VARIANTES); variante = ks[(ks.indexOf(variante) + +d.var + ks.length) % ks.length]; }
    if (d.passo) { S.passo = (S.passo + +d.passo + PASSOS.length) % PASSOS.length; PASSOS[S.passo][1](); }
    const paraLista = extra => { S.rota = 'frentes'; S.frente = null; S.cel = null; Object.assign(S.lista, { cel: null, problema: '', estado: '', natureza: '', origem: '', busca: '', periodo: S.periodo }, extra); };
    if (d.listaCel) paraLista({ cel: d.listaCel });
    if (d.listaEstado) paraLista({ estado: d.listaEstado });
    if (d.listaProblema) paraLista({ problema: d.listaProblema });
    if (d.limpa) S.lista[d.limpa] = d.limpa === 'cel' ? null : '';
    const a = d.act;
    if (a === 'fecha-cel') { S.cel = null; S.endForm = null; }
    if (a === 'fecha-frente') S.frente = null;
    if (a === 'fecha-frente-e-cel') { S.frente = null; S.cel = null; }
    if (a === 'endform') S.endForm = +d.i;
    if (a === 'endcancel') S.endForm = null;
    if (a === 'enderecar') { const [area, tipo] = S.cel.split('|'); D.enderecamentos.push({ area, tipo, visao: S.visao, t: Date.now(), texto: document.getElementById('end-texto').value, solucao: d.sol, quem: document.getElementById('end-quem').value, procedencia: 'tela', ativo: true }); S.endForm = null; }
    if (a === 'desfazer') { const [area, tipo] = S.cel.split('|'); const e = enderecamento(area, tipo, S.visao, S.v); if (e) e.ativo = false; }
    if (a === 'enviar-relato') { const tx = document.getElementById('rel-texto').value.trim(); if (!tx) return;
      const f = entraFrente('relato', document.getElementById('rel-emissor').value.split(' — ')[0], tx); S.relato = { fase: 'classificando', id: f.id, rascunho: tx };
      setTimeout(() => { classificaEPisca(f); S.relato = { fase: 'pronta', id: f.id, rascunho: '' }; desenha(); }, 1100); }
    if (a === 'completar') { const f = PORID[d.id || S.frente], tx = document.getElementById('comp-texto').value.trim(); if (!tx) return; f.complemento = tx; f.complementado_em = Date.now(); classificaEPisca(f); if (S.relato) S.relato = { fase: 'pronta', id: f.id, rascunho: '' }; }
    if (a === 'novo-relato') S.relato = null;
    if (a === 'relato-vago') { S.rota = 'relatar'; S.frente = null; S.relato = { rascunho: VAGO }; }
    if (a === 'rajada') rajada();
    if (a === 'zerar') { D.frentes = D.frentes.filter(f => !f.aoVivo); D.enderecamentos = D.enderecamentos.filter(e => e.procedencia !== 'tela'); D.enderecamentos.forEach(e => { e.ativo = true; }); S.relato = null; S.pisca = {}; S.atualizando = {}; S.passo = 0; base(); }
    desenha();
  });
  document.addEventListener('change', ev => { const c = ev.target.dataset.lista; if (c) { S.lista[c] = ev.target.value; desenha(); } });
  document.addEventListener('keydown', ev => {
    if (ev.target.matches('input, textarea, select, [contenteditable]')) return;
    if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') { const ks = Object.keys(VARIANTES); variante = ks[(ks.indexOf(variante) + (ev.key === 'ArrowRight' ? 1 : -1) + ks.length) % ks.length]; desenha(); }
    if (ev.key === 'Escape') { if (S.frente) S.frente = null; else S.cel = null; desenha(); }
  });
  const dica = document.getElementById('dica');
  document.addEventListener('mousemove', ev => { const el = ev.target.closest && ev.target.closest('[data-dica]');
    if (!el) { dica.hidden = true; return; } dica.hidden = false; dica.textContent = el.dataset.dica; dica.style.left = Math.min(ev.clientX + 14, window.innerWidth - 300) + 'px'; dica.style.top = ev.clientY + 16 + 'px'; });
  window.__proto = { S, agrega, desenha, PASSOS };
  desenha();
})();

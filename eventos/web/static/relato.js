// Medidor de concretude e contador do relato (fase 4a do #116). É só dica, calculada aqui no
// navegador com heurísticas simples: quem decide se o relato pinta o mapa é a pergunta de controle
// do Jev, no servidor. Sem este arquivo o formulário funciona igual, só sem o medidor.
(function () {
  "use strict";
  var CHECKS = {
    sistema: /\b(sistemas?|tela|telas|rotina|rotinas|api|app|portal|servi[cç]os?|fila|job|painel|m[oó]dulo|relat[oó]rio|banco|integra[cç][aã]o|plataforma|site|fornecedor|planilha|boleto|contrato|cadastro)\b/i,
    numero: /\d/,
    efeito: /(n[aã]o consegue|n[aã]o abre|n[aã]o carrega|travou|trava|caiu|fora do ar|erro|falh|lent|demor|atras|perd|bloque|parou|indispon|quebr|duplic|incorret|errad|reprov|nega)/i,
    afetado: /\b(clientes?|usu[aá]rios?|time|times|equipe|analistas?|opera[cç][aã]o|atendimento|vendas|financeiro|cobran[cç]a|parceiros?|todos|ningu[eé]m|gerentes?|vendedores?|corretores?)\b/i
  };
  var ROTULOS = ["vago", "vago", "razoável", "bom", "ótimo"];

  function atualizar(area) {
    var texto = area.value;
    var form = area.form;
    var medidor = form.querySelector("[data-medidor]");
    var contador = form.querySelector("[data-contador]");
    if (contador) {
      contador.hidden = false;
      contador.textContent = texto.length + " / " + area.maxLength;
    }
    if (!medidor) { return; }
    medidor.hidden = false;
    var ok = 0;
    Object.keys(CHECKS).forEach(function (nome) {
      var passou = CHECKS[nome].test(texto);
      var item = medidor.querySelector('[data-check="' + nome + '"]');
      if (item) { item.toggleAttribute("data-ok", passou); }
      if (passou) { ok += 1; }
    });
    var vazio = texto.trim() === "";
    var fraco = !vazio && ok <= 1;
    medidor.setAttribute("data-nivel", vazio ? "0" : String(Math.max(ok, 1)));
    medidor.toggleAttribute("data-fraco", fraco);
    var rotulo = medidor.querySelector("[data-medidor-rotulo]");
    if (rotulo) { rotulo.textContent = vazio ? "" : ROTULOS[ok]; }
    var aviso = medidor.querySelector("[data-medidor-aviso]");
    if (aviso) { aviso.hidden = !fraco; }
  }

  function iniciar() {
    var area = document.querySelector("#gaveta [data-texto]");
    if (area) { atualizar(area); }
  }

  document.addEventListener("input", function (e) {
    if (e.target && e.target.matches && e.target.matches("[data-texto]")) { atualizar(e.target); }
  });
  // Esc fecha a gaveta e volta ao mapa
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") { return; }
    var fechar = document.querySelector("#gaveta [data-fechar]");
    if (fechar) { window.location.href = fechar.getAttribute("href"); }
  });
  document.addEventListener("htmx:afterSwap", iniciar);
  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", iniciar); } else { iniciar(); }
})();

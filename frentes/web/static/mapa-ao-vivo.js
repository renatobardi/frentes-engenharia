// O número da célula que mudou conta do valor anterior até o novo (spec 10). O servidor já
// pôs o texto final no elemento; aqui só se anima. Sem JavaScript fica o valor novo.
(function () {
  var DURACAO = 900;

  function numero(texto) {
    return parseFloat(String(texto).replace(",", "."));
  }

  function formatar(valor) {
    // a mesma regra do servidor: inteiro a partir de 10, uma casa abaixo
    if (valor >= 10) return String(Math.round(valor));
    return valor.toFixed(1).replace(".", ",").replace(/,0$/, "");
  }

  function contar(elemento) {
    var de = numero(elemento.dataset.de);
    var para = numero(elemento.dataset.para);
    var final = elemento.textContent;
    if (isNaN(de) || isNaN(para)) return;
    var inicio = null;
    function passo(agora) {
      if (inicio === null) inicio = agora;
      var t = Math.min(1, (agora - inicio) / DURACAO);
      elemento.textContent = t < 1 ? formatar(de + (para - de) * t) : final;
      if (t < 1) window.requestAnimationFrame(passo);
    }
    elemento.textContent = formatar(de);
    window.requestAnimationFrame(passo);
  }

  // O polling não troca o painel enquanto se edita o endereçamento (formulário aberto ou foco
  // num campo dele): senão o texto digitado se perderia a cada leitura.
  function editandoOEnderecamento() {
    var painel = document.getElementById("painel");
    if (!painel) return false;
    if (painel.querySelector("details.enderecar[open]")) return true;
    return painel.contains(document.activeElement) &&
      /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
  }

  document.addEventListener("htmx:oobBeforeSwap", function (evento) {
    var alvo = evento.detail.target;
    if (alvo && alvo.id === "painel" && editandoOEnderecamento()) evento.preventDefault();
  });

  // Recusa do POST sem tela em HTML (403, 404, 413, ...): a mensagem aparece no aviso do mapa.
  document.addEventListener("htmx:beforeSwap", function (evento) {
    var xhr = evento.detail.xhr;
    var caminho = evento.detail.requestConfig && evento.detail.requestConfig.path || "";
    if (xhr.status < 400 || caminho.indexOf("/mapa/") !== 0 || caminho.indexOf("/mapa/ao-vivo") === 0) return;
    // 404, 409 e 422 em HTML são a tela do mapa com a mensagem no painel: o HTMX a troca
    if ((xhr.getResponseHeader("Content-Type") || "").indexOf("text/html") === 0 &&
        [404, 409, 422].indexOf(xhr.status) >= 0) {
      evento.detail.shouldSwap = true;
      evento.detail.isError = false;
      return;
    }
    var aviso = document.getElementById("aviso-enderecar");
    var texto = "Não foi possível concluir (código " + xhr.status + ").";
    try { var d = JSON.parse(xhr.responseText).detail; if (typeof d === "string") texto = d; } catch (e) {}
    if (aviso) { aviso.textContent = texto; aviso.hidden = false; }
    evento.detail.shouldSwap = false;
    evento.detail.isError = false;
  });

  document.addEventListener("htmx:load", function (evento) {
    var raiz = evento.detail.elt;
    if (!raiz || !raiz.querySelectorAll) return;
    raiz.querySelectorAll("[data-de][data-para]").forEach(contar);
  });
})();

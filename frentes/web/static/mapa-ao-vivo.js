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

  document.addEventListener("htmx:load", function (evento) {
    var raiz = evento.detail.elt;
    if (!raiz || !raiz.querySelectorAll) return;
    raiz.querySelectorAll("[data-de][data-para]").forEach(contar);
  });
})();

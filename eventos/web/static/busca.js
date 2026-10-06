// A paleta da busca (#119): abre pelo botão e por ⌘K / Ctrl+K, fecha com Esc (o <dialog> trata) ou
// clicando fora, e as setas andam pelos resultados. Os resultados vêm do servidor, pelo HTMX.
(function () {
  "use strict";
  var caixa = document.getElementById("busca");
  if (!caixa) return;
  var campo = document.getElementById("busca-campo");
  var botoes = document.querySelectorAll("[data-busca-abrir]");
  var mac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");

  botoes.forEach(function (b) { b.hidden = false; });
  document.querySelectorAll("[data-busca-atalho]").forEach(function (k) {
    k.textContent = mac ? "⌘K" : "Ctrl K";
  });

  function aberta() { return caixa.hasAttribute("open"); }

  function abrir() {
    if (aberta()) return;
    if (typeof caixa.showModal === "function") caixa.showModal(); else caixa.setAttribute("open", "");
    campo.focus();
    campo.select();
    // a paleta sem consulta mostra as ações
    if (window.htmx) window.htmx.trigger(campo, "busca-abriu");
  }

  function fechar() {
    if (!aberta()) return;
    if (typeof caixa.close === "function") caixa.close(); else caixa.removeAttribute("open");
  }

  function itens() { return Array.prototype.slice.call(caixa.querySelectorAll("[data-busca-item]")); }

  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("[data-busca-abrir]")) { e.preventDefault(); abrir(); return; }
    if (e.target === caixa) fechar();  // o clique no fundo escurecido
  });

  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && !e.altKey && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      if (aberta()) fechar(); else abrir();
      return;
    }
    if (!aberta()) return;
    if (e.key === "Escape") { e.preventDefault(); fechar(); return; }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "Enter") return;
    var lista = itens();
    if (!lista.length) return;
    var i = lista.indexOf(document.activeElement);
    if (e.key === "Enter") {
      if (i < 0) { e.preventDefault(); lista[0].click(); }  // no campo: o primeiro resultado
      return;
    }
    e.preventDefault();
    if (e.key === "ArrowDown") lista[Math.min(i + 1, lista.length - 1)].focus();
    else if (i <= 0) campo.focus();
    else lista[i - 1].focus();
  });
})();

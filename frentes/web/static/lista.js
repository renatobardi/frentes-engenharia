/* Lista de frentes: marca a linha da prévia aberta e fecha a prévia. Sem biblioteca. */
(function () {
  "use strict";

  function marcar(id) {
    document.querySelectorAll("#lista tr[data-id]").forEach(function (tr) {
      var ligada = id !== null && tr.getAttribute("data-id") === id;
      tr.classList.toggle("linha-sel", ligada);
      if (ligada) tr.setAttribute("aria-selected", "true");
      else tr.removeAttribute("aria-selected");
    });
  }

  function fechar() {
    var previa = document.getElementById("previa");
    if (previa) previa.replaceChildren();
    marcar(null);
  }

  document.addEventListener("htmx:afterSwap", function (e) {
    var alvo = e.detail.target;
    if (!alvo || alvo.id !== "previa") return;
    var corpo = alvo.querySelector("[data-previa-id]");
    marcar(corpo ? corpo.getAttribute("data-previa-id") : null);
  });

  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-fechar-previa]")) return fechar();
    // a linha inteira abre a prévia; link, botão e campo fazem o que já fazem
    var tr = e.target.closest("#lista tr[data-id]");
    if (!tr || e.target.closest("a, button, input, select, label")) return;
    var botao = tr.querySelector("button[hx-get]");
    if (botao) botao.click();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") fechar();
  });
})();

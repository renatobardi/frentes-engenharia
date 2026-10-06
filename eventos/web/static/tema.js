/* O tema escuro (#120). A escolha fica no navegador (localStorage, chave "tema"), como a dispensa do
   passeio guiado: o endereço guarda a visão do mapa, não o gosto de quem olha. Sem escolha, claro.
   Este arquivo roda no <head>, sem defer, para marcar <html data-tema> antes da primeira pintura. */
(function () {
  var CHAVE = "tema";
  var raiz = document.documentElement;

  function lido() {
    try { return localStorage.getItem(CHAVE) === "escuro" ? "escuro" : "claro"; } catch (e) { return "claro"; }
  }
  function aplicar(tema) {
    if (tema === "escuro") raiz.setAttribute("data-tema", "escuro"); else raiz.removeAttribute("data-tema");
    var botao = document.querySelector("[data-tema-botao]");
    if (botao) {
      botao.hidden = false;
      botao.setAttribute("aria-pressed", tema === "escuro" ? "true" : "false");
      botao.title = tema === "escuro" ? "Voltar ao tema claro" : "Tema escuro";
      botao.setAttribute("aria-label", botao.title);
    }
  }
  aplicar(lido());
  document.addEventListener("DOMContentLoaded", function () { aplicar(lido()); });
  document.addEventListener("click", function (e) {
    if (!e.target.closest || !e.target.closest("[data-tema-botao]")) return;
    var novo = raiz.getAttribute("data-tema") === "escuro" ? "claro" : "escuro";
    try { localStorage.setItem(CHAVE, novo); } catch (err) { /* a escolha vale só nesta página */ }
    aplicar(novo);
  });
})();

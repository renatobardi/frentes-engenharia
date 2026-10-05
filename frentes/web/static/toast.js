// Toast pill do mapa (spec 10): "Endereçado", "Endereçamento desfeito" e "Link copiado", 2,6 s.
// O painel carrega este arquivo e o HTMX o executa de novo a cada troca; o guarda abaixo evita
// registrar os ouvintes duas vezes. O toast mora fora do painel (no body): sobrevive à troca.
(function () {
  if (window.__toastDoMapa) return;
  window.__toastDoMapa = true;

  var DURACAO = 2600;
  var temporizador = null;

  function elemento() {
    var t = document.getElementById("toast");
    if (t) return t;
    t = document.createElement("div");
    t.id = "toast";
    t.className = "toast";
    t.setAttribute("role", "status");
    t.setAttribute("aria-live", "polite");
    t.hidden = true;
    document.body.appendChild(t);
    return t;
  }

  function mostrar(texto) {
    var t = elemento();
    t.textContent = texto;
    t.hidden = false;
    // reinicia a animação de entrada quando um toast vem logo depois de outro
    t.classList.remove("toast-entra");
    void t.offsetWidth;
    t.classList.add("toast-entra");
    window.clearTimeout(temporizador);
    temporizador = window.setTimeout(function () { t.hidden = true; }, DURACAO);
  }
  window.mostrarToast = mostrar;

  // endereçar e desfazer: o toast sai quando o servidor aceita (2xx); a recusa mostra a mensagem
  // no próprio painel
  document.addEventListener("htmx:afterRequest", function (evento) {
    var d = evento.detail;
    var caminho = d.requestConfig && d.requestConfig.path || "";
    if (!d.successful || !d.requestConfig || d.requestConfig.verb !== "post") return;
    if (caminho.indexOf("/mapa/enderecar") === 0) mostrar("Célula endereçada");
    else if (caminho.indexOf("/mapa/desfazer") === 0) mostrar("Endereçamento desfeito");
  });

  function copiarTexto(texto) {
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(texto);
    return new Promise(function (ok, falha) {
      var campo = document.createElement("textarea");
      campo.value = texto;
      campo.setAttribute("readonly", "");
      campo.style.position = "fixed";
      campo.style.opacity = "0";
      document.body.appendChild(campo);
      campo.select();
      var copiou = false;
      try { copiou = document.execCommand("copy"); } catch (e) {}
      document.body.removeChild(campo);
      return copiou ? ok() : falha(new Error("sem cópia"));
    });
  }

  document.addEventListener("click", function (evento) {
    var alvo = evento.target && evento.target.closest ? evento.target.closest("[data-copiar-link], [data-cancelar]") : null;
    if (!alvo) return;
    if (alvo.hasAttribute("data-cancelar")) {
      var detalhes = alvo.closest("details");
      if (detalhes) detalhes.open = false;
      return;
    }
    // o endereço da tela já leva visão, período, origem, versão e célula (spec 10)
    copiarTexto(window.location.href).then(
      function () { mostrar("Link copiado"); },
      function () { mostrar("Não foi possível copiar o link"); }
    );
  });
})();

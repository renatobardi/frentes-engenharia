// O passeio guiado do mapa (#139). Os passos e os textos vêm do servidor (`mapa/guia.html`); aqui
// ficam a posição do balão, o destaque do alvo, o teclado e a memória. A dispensa é guardada no
// navegador (localStorage): sem ele (aba anônima, bloqueio) o passeio só volta a abrir sozinho.
// O HTMX troca o `#mapa` inteiro (filtro) e o Top 3, a grade e os contadores (polling): o alvo é
// procurado de novo a cada posicionamento, nunca guardado.
(function () {
  var CHAVE = "frentes.guia.mapa.v1";
  var FOLGA = 6;    // entre o alvo e a borda do destaque
  var MARGEM = 12;  // entre o destaque e o balão, e entre o balão e a janela
  var CABECALHO = 64;  // o cabeçalho fixo cobre o topo da janela

  var guia = document.getElementById("guia");
  var destaque = document.getElementById("guia-destaque");
  if (!guia || !destaque) return;
  // como o toast, os dois moram no body: dentro do `main` um ancestral desloca o `position: fixed`
  document.body.appendChild(destaque);
  document.body.appendChild(guia);

  var conta = guia.querySelector("[data-guia-conta]");
  var titulo = document.getElementById("guia-titulo");
  var texto = document.getElementById("guia-texto");
  var voltar = guia.querySelector("[data-guia-voltar]");
  var proximo = guia.querySelector("[data-guia-proximo]");
  var passos = Array.prototype.slice.call(guia.querySelectorAll(".guia-passos > li"));

  var visiveis = [];  // os passos com alvo na tela, fixados ao abrir
  var atual = 0;
  var aberto = false;
  var quemAbriu = null;
  var engolirEsc = false;

  function jaViu() {
    try { return window.localStorage.getItem(CHAVE) === "1"; } catch (e) { return false; }
  }
  function lembrar() {
    try { window.localStorage.setItem(CHAVE, "1"); } catch (e) {}
  }

  function naTela(el) {
    if (!el) return false;
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }

  // inteiro na janela, com folga para o cabeçalho fixo em cima
  function aVista(el) {
    var r = el.getBoundingClientRect();
    return r.top >= CABECALHO && r.bottom <= window.innerHeight - MARGEM &&
      r.left >= MARGEM && r.right <= window.innerWidth - MARGEM;
  }

  function alvoDe(passo) {
    var seletor = passo.getAttribute("data-alvo");
    var pelo = passo.getAttribute("data-alvo-pelo-link-de");
    if (pelo) {
      var origem = document.querySelector(pelo);
      var href = origem && origem.getAttribute("href");
      var candidatos = document.querySelectorAll(seletor);
      for (var i = 0; href && i < candidatos.length; i++) {
        if (candidatos[i].getAttribute("href") === href && naTela(candidatos[i])) return candidatos[i];
      }
    }
    var el = document.querySelector(seletor);
    return naTela(el) ? el : null;
  }

  function limitar(valor, minimo, maximo) {
    return Math.max(minimo, Math.min(valor, Math.max(minimo, maximo)));
  }

  function posicionar() {
    if (!aberto) return;
    var alvo = alvoDe(visiveis[atual]);
    if (!alvo) {
      // o alvo sumiu numa troca (ex.: o recorte ficou sem Top 3): segue com os que restam
      var passo = visiveis[atual];
      visiveis = visiveis.filter(alvoDe);
      if (!visiveis.length) return fechar(false);
      atual = Math.min(visiveis.indexOf(passo) < 0 ? atual : visiveis.indexOf(passo), visiveis.length - 1);
      return mostrar(false);
    }
    var r = alvo.getBoundingClientRect();
    var largura = window.innerWidth, altura = window.innerHeight;
    destaque.style.top = (r.top - FOLGA) + "px";
    destaque.style.left = (r.left - FOLGA) + "px";
    destaque.style.width = (r.width + 2 * FOLGA) + "px";
    destaque.style.height = (r.height + 2 * FOLGA) + "px";

    var b = guia.getBoundingClientRect();
    var abaixo = r.bottom + FOLGA + MARGEM;
    var acima = r.top - FOLGA - MARGEM - b.height;
    var topo = abaixo + b.height <= altura - MARGEM ? abaixo : (acima >= MARGEM ? acima : altura - b.height - MARGEM);
    guia.style.top = limitar(topo, MARGEM, altura - b.height - MARGEM) + "px";
    guia.style.left = limitar(r.left + r.width / 2 - b.width / 2, MARGEM, largura - b.width - MARGEM) + "px";
  }

  function mostrar(rolar) {
    var passo = visiveis[atual];
    var ultimo = atual === visiveis.length - 1;
    conta.textContent = (atual + 1) + " de " + visiveis.length;
    titulo.textContent = passo.getAttribute("data-titulo");
    texto.textContent = passo.textContent;
    voltar.hidden = atual === 0;
    proximo.textContent = ultimo ? "Concluir" : "Próximo";
    guia.hidden = false;
    destaque.hidden = false;
    var alvo = alvoDe(passo);
    if (rolar && alvo && alvo.scrollIntoView && !aVista(alvo)) {
      // o alvo pode estar abaixo da dobra, sob o cabeçalho fixo ou fora da rolagem da grade
      alvo.scrollIntoView({ block: "center", inline: "nearest" });
    }
    posicionar();
  }

  function abrir(origem) {
    visiveis = passos.filter(alvoDe);
    if (!visiveis.length) return;
    atual = 0;
    aberto = true;
    quemAbriu = origem || null;
    mostrar(true);
    proximo.focus();
  }

  function fechar(devolverFoco) {
    aberto = false;
    guia.hidden = true;
    destaque.hidden = true;
    lembrar();
    if (devolverFoco !== false && quemAbriu && quemAbriu.focus) quemAbriu.focus();
  }

  function ir(delta) {
    var novo = atual + delta;
    if (novo >= visiveis.length) return fechar();
    if (novo < 0) return;
    atual = novo;
    mostrar(true);
  }

  document.addEventListener("click", function (evento) {
    var alvo = evento.target && evento.target.closest ? evento.target.closest("[data-guia-abrir], [data-guia-pular], [data-guia-voltar], [data-guia-proximo]") : null;
    if (!alvo) return;
    if (alvo.hasAttribute("data-guia-abrir")) abrir(alvo);
    else if (alvo.hasAttribute("data-guia-pular")) fechar();
    else if (alvo.hasAttribute("data-guia-voltar")) ir(-1);
    else ir(1);
  });

  // Esc fecha só o passeio. O painel da célula fecha no keyup do Esc (hx-trigger no body): o
  // keyup da mesma tecla é engolido antes de chegar lá.
  document.addEventListener("keydown", function (evento) {
    if (!aberto || evento.key !== "Escape") return;
    engolirEsc = true;
    evento.stopPropagation();
    fechar();
  }, true);
  document.addEventListener("keyup", function (evento) {
    if (evento.key !== "Escape" || !engolirEsc) return;
    engolirEsc = false;
    evento.stopPropagation();
  }, true);

  window.addEventListener("resize", posicionar);
  window.addEventListener("scroll", posicionar, true);
  document.addEventListener("htmx:afterSettle", posicionar);

  var auto = guia.getAttribute("data-auto");
  if (auto === "nunca") lembrar();
  else if (auto === "sim" && !jaViu()) abrir(null);
})();

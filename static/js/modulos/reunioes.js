/* Comportamento próprio do módulo reunioes. Sem script inline: inicie com htmx.onLoad.
   Título sugerido: quando a pessoa troca o tipo, o exemplo dentro do campo de título acompanha.
   Sem JavaScript, o servidor usa a mesma sugestão se o título ficar em branco. */
(function () {
  "use strict";

  function ligarSugestao(campo) {
    if (campo.dataset.sugestaoLigada) return;
    campo.dataset.sugestaoLigada = "1";
    var sugestoes;
    try { sugestoes = JSON.parse(campo.getAttribute("data-sugestoes") || "{}"); } catch (e) { return; }
    var formulario = campo.form;
    if (!formulario) return;
    var origem = formulario.querySelector('[name="' + campo.getAttribute("data-sugestao-de") + '"]');
    if (!origem) return;
    origem.addEventListener("change", function () {
      if (sugestoes[origem.value]) campo.setAttribute("placeholder", sugestoes[origem.value]);
    });
  }

  function iniciar(raiz) {
    (raiz || document).querySelectorAll("input[data-sugestoes][data-sugestao-de]").forEach(ligarSugestao);
  }

  if (window.htmx) {
    htmx.onLoad(iniciar);
  } else {
    document.addEventListener("DOMContentLoaded", function () { iniciar(document); });
  }
})();

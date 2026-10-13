/* Comportamento próprio do módulo equipe. Sem script inline: inicie com htmx.onLoad.
   - Botão "Copiar link" do link de senha: só aparece quando o aparelho deixa copiar;
     sem ele, o link continua no campo, que se seleciona inteiro ao tocar. */
(function () {
  "use strict";

  function avisar(botao, texto) {
    var aviso = document.getElementById(botao.getAttribute("data-aviso"));
    if (aviso) aviso.textContent = texto;
  }

  function iniciarCopia(botao) {
    if (botao.dataset.equipePronto) return;
    botao.dataset.equipePronto = "1";
    if (!navigator.clipboard || !window.isSecureContext) return;
    botao.hidden = false;
    botao.addEventListener("click", function (evt) {
      evt.preventDefault();
      var campo = document.getElementById(botao.getAttribute("data-copiar"));
      if (!campo) return;
      navigator.clipboard.writeText(campo.value).then(function () {
        avisar(botao, "Link copiado. Cole na conversa do WhatsApp de trabalho.");
      }, function () {
        campo.focus();
        campo.select();
        avisar(botao, "Não deu para copiar sozinho. O link está selecionado: copie pelo menu do aparelho.");
      });
    });
  }

  function iniciarSelecao(campo) {
    if (campo.dataset.equipePronto) return;
    campo.dataset.equipePronto = "1";
    campo.addEventListener("focus", function () { campo.select(); });
  }

  function iniciar(raiz) {
    var base = raiz && raiz.querySelectorAll ? raiz : document;
    base.querySelectorAll("[data-copiar]").forEach(iniciarCopia);
    base.querySelectorAll("[data-selecionar-tudo]").forEach(iniciarSelecao);
  }

  if (window.htmx) {
    htmx.onLoad(iniciar);
  } else {
    document.addEventListener("DOMContentLoaded", function () { iniciar(document); });
  }
})();

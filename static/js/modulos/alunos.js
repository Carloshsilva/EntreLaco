/* Comportamento próprio do módulo alunos. Sem script inline: inicie com htmx.onLoad.
   Tudo funciona sem JavaScript; aqui só melhoramos a experiência:
   - na tela de mudar situação, os campos de saída aparecem só quando a nova situação é "encerrado";
   - nas abas do perfil, a aba escolhida fica marcada. */
(function () {
  "use strict";

  function iniciarSituacao(form) {
    if (form.dataset.alunosPronto) return;
    form.dataset.alunosPronto = "1";
    var saida = form.querySelector("[data-so-encerrar]");
    if (!saida) return;
    function atualizar() {
      var escolhido = form.querySelector('input[name="para"]:checked');
      saida.hidden = !(escolhido && escolhido.value === "encerrado");
    }
    form.addEventListener("change", function (evt) {
      if (evt.target && evt.target.name === "para") atualizar();
    });
    atualizar();
  }

  function marcarAba(link) {
    var abas = link.closest("nav");
    if (!abas) return;
    abas.querySelectorAll("[data-aba-do-perfil]").forEach(function (aba) { aba.removeAttribute("aria-current"); });
    link.setAttribute("aria-current", "true");
  }

  document.addEventListener("click", function (evt) {
    var link = evt.target.closest ? evt.target.closest("[data-aba-do-perfil]") : null;
    if (link) marcarAba(link);
  });

  function iniciar(raiz) {
    var base = raiz || document;
    if (base.matches && base.matches("form[data-situacao-form]")) iniciarSituacao(base);
    base.querySelectorAll("form[data-situacao-form]").forEach(iniciarSituacao);
  }

  if (window.htmx) {
    htmx.onLoad(iniciar);
  } else {
    document.addEventListener("DOMContentLoaded", function () { iniciar(document); });
  }
})();

/* Comportamento próprio do módulo aulas. Sem script inline: inicie com htmx.onLoad.
   Só informa: diz quantas fotos foram escolhidas e avisa quando passam do limite por envio.
   Não mexe no envio do formulário, para o aviso de conexão do núcleo (RNF-03) manter o que foi
   digitado e reenviar quando a internet voltar. */
(function () {
  "use strict";

  function resumoDoCampo(campo) {
    var id = campo.id + "-escolhidas";
    var resumo = document.getElementById(id);
    if (!resumo) {
      resumo = document.createElement("p");
      resumo.id = id;
      resumo.className = "el-aulas-fotos-escolhidas";
      resumo.setAttribute("aria-live", "polite");
      campo.insertAdjacentElement("afterend", resumo);
    }
    return resumo;
  }

  function atualizar(campo) {
    var resumo = resumoDoCampo(campo);
    var limite = parseInt(campo.getAttribute("data-fotos"), 10) || 10;
    var total = campo.files ? campo.files.length : 0;
    resumo.removeAttribute("data-excesso");
    if (!total) {
      resumo.textContent = "";
    } else if (total > limite) {
      resumo.setAttribute("data-excesso", "");
      resumo.textContent = "Você escolheu " + total + " fotos. Envie até " + limite + " por vez; as outras podem ir depois, em Adicionar fotos.";
    } else {
      resumo.textContent = total === 1 ? "1 foto escolhida." : total + " fotos escolhidas.";
    }
  }

  document.addEventListener("change", function (evt) {
    var campo = evt.target;
    if (campo && campo.matches && campo.matches("input[type=file][data-fotos]")) atualizar(campo);
  });

  function iniciar(raiz) {
    (raiz || document).querySelectorAll("input[type=file][data-fotos]").forEach(function (campo) {
      resumoDoCampo(campo);
    });
  }

  if (window.htmx) {
    htmx.onLoad(iniciar);
  } else {
    document.addEventListener("DOMContentLoaded", function () { iniciar(document); });
  }
})();

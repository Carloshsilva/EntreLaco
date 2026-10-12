/* EntreLaço: comportamento das telas.
   Tudo funciona sem JavaScript; este arquivo só melhora a experiência:
   - envia o token CSRF nas requisições do HTMX;
   - se a internet cair no envio, mantém o que foi digitado, avisa e reenvia quando ela volta (RNF-03);
   - botões "usar o valor salvo" na tela de conflito (RNF-04);
   - quadro de assinatura com o dedo (modo assinatura, SEG-08);
   - foco e menu acessíveis depois de cada troca de tela. */
(function () {
  "use strict";

  function token() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  document.addEventListener("htmx:configRequest", function (evt) {
    var t = token();
    if (t) evt.detail.headers["X-CSRFToken"] = t;
  });

  /* ---------- Conexão (RNF-03) ---------- */
  var pendente = null;

  function aviso() { return document.getElementById("aviso-conexao"); }

  function mostrarAviso(estado, texto) {
    var el = aviso();
    if (!el) return;
    el.className = "el-sync el-sync-" + estado;
    el.querySelector("[data-aviso-texto]").textContent = texto;
    var botao = el.querySelector("[data-aviso-tentar]");
    if (botao) botao.hidden = estado !== "offline";
    var icone = el.querySelector("use");
    if (icone) {
      var base = icone.getAttribute("href").split("#")[0];
      var nome = estado === "offline" ? "offline" : estado === "syncing" ? "sincronizando" : "ok";
      icone.setAttribute("href", base + "#" + nome);
    }
    el.hidden = false;
  }

  function esconderAviso() {
    var el = aviso();
    if (el) el.hidden = true;
  }

  function reenviar() {
    if (!pendente) return;
    var alvo = pendente;
    pendente = null;
    mostrarAviso("syncing", "Enviando o que ficou pendente…");
    if (alvo.tagName === "FORM") {
      if (typeof alvo.requestSubmit === "function") alvo.requestSubmit();
      else htmx.trigger(alvo, "submit");
    } else {
      alvo.click();
    }
  }

  document.addEventListener("htmx:sendError", function (evt) {
    var elt = evt.detail.elt;
    pendente = elt.closest("form") || elt;
    mostrarAviso("offline", "Sem internet. O que você digitou continua na tela e será enviado quando a conexão voltar.");
  });

  document.addEventListener("htmx:responseError", function (evt) {
    if (evt.detail.xhr && evt.detail.xhr.status >= 500) {
      mostrarAviso("offline", "O servidor não respondeu como esperado. O que você digitou continua na tela; tente de novo em instantes.");
      var elt = evt.detail.elt;
      pendente = elt.closest("form") || elt;
    }
  });

  document.addEventListener("htmx:afterRequest", function (evt) {
    if (evt.detail.successful && aviso() && !aviso().hidden && !pendente) {
      mostrarAviso("synced", "Tudo enviado.");
      window.setTimeout(esconderAviso, 4000);
    }
  });

  window.addEventListener("online", reenviar);

  document.addEventListener("click", function (evt) {
    var botao = evt.target.closest("[data-aviso-tentar]");
    if (botao) {
      evt.preventDefault();
      reenviar();
    }
  });

  /* ---------- Conflito de edição (RNF-04) ---------- */
  function definirValor(nome, valor) {
    var campos = document.querySelectorAll('[name="' + nome + '"]');
    if (!campos.length) return;
    var lista = Array.isArray(valor) ? valor.map(String) : [valor === null || valor === undefined ? "" : String(valor)];
    campos.forEach(function (campo) {
      if (campo.type === "checkbox" && campos.length === 1) {
        campo.checked = valor === true || valor === "True" || valor === "on";
      } else if (campo.type === "checkbox" || campo.type === "radio") {
        campo.checked = lista.indexOf(campo.value) !== -1;
      } else if (campo.tagName === "SELECT" && campo.multiple) {
        Array.prototype.forEach.call(campo.options, function (opcao) { opcao.selected = lista.indexOf(opcao.value) !== -1; });
      } else {
        campo.value = lista[0];
      }
      campo.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  document.addEventListener("click", function (evt) {
    var botao = evt.target.closest("[data-usar-valor]");
    if (!botao) return;
    evt.preventDefault();
    var valor;
    try { valor = JSON.parse(botao.getAttribute("data-valor")); } catch (e) { valor = botao.getAttribute("data-valor"); }
    definirValor(botao.getAttribute("data-campo"), valor);
    var item = botao.closest(".el-conflict-item");
    var status = item ? item.querySelector("[data-escolha]") : null;
    if (status) status.textContent = "Valor salvo aplicado ao formulário. Confira e salve de novo.";
    var campo = document.getElementById("id_" + botao.getAttribute("data-campo"));
    if (campo) campo.focus();
  });

  /* ---------- Quadro de assinatura (SEG-08) ---------- */
  function iniciarAssinatura(canvas) {
    if (canvas.dataset.pronto) return;
    canvas.dataset.pronto = "1";
    var destino = document.getElementById(canvas.getAttribute("data-destino"));
    var ctx = canvas.getContext("2d");
    var desenhando = false;
    var tracou = false;

    function ajustar() {
      var r = canvas.getBoundingClientRect();
      var escala = window.devicePixelRatio || 1;
      canvas.width = Math.round(r.width * escala);
      canvas.height = Math.round(r.height * escala);
      ctx.setTransform(escala, 0, 0, escala, 0, 0);
      ctx.lineWidth = 2.5;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = "#16201D";
      ctx.fillStyle = "#FFFFFF";
      ctx.fillRect(0, 0, r.width, r.height);
      tracou = false;
      if (destino) destino.value = "";
    }

    function ponto(evt) {
      var r = canvas.getBoundingClientRect();
      return { x: evt.clientX - r.left, y: evt.clientY - r.top };
    }

    canvas.addEventListener("pointerdown", function (evt) {
      desenhando = true;
      canvas.setPointerCapture(evt.pointerId);
      var p = ponto(evt);
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
    });
    canvas.addEventListener("pointermove", function (evt) {
      if (!desenhando) return;
      var p = ponto(evt);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      tracou = true;
    });
    function terminar() {
      if (!desenhando) return;
      desenhando = false;
      if (tracou && destino) destino.value = canvas.toDataURL("image/png");
    }
    canvas.addEventListener("pointerup", terminar);
    canvas.addEventListener("pointercancel", terminar);

    var limpar = document.querySelector('[data-limpar-assinatura="' + canvas.id + '"]');
    if (limpar) limpar.addEventListener("click", function (evt) { evt.preventDefault(); ajustar(); });

    ajustar();
  }

  /* ---------- Menu ---------- */
  document.addEventListener("keydown", function (evt) {
    if (evt.key !== "Escape") return;
    document.querySelectorAll("details.el-menu[open]").forEach(function (menu) {
      menu.removeAttribute("open");
      var resumo = menu.querySelector("summary");
      if (resumo) resumo.focus();
    });
  });

  document.addEventListener("click", function (evt) {
    document.querySelectorAll("details.el-menu[open]").forEach(function (menu) {
      if (!menu.contains(evt.target)) menu.removeAttribute("open");
    });
  });

  /* ---------- Foco depois da troca de tela ---------- */
  document.addEventListener("htmx:afterSettle", function (evt) {
    var erros = document.querySelector(".el-form-errors");
    if (erros) {
      erros.setAttribute("tabindex", "-1");
      erros.focus();
      return;
    }
    var conflito = document.querySelector(".el-conflict");
    if (conflito) {
      conflito.setAttribute("tabindex", "-1");
      conflito.focus();
      return;
    }
    if (evt.detail.boosted) {
      var main = document.getElementById("conteudo");
      if (main) main.focus({ preventScroll: false });
      window.scrollTo(0, 0);
    }
  });

  function iniciar(raiz) {
    (raiz || document).querySelectorAll("canvas[data-assinatura]").forEach(iniciarAssinatura);
    (raiz || document).querySelectorAll("[data-usar-valor]").forEach(function (b) { b.hidden = false; });
  }

  if (window.htmx) {
    htmx.onLoad(iniciar);
  } else {
    document.addEventListener("DOMContentLoaded", function () { iniciar(document); });
  }
})();

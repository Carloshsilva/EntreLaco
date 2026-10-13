"""Edição com motivo e detecção de conflito para cadastros sem o campo `versao`.

Pessoa (core.Usuario e core.Vinculo), papel (core.Papel) e configuração (core.Servico) são do
núcleo e não herdam ModeloDoServico, então o EditarComAuditoriaMixin não serve para eles.
Este mixin segue a mesma regra (RNF-04), comparando valores em vez de versões:

- a página leva, num campo escondido e assinado (`estado_original`), os valores que a pessoa viu;
- ao salvar, campo que só a outra pessoa mudou fica com o valor dela;
- campo que as duas mudaram, para valores diferentes, é conflito: nada é salvo e a tela mostra
  as duas versões (core/_conflito.html).
"""
import json

from django.contrib import messages
from django.core import signing
from django.db import transaction
from django.http import HttpResponseRedirect

SAL_DO_ESTADO = "entrelaco.equipe.estado-original"


def assinar_estado(valores):
    return signing.dumps(valores, salt=SAL_DO_ESTADO, compress=True)


def ler_estado(texto):
    if not texto:
        return None
    try:
        return signing.loads(texto, salt=SAL_DO_ESTADO)
    except signing.BadSignature:
        return None


def comparar_com_o_salvo(original, salvo, enviado):
    """Devolve (conflitos, manter_do_banco), listas de nomes de campo."""
    if original is None or original == salvo:
        return [], []
    conflitos, manter = [], []
    for nome, valor_salvo in salvo.items():
        if nome not in original or original[nome] == valor_salvo:
            continue
        if enviado.get(nome) == original[nome]:
            manter.append(nome)
        elif enviado.get(nome) != valor_salvo:
            conflitos.append(nome)
    return conflitos, manter


def dados_com_o_salvo(post, nomes, brutos):
    """O POST com os campos `nomes` trocados pelo valor salvo."""
    dados = post.copy()
    for nome in nomes:
        valor = brutos[nome]
        if isinstance(valor, (list, tuple)):
            dados.setlist(nome, [str(v) for v in valor])
        elif isinstance(valor, bool):
            if valor:
                dados[nome] = "on"
            else:
                dados.pop(nome, None)
        else:
            dados[nome] = "" if valor is None else str(valor)
    return dados


def mudancas_entre(antes, depois, form):
    """Dicionário de mudanças no formato da trilha (core.auditoria.comparar)."""
    mudancas = {}
    for nome, novo in depois.items():
        velho = antes.get(nome, "")
        if velho != novo:
            mudancas[nome] = {"rotulo": str(form.fields[nome].label), "grupo": None, "de": velho, "para": novo}
    return mudancas


class EdicaoSemVersaoMixin:
    """Para FormView. A view define:

    - `objeto_atual()`: o cadastro como está agora (sem trava), para montar o estado original;
    - `travar()`: o mesmo cadastro lido com select_for_update, dentro da transação;
    - `valores_salvos(obj)` e `valores_brutos(obj)`: legíveis (como na trilha) e no formato do formulário;
    - `salvar(obj, form, mudancas)`: grava e registra na trilha, na mesma transação;
    - `ultimo_evento(obj)` (opcional): o último evento da trilha, para dizer quem salvou antes.

    O formulário define `valores_legiveis()` a partir do cleaned_data.
    """

    mensagem_sucesso = "Alterações salvas."

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        if "estado_original" not in contexto:
            # Formulário devolvido com erro mantém o que a pessoa viu ao abrir, não o que está salvo
            # agora: senão a mudança de outra pessoa nesse meio-tempo passaria sem aviso.
            enviado = self.request.POST.get("estado_original", "") if self.request.method == "POST" else ""
            if ler_estado(enviado) is not None:
                contexto["estado_original"] = enviado
            else:
                contexto["estado_original"] = assinar_estado(self.valores_salvos(self.objeto_atual()))
        return contexto

    def ultimo_evento(self, obj):
        return None

    def form_valid(self, form):
        mudancas = {}
        with transaction.atomic():
            atual = self.travar()
            salvo = self.valores_salvos(atual)
            enviado = form.valores_legiveis()
            original = ler_estado(self.request.POST.get("estado_original", ""))
            conflitos, manter = comparar_com_o_salvo(original, salvo, enviado)
            brutos = self.valores_brutos(atual)
            if manter:
                kwargs = self.get_form_kwargs()
                kwargs["data"] = dados_com_o_salvo(self.request.POST, manter, brutos)
                form = self.get_form_class()(**kwargs)
                if not form.is_valid():
                    return self.form_invalid(form)
                enviado = form.valores_legiveis()
            if conflitos:
                evento = self.ultimo_evento(atual)
                return self.render_to_response(self.get_context_data(
                    form=form,
                    conflitos=[
                        {
                            "nome": nome,
                            "rotulo": form.fields[nome].label,
                            "salvo": salvo[nome],
                            "meu": enviado[nome],
                            "valor_salvo_json": json.dumps(brutos[nome]),
                        }
                        for nome in conflitos
                    ],
                    conflito_autor=evento.usuario if evento is not None else None,
                    conflito_quando=evento.criado_em if evento is not None else None,
                    estado_original=assinar_estado(salvo),
                ))
            mudancas = mudancas_entre(salvo, enviado, form)
            if mudancas:
                self.salvar(atual, form, mudancas)
        messages.success(self.request, self.mensagem_sucesso if mudancas else "Nada mudou.")
        return HttpResponseRedirect(self.get_success_url())

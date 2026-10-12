"""Mixins que toda tela de cadastro usa.

- `AcessoMixin`: exige login, um serviço e a permissão pedida pela tela.
- `DoServicoMixin`: limita as consultas ao serviço da pessoa (SEG-05); objeto de
  outro serviço dá 404.
- `CriarComAuditoriaMixin` e `EditarComAuditoriaMixin`: gravam quem fez o quê
  na trilha (SEG-03), pedem o motivo na edição e detectam quando outra pessoa
  salvou o mesmo dado no meio do caminho (RNF-04).
"""
import datetime
import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import render

from . import auditoria
from .formularios import formulario_para
from .permissoes import EDITAR, VER

SAL_DO_ESTADO = "entrelaco.estado-original"


class AcessoMixin(LoginRequiredMixin):
    """Exige serviço e permissão.

    Defina `grupo` (tipo de dado) e `modo` ('ver' ou 'editar'), ou `acao`
    (código de ACOES), ou `exige_configurar = True`.
    """

    grupo = None
    modo = VER
    acao = None
    exige_configurar = False

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.servico is None:
            return render(request, "core/sem_vinculo.html", status=403)
        if not self.tem_permissao(request):
            raise PermissionDenied("Seu papel não permite esta tela.")
        return super().dispatch(request, *args, **kwargs)

    def tem_permissao(self, request):
        acesso = request.acesso
        if self.exige_configurar and not acesso.configurar:
            return False
        if self.acao and not acesso.tem(self.acao):
            return False
        if self.grupo and not acesso.pode(self.grupo, self.modo):
            return False
        return True


class DoServicoMixin:
    """Filtra o queryset pelo serviço da pessoa logada."""

    def get_queryset(self):
        return super().get_queryset().filter(servico=self.request.servico)


class FormularioPorPermissaoMixin:
    """Monta o formulário só com os campos que o papel pode editar.

    Defina `campos` (ordem e recorte) e, se precisar, `form_base` e `widgets`.
    """

    campos = None
    form_base = None
    widgets = None
    edicao = False

    def get_form_class(self):
        kwargs = {"campos": self.campos, "edicao": self.edicao, "widgets": self.widgets}
        if self.form_base is not None:
            kwargs["base"] = self.form_base
        return formulario_para(self.model, self.request.acesso, **kwargs)

    def campos_auditados(self, form):
        return [nome for nome in form.fields if nome != "motivo_alteracao" and _e_campo_do_modelo(self.model, nome)]


def _e_campo_do_modelo(modelo, nome):
    try:
        modelo._meta.get_field(nome)
        return True
    except Exception:  # noqa: BLE001 - FieldDoesNotExist e afins
        return False


class CriarComAuditoriaMixin(FormularioPorPermissaoMixin):
    modo = EDITAR
    mensagem_sucesso = "Salvo."

    def preparar_objeto(self, obj, form):
        """Gancho para preencher campos que não vêm do formulário."""

    def form_valid(self, form):
        with transaction.atomic():
            obj = form.save(commit=False)
            obj.servico = self.request.servico
            obj.criado_por = self.request.user
            obj.atualizado_por = self.request.user
            self.preparar_objeto(obj, form)
            obj.save()
            form.save_m2m()
            campos = self.campos_auditados(form)
            depois = auditoria.fotografar(obj, campos)
            mudancas = auditoria.comparar(type(obj), {}, depois)
            auditoria.registrar(self.request, auditoria.Acao.CRIOU, obj, mudancas=mudancas)
            self.object = obj
            self.depois_de_salvar(obj, form, criado=True)
        if self.mensagem_sucesso:
            messages.success(self.request, self.mensagem_sucesso)
        return HttpResponseRedirect(self.get_success_url())

    def depois_de_salvar(self, obj, form, criado):
        """Gancho para trabalho extra na mesma transação."""


class EditarComAuditoriaMixin(FormularioPorPermissaoMixin):
    """Edição com motivo obrigatório e detecção de conflito (RNF-04).

    A página leva, num campo escondido e assinado (`estado_original`), a versão
    e os valores que a pessoa viu ao abrir o formulário. Ao salvar, se outra
    pessoa gravou no meio do caminho:
    - campo que só a outra pessoa mudou fica com o valor dela;
    - campo que só esta pessoa mudou é salvo;
    - campo que as duas mudaram, para valores diferentes, é conflito: nada é
      salvo, e a tela mostra as duas versões para a pessoa escolher.

    O template inclui `core/_formulario.html`, que já põe o campo escondido e
    o quadro de conflito.
    """

    modo = EDITAR
    edicao = True
    mensagem_sucesso = "Alterações salvas."

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        if "estado_original" not in contexto:
            form = contexto.get("form")
            campos = self.campos_auditados(form) if form is not None else []
            contexto["estado_original"] = _assinar_estado(self.object, campos)
        return contexto

    def form_valid(self, form):
        modelo = type(self.object)
        estado = _ler_estado(self.request.POST.get("estado_original", ""))
        mudancas = {}
        with transaction.atomic():
            atual = modelo.objects.select_for_update().get(pk=self.object.pk)
            campos = self.campos_auditados(form)
            manter_do_banco = []
            if estado is not None and estado["versao"] != atual.versao:
                conflitos, manter_do_banco = self._comparar_com_o_banco(atual, form, campos, estado["valores"])
                if conflitos:
                    return self._mostrar_conflitos(atual, form, campos, conflitos, manter_do_banco)
            for nome in manter_do_banco:
                campo_modelo = modelo._meta.get_field(nome)
                if campo_modelo.many_to_many:
                    form.cleaned_data[nome] = list(getattr(atual, nome).all())
                else:
                    setattr(form.instance, campo_modelo.attname, getattr(atual, campo_modelo.attname))
            antes = auditoria.fotografar(atual, campos)
            obj = form.save(commit=False)
            obj.versao = atual.versao + 1
            obj.atualizado_por = self.request.user
            obj.servico_id = atual.servico_id
            self.preparar_objeto(obj, form)
            obj.save()
            form.save_m2m()
            depois = auditoria.fotografar(obj, campos)
            mudancas = auditoria.comparar(modelo, antes, depois)
            if mudancas:
                auditoria.registrar(
                    self.request, auditoria.Acao.ALTEROU, obj,
                    mudancas=mudancas, motivo=form.cleaned_data.get("motivo_alteracao", ""),
                )
            self.object = obj
            self.depois_de_salvar(obj, form, criado=False)
        if self.mensagem_sucesso:
            messages.success(self.request, self.mensagem_sucesso if mudancas else "Nada mudou.")
        return HttpResponseRedirect(self.get_success_url())

    def preparar_objeto(self, obj, form):
        """Gancho para preencher campos que não vêm do formulário."""

    def depois_de_salvar(self, obj, form, criado):
        """Gancho para trabalho extra na mesma transação."""

    def _comparar_com_o_banco(self, atual, form, campos, originais):
        salvo = auditoria.fotografar(atual, campos)
        conflitos, manter_do_banco = [], []
        for nome in campos:
            if nome not in originais:
                continue
            outra_pessoa_mudou = salvo[nome] != originais[nome]
            if not outra_pessoa_mudou:
                continue
            enviado = _valor_enviado(form, nome)
            esta_pessoa_mudou = enviado != originais[nome]
            if not esta_pessoa_mudou:
                manter_do_banco.append(nome)
            elif enviado != salvo[nome]:
                conflitos.append({
                    "nome": nome,
                    "rotulo": form.fields[nome].label,
                    "salvo": salvo[nome],
                    "meu": enviado,
                    "valor_salvo_json": json.dumps(_valor_para_o_formulario(atual, nome, form.fields[nome])),
                })
        return conflitos, manter_do_banco

    def _mostrar_conflitos(self, atual, form, campos, conflitos, manter_do_banco):
        """Mostra o formulário de novo com as duas versões; nada foi salvo."""
        dados = self.request.POST.copy()
        for nome in manter_do_banco:
            valor = _valor_para_o_formulario(atual, nome, form.fields[nome])
            if isinstance(valor, list):
                dados.setlist(nome, [str(v) for v in valor])
            elif isinstance(valor, bool):
                if valor:
                    dados[nome] = "on"
                else:
                    dados.pop(nome, None)
            else:
                dados[nome] = "" if valor is None else str(valor)
        novo_form = self.get_form_class()(data=dados, files=self.request.FILES, instance=self.object)
        novo_form.is_valid()
        return self.render_to_response(self.get_context_data(
            form=novo_form,
            conflitos=conflitos,
            conflito_autor=atual.atualizado_por,
            conflito_quando=atual.atualizado_em,
            estado_original=_assinar_estado(atual, campos),
        ))


def _assinar_estado(obj, campos):
    return signing.dumps(
        {"versao": obj.versao, "valores": auditoria.fotografar(obj, campos)}, salt=SAL_DO_ESTADO, compress=True
    )


def _ler_estado(texto):
    if not texto:
        return None
    try:
        return signing.loads(texto, salt=SAL_DO_ESTADO)
    except signing.BadSignature:
        return None


def _valor_enviado(form, nome):
    """O valor que a pessoa enviou, no mesmo formato legível da trilha."""
    campo_modelo = form.instance._meta.get_field(nome)
    if campo_modelo.many_to_many:
        return auditoria.valor_legivel(form.cleaned_data.get(nome) or [])
    return auditoria.valor_do_campo(form.instance, nome)


def _valor_para_o_formulario(obj, nome, campo_form):
    """Valor salvo no formato que o campo do formulário espera (para o botão "usar o valor salvo")."""
    campo_modelo = obj._meta.get_field(nome)
    if campo_modelo.many_to_many:
        return [item.pk for item in getattr(obj, nome).all()]
    if campo_modelo.is_relation:
        return getattr(obj, campo_modelo.attname)
    valor = getattr(obj, nome)
    if isinstance(valor, datetime.datetime):
        return valor.strftime("%Y-%m-%dT%H:%M")
    if isinstance(valor, datetime.date):
        return valor.isoformat()
    if isinstance(valor, datetime.time):
        return valor.strftime("%H:%M")
    if isinstance(valor, (bool, int, float)) or valor is None:
        return valor
    if hasattr(valor, "name"):  # arquivo: não dá para pôr de volta num campo de envio
        return None
    return str(valor)

"""Telas das reuniões: calendário, pauta, ata e alunos citados (RF-17, RF-44).

- Ver as telas pede ver "Reuniões e atas"; marcar, editar e citar alunos pede editar.
- Toda consulta filtra por `request.servico`; reunião ou citação de outro serviço dá 404.
- Uma citação só aparece para quem vê as atas e o tipo de dado dela (RF-17). A de um
  tipo que a pessoa não vê não existe para ela: some da lista, do detalhe e dá 404.
"""
import datetime

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView

from alunos.models import Aluno
from core import auditoria
from core.formularios import DATA, HORA
from core.models import EventoAuditoria
from core.permissoes import EDITAR
from core.views import eventos_do_objeto
from core.views_base import (
    AcessoMixin,
    CriarComAuditoriaMixin,
    DoServicoMixin,
    EditarComAuditoriaMixin,
    _ler_estado,
)

from .consultas import (
    GRUPO,
    citacoes_visiveis,
    grupos_visiveis,
    participantes_em_ordem,
    pode_concluir,
    preparar_citacoes,
    proteger_mudancas,
)
from .formularios import FormularioCitacaoBase, FormularioReuniaoBase, com_contexto
from .models import CitacaoDeAluno, Reuniao

POR_PAGINA = 20
LIMITE_DE_PROXIMAS = 60
LIMITE_DO_HISTORICO = 30

CAMPOS_DA_REUNIAO = ["tipo", "titulo", "data", "hora_inicio", "duracao_minutos", "local", "participantes", "pauta"]
CAMPOS_DA_EDICAO = CAMPOS_DA_REUNIAO + ["situacao", "ata"]
CAMPOS_DA_CITACAO = ["aluno", "texto", "grupo_de_dado", "encaminhamento", "responsavel", "prazo"]
CAMPOS_DA_EDICAO_DA_CITACAO = CAMPOS_DA_CITACAO + ["concluida"]


def _aluno_do_parametro(request):
    """Aluno pedido por ?aluno=<pk>, sempre do serviço da pessoa (o de outro serviço dá 404)."""
    valor = request.GET.get("aluno", "")
    if not valor.isdigit():
        return None
    return get_object_or_404(
        Aluno.objects.only("id", "nome", "nome_social", "servico_id"), pk=int(valor), servico=request.servico
    )


def _proximo_seguro(request):
    proximo = request.POST.get("proximo") or request.GET.get("proximo") or ""
    if proximo and url_has_allowed_host_and_scheme(
        proximo, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return proximo
    return ""


def _url_da_citacao(citacao):
    return reverse("reunioes:detalhe", args=[citacao.reuniao_id]) + f"#citacao-{citacao.pk}"


# ---------------------------------------------------------------- lista

class ListaDeReunioes(AcessoMixin, TemplateView):
    """Próximas e passadas, com o número de alunos citados que a pessoa pode ver."""

    grupo = GRUPO
    template_name = "reunioes/lista.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        request = self.request
        hoje = timezone.localdate()
        grupos = grupos_visiveis(request.acesso)
        reunioes = Reuniao.objects.filter(servico=request.servico).annotate(
            alunos_citados=Count("citacoes__aluno", filter=Q(citacoes__grupo_de_dado__in=grupos), distinct=True)
        ).only("id", "tipo", "titulo", "data", "hora_inicio", "situacao")
        proximas = list(
            reunioes.filter(data__gte=hoje).order_by("data", F("hora_inicio").asc(nulls_first=True), "pk")
            [:LIMITE_DE_PROXIMAS]
        )
        passadas = reunioes.filter(data__lt=hoje).order_by("-data", F("hora_inicio").desc(nulls_last=True), "-pk")
        aluno_citar = None
        if request.acesso.pode_editar(GRUPO):
            aluno_citar = _aluno_do_parametro(request)
        contexto.update({
            "proximas": proximas,
            "pagina": Paginator(passadas, POR_PAGINA).get_page(request.GET.get("pagina")),
            "aluno_citar": aluno_citar,
            "limite_de_proximas": LIMITE_DE_PROXIMAS,
        })
        return contexto


# ---------------------------------------------------------------- marcar e editar

class FormularioDaReuniaoMixin:
    grupo = GRUPO
    modo = EDITAR
    model = Reuniao
    form_base = FormularioReuniaoBase
    widgets = {
        "data": DATA,
        "hora_inicio": HORA,
        "duracao_minutos": forms.NumberInput,
        "participantes": forms.CheckboxSelectMultiple,
        "pauta": forms.Textarea(attrs={"rows": 4}),
        "ata": forms.Textarea(attrs={"rows": 12}),
        "situacao": forms.RadioSelect,
    }
    template_name = "reunioes/reuniao_form.html"

    def get_form_class(self):
        return com_contexto(super().get_form_class(), self.request)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        secoes = [
            {"titulo": "Quando e onde", "campos": ["tipo", "titulo", "data", "hora_inicio", "duracao_minutos", "local"]},
            {"titulo": "Quem participa", "campos": ["participantes"]},
            {"titulo": "O que vai ser conversado", "campos": ["pauta"]},
        ]
        if self.object is not None:
            secoes.append({
                "titulo": "Ata e situação",
                "campos": ["situacao", "ata"],
                "ajuda": "Depois da reunião, escreva a ata e mude a situação para realizada.",
            })
        contexto["secoes"] = secoes
        return contexto

    def get_success_url(self):
        return reverse("reunioes:detalhe", args=[self.object.pk])


class NovaReuniao(FormularioDaReuniaoMixin, AcessoMixin, CriarComAuditoriaMixin, CreateView):
    campos = CAMPOS_DA_REUNIAO
    mensagem_sucesso = "Reunião marcada."

    def get_initial(self):
        inicial = {"participantes": [self.request.user.pk]}
        try:
            inicial["data"] = datetime.date.fromisoformat(self.request.GET.get("data", ""))
        except ValueError:
            pass
        return inicial


class EditarReuniao(FormularioDaReuniaoMixin, AcessoMixin, DoServicoMixin, EditarComAuditoriaMixin, UpdateView):
    campos = CAMPOS_DA_EDICAO
    mensagem_sucesso = "Reunião salva."


# ---------------------------------------------------------------- detalhe

class DetalheDaReuniao(AcessoMixin, DoServicoMixin, DetailView):
    """Dados, participantes, pauta, ata, alunos citados (só os visíveis) e histórico."""

    grupo = GRUPO
    model = Reuniao
    template_name = "reunioes/detalhe.html"
    context_object_name = "reuniao"

    def get_queryset(self):
        return super().get_queryset().prefetch_related(participantes_em_ordem())

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        request = self.request
        reuniao = self.object
        citacoes = list(
            citacoes_visiveis(request.servico, request.acesso).filter(reuniao=reuniao)
            .select_related("aluno", "responsavel").order_by("aluno__nome", "criado_em")
        )
        preparar_citacoes(citacoes, request.user, request.acesso)
        eventos = eventos_do_objeto(request, reuniao, limite=LIMITE_DO_HISTORICO)
        if citacoes:
            # Histórico das citações que a pessoa vê; as escondidas ficam fora (RF-07).
            eventos_das_citacoes = list(EventoAuditoria.objects.filter(
                servico=request.servico, modelo=CitacaoDeAluno._meta.label,
                objeto_id__in=[str(citacao.pk) for citacao in citacoes],
            )[:LIMITE_DO_HISTORICO])
            eventos_das_citacoes = auditoria.preparar_para_exibir(eventos_das_citacoes, request.acesso)
            eventos = sorted(eventos + eventos_das_citacoes, key=lambda e: (e.criado_em, e.pk), reverse=True)
        contexto.update({
            "citacoes": citacoes,
            "alunos_citados": len({citacao.aluno_id for citacao in citacoes}),
            "eventos": eventos[:LIMITE_DO_HISTORICO],
        })
        return contexto


# ---------------------------------------------------------------- citações

class FormularioDaCitacaoMixin:
    """Comum a citar e editar a citação.

    A gravação é a dos mixins do núcleo, com uma diferença: as mudanças de uma citação
    de saúde (ou de outro tipo restrito) vão para a trilha marcadas com esse tipo, para
    que quem não o vê não leia o que foi dito no histórico (veja `proteger_mudancas`).
    """

    grupo = GRUPO
    modo = EDITAR
    model = CitacaoDeAluno
    form_base = FormularioCitacaoBase
    widgets = {
        "grupo_de_dado": forms.RadioSelect,
        "texto": forms.Textarea(attrs={"rows": 4}),
        "encaminhamento": forms.Textarea(attrs={"rows": 3}),
        "prazo": DATA,
    }
    template_name = "reunioes/citacao_form.html"

    def get_form_class(self):
        return com_contexto(super().get_form_class(), self.request)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["reuniao"] = self.reuniao
        contexto["secoes"] = [
            {"titulo": "Aluno e o que foi dito", "campos": ["aluno", "texto", "grupo_de_dado"]},
            {
                "titulo": "Encaminhamento",
                "campos": ["encaminhamento", "responsavel", "prazo", "concluida"],
                "ajuda": "Com responsável, o encaminhamento aparece nas pendências da pessoa até ser concluído.",
            },
        ]
        return contexto

    def get_success_url(self):
        return _url_da_citacao(self.object)


class NovaCitacao(FormularioDaCitacaoMixin, AcessoMixin, CriarComAuditoriaMixin, CreateView):
    campos = CAMPOS_DA_CITACAO
    mensagem_sucesso = "Citação salva. Ela já aparece no perfil do aluno."

    @cached_property
    def reuniao(self):
        return get_object_or_404(Reuniao, pk=self.kwargs["pk"], servico=self.request.servico)

    @cached_property
    def aluno_inicial(self):
        return _aluno_do_parametro(self.request)

    def get(self, request, *args, **kwargs):
        self.reuniao, self.aluno_inicial  # noqa: B018 - 404 antes de montar a tela
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.reuniao  # noqa: B018 - 404 antes de validar o formulário
        return super().post(request, *args, **kwargs)

    def get_initial(self):
        inicial = super().get_initial()
        if self.request.method == "GET" and self.aluno_inicial is not None:
            inicial["aluno"] = self.aluno_inicial.pk
        return inicial

    def form_valid(self, form):
        request = self.request
        with transaction.atomic():
            citacao = form.save(commit=False)
            citacao.servico = request.servico
            citacao.reuniao = self.reuniao
            citacao.criado_por = request.user
            citacao.atualizado_por = request.user
            citacao.save()
            campos = self.campos_auditados(form)
            mudancas = auditoria.comparar(CitacaoDeAluno, {}, auditoria.fotografar(citacao, campos))
            auditoria.registrar(
                request, auditoria.Acao.CRIOU, citacao, mudancas=proteger_mudancas(mudancas, citacao.grupo_de_dado)
            )
            self.object = citacao
        messages.success(request, self.mensagem_sucesso)
        return HttpResponseRedirect(self.get_success_url())


class EditarCitacao(FormularioDaCitacaoMixin, AcessoMixin, DoServicoMixin, EditarComAuditoriaMixin, UpdateView):
    campos = CAMPOS_DA_EDICAO_DA_CITACAO
    mensagem_sucesso = "Citação salva."

    def get_queryset(self):
        # Citação de um tipo de dado que a pessoa não vê não existe para ela (404).
        return super().get_queryset().filter(
            grupo_de_dado__in=grupos_visiveis(self.request.acesso)
        ).select_related("reuniao", "aluno")

    @property
    def reuniao(self):
        return self.object.reuniao

    def form_valid(self, form):
        """O mesmo de EditarComAuditoriaMixin.form_valid, com as mudanças protegidas na trilha."""
        request = self.request
        estado = _ler_estado(request.POST.get("estado_original", ""))
        mudancas = {}
        with transaction.atomic():
            atual = CitacaoDeAluno.objects.select_for_update().get(pk=self.object.pk)
            campos = self.campos_auditados(form)
            manter_do_banco = []
            if estado is not None and estado["versao"] != atual.versao:
                conflitos, manter_do_banco = self._comparar_com_o_banco(atual, form, campos, estado["valores"])
                if conflitos:
                    return self._mostrar_conflitos(atual, form, campos, conflitos, manter_do_banco)
            for nome in manter_do_banco:
                campo = CitacaoDeAluno._meta.get_field(nome)
                setattr(form.instance, campo.attname, getattr(atual, campo.attname))
            antes = auditoria.fotografar(atual, campos)
            citacao = form.save(commit=False)
            citacao.versao = atual.versao + 1
            citacao.atualizado_por = request.user
            citacao.servico_id = atual.servico_id
            citacao.reuniao_id = atual.reuniao_id
            citacao.save()
            mudancas = auditoria.comparar(CitacaoDeAluno, antes, auditoria.fotografar(citacao, campos))
            if mudancas:
                auditoria.registrar(
                    request, auditoria.Acao.ALTEROU, citacao,
                    mudancas=proteger_mudancas(mudancas, atual.grupo_de_dado, citacao.grupo_de_dado),
                    motivo=form.cleaned_data.get("motivo_alteracao", ""),
                )
            self.object = citacao
        messages.success(request, self.mensagem_sucesso if mudancas else "Nada mudou.")
        return HttpResponseRedirect(self.get_success_url())


@login_required
@require_POST
def concluir_citacao(request, pk):
    """Marca o encaminhamento como concluído: o responsável por ele ou quem edita as atas (RF-17)."""
    if request.servico is None:
        return render(request, "core/sem_vinculo.html", status=403)
    if not request.acesso.pode_ver(GRUPO):
        raise PermissionDenied("Seu papel não permite ver as reuniões.")
    with transaction.atomic():
        citacao = get_object_or_404(citacoes_visiveis(request.servico, request.acesso).select_for_update(), pk=pk)
        if citacao.concluida:
            messages.info(request, "Este encaminhamento já estava concluído.")
        elif not pode_concluir(citacao, request.user, request.acesso):
            raise PermissionDenied("Só o responsável pelo encaminhamento ou quem edita as atas pode concluí-lo.")
        else:
            antes = auditoria.fotografar(citacao, ["concluida"])
            citacao.concluida = True
            citacao.versao += 1
            citacao.atualizado_por = request.user
            citacao.save(update_fields=["concluida", "versao", "atualizado_por", "atualizado_em"])
            mudancas = auditoria.comparar(CitacaoDeAluno, antes, auditoria.fotografar(citacao, ["concluida"]))
            auditoria.registrar(
                request, auditoria.Acao.ALTEROU, citacao,
                mudancas=proteger_mudancas(mudancas, citacao.grupo_de_dado), descricao="Concluiu o encaminhamento",
            )
            messages.success(request, "Encaminhamento concluído.")
    return redirect(_proximo_seguro(request) or _url_da_citacao(citacao))

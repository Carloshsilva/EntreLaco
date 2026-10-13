"""Telas das autorizações da família e dos termos (RF-25 a RF-29, RF-64, SEG-08, LGPD-03, LGPD-04).

- Termos: só quem configura o serviço. Cada termo tem versão; a nova vira a vigente e
  a anterior fica guardada para sempre. Termo já usado não se edita.
- Colher, revogar e o modo assinatura pedem editar "Autorizações"; o comprovante e os
  arquivos pedem ver. As telas que mostram o aluno pedem também ver a identificação.
- Toda consulta filtra por `request.servico`: aluno, autorização ou termo de outro
  serviço dá 404 (SEG-05).
- Os arquivos (foto do papel, conversa, assinatura) só saem pelas views `arquivo` e
  `imagem_assinatura`, que conferem login, serviço e permissão e registram cada abertura.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_safe
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView

from alunos.models import Aluno, Responsavel
from core import auditoria
from core.arquivos import resumo_sha256, servir_arquivo
from core.middleware import CHAVE_MODO_ASSINATURA
from core.permissoes import EDITAR, VER
from core.views import eventos_do_objeto
from core.views_base import AcessoMixin, CriarComAuditoriaMixin, DoServicoMixin, EditarComAuditoriaMixin

from . import regras
from .formularios import (
    FormularioAssinatura,
    FormularioPapel,
    FormularioPendente,
    FormularioRevogacao,
    FormularioTermo,
    FormularioTermoEdicao,
    FormularioWhatsapp,
)
from .models import Autorizacao, Termo, Tipo, autorizacao_atual

GRUPO = regras.GRUPO
Situacao = Autorizacao.Situacao
Forma = Autorizacao.Forma
Acao = auditoria.Acao

# Campos que vão para a trilha quando uma coleta é registrada.
CAMPOS_DA_TRILHA = [
    "tipo", "situacao", "forma", "termo", "responsavel_nome", "responsavel_documento", "colhida_por", "colhida_em",
    "observacoes",
]
CAMPOS_DA_ASSINATURA = CAMPOS_DA_TRILHA + ["aparelho", "assinatura", "impressao_digital"]
CAMPOS_DA_REVOGACAO = ["situacao", "revogada_em", "revogacao_motivo"]


# ---------------------------------------------------------------- permissões

def exige(modo, *, identificacao=True):
    """Login, serviço e permissão em "Autorizações" (e, quando a tela mostra o aluno, na identificação)."""

    def decorador(view):
        @login_required
        @wraps(view)
        def envolvida(request, *args, **kwargs):
            if request.servico is None:
                return render(request, "core/sem_vinculo.html", status=403)
            acesso = request.acesso
            if not acesso.pode(GRUPO, modo) or (identificacao and not acesso.pode_ver("identificacao")):
                if modo == EDITAR:
                    raise PermissionDenied("Seu papel não permite colher nem revogar autorizações.")
                raise PermissionDenied("Seu papel não permite ver as autorizações da família.")
            return view(request, *args, **kwargs)

        return envolvida

    return decorador


def url_da_secao(aluno):
    return reverse("alunos:detalhe", args=[aluno.pk]) + "#secao-autorizacoes"


def responsaveis_para(request, aluno, *, so_legais=False):
    """Responsáveis do aluno para escolher quem autorizou; só para quem vê a família (RF-07)."""
    if not request.acesso.pode_ver("familia"):
        return []
    responsaveis = Responsavel.objects.filter(servico=request.servico, aluno=aluno)
    if so_legais:
        responsaveis = responsaveis.filter(responsavel_legal=True)
    return list(responsaveis.order_by("-responsavel_legal", "nome", "pk"))


def fotografar(obj, campos):
    return auditoria.fotografar(obj, campos)


# ---------------------------------------------------------------- termos (quem configura)

class TermoMixin:
    """Telas de termos: só quem configura o serviço, e só os termos do próprio serviço (SEG-05).

    Vem antes de AcessoMixin na lista de bases, para valer o `exige_configurar`.
    """

    exige_configurar = True
    model = Termo

    def get_queryset(self):
        return Termo.objects.filter(servico=self.request.servico)


class ListaDeTermos(AcessoMixin, TemplateView):
    """Termos por tipo, com a versão vigente e as anteriores (RF-25, LGPD-03)."""

    exige_configurar = True
    template_name = "autorizacoes/termos.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        termos = list(
            Termo.objects.filter(servico=self.request.servico)
            .annotate(usos=Count("autorizacoes"))
            .select_related("criado_por")
            .order_by("tipo", "-versao_do_termo")
        )
        tipos = []
        for codigo, rotulo in Tipo.choices:
            do_tipo = [t for t in termos if t.tipo == codigo]
            vigente = next((t for t in do_tipo if t.vigente), None)
            tipos.append({
                "codigo": codigo,
                "rotulo": rotulo,
                "rotulo_minusculo": regras.tipo_em_minusculas(codigo),
                "vigente": vigente,
                "anteriores": [t for t in do_tipo if t is not vigente],
            })
        contexto["tipos"] = tipos
        return contexto


class NovoTermo(TermoMixin, AcessoMixin, CriarComAuditoriaMixin, CreateView):
    """Nova versão de um termo: vira a vigente, e a anterior deixa de valer (fica guardada)."""

    template_name = "autorizacoes/termo_form.html"
    mensagem_sucesso = "Termo salvo."

    def get_form_class(self):
        return FormularioTermo

    def _base(self):
        pk = self.request.GET.get("base", "")
        if not pk.isdigit():
            return None
        return Termo.objects.filter(servico=self.request.servico, pk=int(pk)).first()

    def get_initial(self):
        inicial = super().get_initial()
        base = self._base()
        if base is not None:
            inicial.update({"tipo": base.tipo, "titulo": base.titulo, "texto": base.texto})
        elif self.request.GET.get("tipo") in Tipo.values:
            inicial["tipo"] = self.request.GET["tipo"]
        return inicial

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        form = contexto["form"]
        tipo = form["tipo"].value() if "tipo" in form.fields else None
        contexto["vigentes"] = {
            t.tipo: t for t in Termo.objects.filter(servico=self.request.servico, vigente=True)
        }
        contexto["tipo_escolhido"] = tipo if tipo in Tipo.values else None
        contexto["vigente_do_tipo"] = contexto["vigentes"].get(tipo)
        return contexto

    def preparar_objeto(self, obj, form):
        versoes = list(
            Termo.objects.select_for_update().filter(servico=obj.servico, tipo=obj.tipo)
            .values_list("versao_do_termo", flat=True)
        )
        obj.versao_do_termo = max(versoes, default=0) + 1
        obj.vigente = True
        self.mensagem_sucesso = (
            f"Termo salvo. A versão {obj.versao_do_termo} é a vigente a partir de agora; "
            "as autorizações já colhidas continuam apontando para a versão que a família viu."
        )

    def depois_de_salvar(self, obj, form, criado):
        anteriores = Termo.objects.select_for_update().filter(
            servico=obj.servico, tipo=obj.tipo, vigente=True
        ).exclude(pk=obj.pk)
        for anterior in anteriores:
            antes = fotografar(anterior, ["vigente"])
            anterior.vigente = False
            anterior.versao += 1
            anterior.atualizado_por = self.request.user
            anterior.save(update_fields=["vigente", "versao", "atualizado_por", "atualizado_em"])
            auditoria.registrar(
                self.request, Acao.ALTEROU, anterior,
                mudancas=auditoria.comparar(Termo, antes, fotografar(anterior, ["vigente"])),
                motivo=f"Substituído pela versão {obj.versao_do_termo}.",
                descricao=f"Deixou de valer com a versão {obj.versao_do_termo}",
            )

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except IntegrityError:
            form.add_error(
                None,
                "Outra pessoa salvou uma versão deste termo agora mesmo. Confira a lista de termos e tente de novo.",
            )
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse("autorizacoes:termo_detalhe", args=[self.object.pk])


class DetalheDoTermo(TermoMixin, AcessoMixin, DetailView):
    template_name = "autorizacoes/termo_detalhe.html"
    context_object_name = "termo"

    def get_queryset(self):
        return super().get_queryset().select_related("criado_por").annotate(usos=Count("autorizacoes"))

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        termo = self.object
        contexto.update({
            "vigente_do_tipo": termo if termo.vigente else regras.termo_vigente(self.request.servico, termo.tipo),
            "eventos": eventos_do_objeto(self.request, termo),
        })
        return contexto


class EditarTermo(TermoMixin, AcessoMixin, EditarComAuditoriaMixin, UpdateView):
    """Corrigir um termo que ainda não foi usado. Termo usado não se edita: só ganha nova versão."""

    template_name = "autorizacoes/termo_form.html"
    mensagem_sucesso = "Termo salvo."

    def get_form_class(self):
        return FormularioTermoEdicao

    def _recusar_se_usado(self):
        if regras.termo_usado(self.object):
            messages.warning(
                self.request,
                "Este termo já foi usado em autorizações e não pode mais mudar: a família viu este texto. "
                "Para mudar o texto, crie uma nova versão.",
            )
            return redirect(f"{reverse('autorizacoes:termo_novo')}?base={self.object.pk}")
        return None

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self._recusar_se_usado() or super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self._recusar_se_usado() or super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["edicao"] = True
        return contexto

    def get_success_url(self):
        return reverse("autorizacoes:termo_detalhe", args=[self.object.pk])


# ---------------------------------------------------------------- colher

FORMULARIOS_DE_COLETA = {
    Forma.PAPEL: FormularioPapel,
    Forma.WHATSAPP: FormularioWhatsapp,
    regras.PENDENTE: FormularioPendente,
}


@exige(EDITAR)
def colher(request, aluno_pk, tipo):
    """Escolher a forma de coleta, uma por vez, e registrar a coleta (RF-26, RF-27, RF-64).

    Toda coleta é um registro novo; a anterior continua guardada como prova (LGPD-03).
    """
    if tipo not in Tipo.values:
        raise Http404("Tipo de autorização desconhecido.")
    aluno = get_object_or_404(Aluno, pk=aluno_pk, servico=request.servico)
    termo = regras.termo_vigente(request.servico, tipo)
    atual = (
        Autorizacao.objects.filter(servico=request.servico, aluno=aluno, tipo=tipo)
        .select_related("colhida_por").order_by("-criado_em", "-id").first()
    )
    permitidas = regras.formas_permitidas(atual)
    forma = request.POST.get("forma") if request.method == "POST" else request.GET.get("forma")
    if forma not in permitidas or termo is None or not regras.pode_colher(atual):
        forma = None
    contexto = {
        "aluno": aluno,
        "tipo": tipo,
        "tipo_rotulo": Tipo(tipo).label,
        "tipo_minusculo": regras.tipo_em_minusculas(tipo),
        "termo": termo,
        "atual": atual,
        "pode_colher": regras.pode_colher(atual),
        "definitivo": atual is not None and atual.situacao == Situacao.PROVISORIA,
        "permitidas": permitidas,
        "forma": forma,
        "url_voltar": url_da_secao(aluno),
        "url_colher": reverse("autorizacoes:colher", args=[aluno.pk, tipo]),
    }
    if forma is None:
        return render(request, "autorizacoes/colher.html", contexto)

    if forma == Forma.TABLET:
        if request.method == "POST":
            return _comecar_no_tablet(request, aluno, tipo, termo)
        contexto["acao"] = contexto["url_colher"]
        return render(request, "autorizacoes/entregar_tablet.html", contexto)

    classe = FORMULARIOS_DE_COLETA[forma]
    responsaveis = responsaveis_para(request, aluno)
    if request.method == "POST":
        form = classe(request.POST, request.FILES, responsaveis=responsaveis)
        if form.is_valid():
            autorizacao = _registrar_coleta(request, aluno, tipo, termo, forma, form)
            messages.success(request, _mensagem_da_coleta(autorizacao))
            return redirect(url_da_secao(aluno))
    else:
        form = classe(responsaveis=responsaveis)
    contexto["form"] = form
    return render(request, "autorizacoes/colher.html", contexto)


def _mensagem_da_coleta(autorizacao):
    contato = autorizacao.tipo == Tipo.CONTATO_ESCOLA
    if autorizacao.situacao == Situacao.VALIDA:
        return f"Autorização de {regras.tipo_em_minusculas(autorizacao.tipo)} registrada como válida."
    if autorizacao.situacao == Situacao.RECUSADA:
        if contato:
            return "Recusa registrada. Sem autorização de contato, nada é enviado à escola sobre este aluno."
        return "Recusa registrada."
    if autorizacao.situacao == Situacao.PROVISORIA:
        extra = " O contato com a escola já está liberado." if contato else ""
        return (
            f"Sim provisório registrado.{extra} Colha o sim definitivo no tablet ou no papel em até "
            f"{regras.PRAZO_DA_PENDENCIA_DIAS} dias: ele está nas suas pendências."
        )
    return "Autorização registrada como pendente. Ela fica nas suas pendências até a família decidir."


def _registrar_coleta(request, aluno, tipo, termo, forma, form):
    """Papel, WhatsApp ou pendente: um registro novo, com a prova e a trilha na mesma transação."""
    dados = form.cleaned_data
    autorizacao = Autorizacao(
        servico=request.servico, aluno=aluno, tipo=tipo, termo=termo,
        criado_por=request.user, atualizado_por=request.user, colhida_por=request.user,
        observacoes=(dados.get("observacoes") or "").strip(),
    )
    if forma == regras.PENDENTE:
        autorizacao.situacao = Situacao.PENDENTE
        acao, descricao = Acao.CRIOU, "Registrou a autorização como pendente: a família vai decidir depois"
    else:
        arquivo = dados["arquivo"]
        autorizacao.forma = forma
        autorizacao.responsavel = form.responsavel
        autorizacao.responsavel_nome = (dados.get("nome") or "").strip()
        autorizacao.responsavel_documento = (dados.get("documento") or "").strip()
        autorizacao.colhida_em = regras.agora_sem_microssegundos()
        autorizacao.impressao_digital = resumo_sha256(arquivo)
        autorizacao.arquivo = arquivo
        acao = Acao.ASSINOU
        if forma == Forma.PAPEL:
            autorizacao.situacao = Situacao.VALIDA if form.autorizou else Situacao.RECUSADA
            descricao = "Registrou o papel assinado: " + ("autorizou" if form.autorizou else "não autorizou")
        else:
            autorizacao.situacao = Situacao.PROVISORIA
            descricao = "Registrou o sim provisório por WhatsApp"
    with transaction.atomic():
        autorizacao.save()
        auditoria.registrar(
            request, acao, autorizacao,
            mudancas=auditoria.comparar(Autorizacao, {}, fotografar(autorizacao, CAMPOS_DA_TRILHA)),
            descricao=descricao,
        )
    return autorizacao


def _comecar_no_tablet(request, aluno, tipo, termo):
    """Cria a autorização pendente e prende o tablet na tela do termo (SEG-08)."""
    with transaction.atomic():
        autorizacao = Autorizacao.objects.create(
            servico=request.servico, aluno=aluno, tipo=tipo, termo=termo, forma=Forma.TABLET,
            situacao=Situacao.PENDENTE, colhida_por=request.user, criado_por=request.user,
            atualizado_por=request.user,
        )
        auditoria.registrar(
            request, Acao.CRIOU, autorizacao,
            mudancas=auditoria.comparar(Autorizacao, {}, fotografar(autorizacao, CAMPOS_DA_TRILHA)),
            descricao="Começou a assinatura no tablet: o tablet ficou com a família",
        )
    return _entrar_no_modo_assinatura(request, autorizacao)


def _entrar_no_modo_assinatura(request, autorizacao):
    url = reverse("autorizacoes:assinar", args=[autorizacao.pk])
    request.session[CHAVE_MODO_ASSINATURA] = url
    return redirect(url)


# ---------------------------------------------------------------- modo assinatura (SEG-08)

def _sair_do_modo_assinatura(request, *, ok=False, mensagem=""):
    """Encerra a sessão do professor e volta para a tela de entrar."""
    if request.user.is_authenticated:
        auditoria.registrar(
            request, Acao.SAIU, usuario=request.user, descricao="Saiu ao terminar o modo assinatura",
        )
    logout(request)
    if mensagem:
        messages.info(request, mensagem)
    destino = reverse("entrar")
    return HttpResponseRedirect(f"{destino}?assinatura=ok" if ok else destino)


@login_required
def assinar(request, pk):
    """A família lê o termo e assina com o dedo no tablet do professor (SEG-08).

    Enquanto a sessão está no modo assinatura, o middleware do núcleo devolve
    qualquer outro endereço para esta tela. Ao assinar ou cancelar, a sessão do
    professor é encerrada e a plataforma pede o login de novo. Fora do modo (por
    exemplo, para continuar uma assinatura interrompida), a tela pede ao professor
    para entregar o tablet antes de mostrar o termo.
    """
    url = reverse("autorizacoes:assinar", args=[pk])
    no_modo = request.session.get(CHAVE_MODO_ASSINATURA) == url
    if request.servico is None:
        if no_modo:
            return _sair_do_modo_assinatura(request)
        return render(request, "core/sem_vinculo.html", status=403)
    autorizacao = (
        Autorizacao.objects.select_related("aluno", "termo").filter(pk=pk, servico=request.servico).first()
    )
    if autorizacao is None:
        if no_modo:
            return _sair_do_modo_assinatura(request)
        raise Http404("Autorização não encontrada.")
    acesso = request.acesso
    pode = acesso.pode_editar(GRUPO) and acesso.pode_ver("identificacao")
    if not pode or not regras.assinavel_no_tablet(autorizacao):
        if no_modo:
            return _sair_do_modo_assinatura(
                request, mensagem="Esta autorização não está mais esperando assinatura. Entre de novo para continuar.",
            )
        if not pode:
            raise PermissionDenied("Seu papel não permite colher autorizações.")
        messages.info(request, "Esta autorização não está esperando assinatura no tablet.")
        return redirect("autorizacoes:detalhe", pk=autorizacao.pk)

    aluno = autorizacao.aluno
    if not no_modo:
        if request.method == "POST" and request.POST.get("acao") == "comecar":
            auditoria.registrar(
                request, Acao.OUTRO, autorizacao, descricao="Retomou a assinatura no tablet: o tablet ficou com a família",
            )
            return _entrar_no_modo_assinatura(request, autorizacao)
        return render(request, "autorizacoes/entregar_tablet.html", {
            "aluno": aluno,
            "tipo": autorizacao.tipo,
            "tipo_rotulo": autorizacao.get_tipo_display(),
            "tipo_minusculo": regras.tipo_em_minusculas(autorizacao.tipo),
            "termo": autorizacao.termo,
            "acao": url,
            "retomar": True,
            "url_voltar": reverse("autorizacoes:detalhe", args=[autorizacao.pk]),
        })

    if request.method == "POST" and request.POST.get("acao") == "cancelar":
        auditoria.registrar(
            request, Acao.OUTRO, autorizacao,
            descricao="Cancelou a assinatura no tablet; a autorização continua pendente",
        )
        return _sair_do_modo_assinatura(
            request, mensagem="Assinatura cancelada. A autorização continua pendente. Professor(a), entre de novo.",
        )

    responsaveis = responsaveis_para(request, aluno, so_legais=True)
    form = FormularioAssinatura(request.POST or None, responsaveis=responsaveis)
    if request.method == "POST" and form.is_valid():
        if _registrar_assinatura(request, autorizacao, form):
            return _sair_do_modo_assinatura(request, ok=True)
        return _sair_do_modo_assinatura(
            request, mensagem="Esta autorização não está mais esperando assinatura. Entre de novo para continuar.",
        )
    return render(request, "autorizacoes/assinar.html", {
        "autorizacao": autorizacao,
        "termo": autorizacao.termo,
        "primeiro_nome": regras.primeiro_nome(aluno),
        "form": form,
        "url": url,
    })


def _registrar_assinatura(request, autorizacao, form):
    """Grava a decisão, a assinatura e a prova (LGPD-03), com a trilha na mesma transação."""
    dados = form.cleaned_data
    with transaction.atomic():
        atual = Autorizacao.objects.select_for_update().select_related("termo").get(pk=autorizacao.pk)
        if not regras.assinavel_no_tablet(atual):
            return False
        antes = fotografar(atual, CAMPOS_DA_ASSINATURA)
        nome = (dados.get("nome") or "").strip()
        documento = (dados.get("documento") or "").strip()
        decisao = dados["decisao"]
        colhida_em = regras.agora_sem_microssegundos()
        atual.responsavel = form.responsavel
        atual.responsavel_nome = nome
        atual.responsavel_documento = documento
        atual.colhida_em = colhida_em
        atual.aparelho = (request.META.get("HTTP_USER_AGENT") or "")[:255]
        atual.situacao = Situacao.VALIDA if form.autoriza else Situacao.RECUSADA
        atual.impressao_digital = regras.impressao_digital_do_tablet(
            texto_do_termo=atual.termo.texto, versao_do_termo=atual.termo.versao_do_termo, nome=nome,
            documento=documento, decisao=decisao, colhida_em=colhida_em, assinatura=form.assinatura_png,
        )
        if dados.get("sem_assinatura_com_o_dedo") and not form.assinatura_png:
            confirmacao = (
                f"O responsável não conseguiu assinar com o dedo; {request.user.nome} confirmou que ele "
                "autorizou em voz alta."
            )
            atual.observacoes = f"{atual.observacoes}\n{confirmacao}".strip()
        if form.assinatura_png:
            atual.assinatura.save("assinatura.png", ContentFile(form.assinatura_png), save=False)
        atual.versao += 1
        atual.atualizado_por = request.user
        atual.save()
        decisao_legivel = "autorizou" if form.autoriza else "não autorizou"
        auditoria.registrar(
            request, Acao.ASSINOU, atual,
            mudancas=auditoria.comparar(Autorizacao, antes, fotografar(atual, CAMPOS_DA_ASSINATURA)),
            descricao=f"Família assinou no tablet: {decisao_legivel}",
        )
    return True


# ---------------------------------------------------------------- revogar (RF-29, LGPD-04)

@exige(EDITAR)
def revogar(request, pk):
    autorizacao = get_object_or_404(
        Autorizacao.objects.select_related("aluno", "colhida_por"), pk=pk, servico=request.servico
    )
    aluno = autorizacao.aluno
    atual = autorizacao_atual(aluno, autorizacao.tipo)
    if not regras.pode_revogar(autorizacao, atual):
        messages.info(request, "Só a autorização atual, válida ou provisória, pode ser revogada.")
        return redirect("autorizacoes:detalhe", pk=autorizacao.pk)
    form = FormularioRevogacao(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            atual = Autorizacao.objects.select_for_update().get(pk=autorizacao.pk)
            if atual.situacao not in regras.SITUACOES_QUE_SE_REVOGAM:
                messages.info(request, "Esta autorização mudou enquanto você preenchia. Confira a situação atual.")
                return redirect("autorizacoes:detalhe", pk=autorizacao.pk)
            antes = fotografar(atual, CAMPOS_DA_REVOGACAO)
            atual.situacao = Situacao.REVOGADA
            atual.revogada_em = timezone.now()
            atual.revogacao_motivo = form.cleaned_data["revogacao_motivo"].strip()
            atual.versao += 1
            atual.atualizado_por = request.user
            atual.save()
            auditoria.registrar(
                request, Acao.ALTEROU, atual,
                mudancas=auditoria.comparar(Autorizacao, antes, fotografar(atual, CAMPOS_DA_REVOGACAO)),
                motivo=atual.revogacao_motivo,
                descricao="Registrou a revogação pedida pela família",
            )
        if atual.tipo == Tipo.CONTATO_ESCOLA:
            messages.success(request, "Revogação registrada. A partir de agora nada mais é enviado à escola sobre este aluno.")
        else:
            messages.success(request, "Revogação registrada. Para voltar a valer, a família precisa autorizar de novo.")
        return redirect(url_da_secao(aluno))
    return render(request, "autorizacoes/revogar.html", {
        "autorizacao": autorizacao,
        "aluno": aluno,
        "form": form,
        "tipo_minusculo": regras.tipo_em_minusculas(autorizacao.tipo),
    })


# ---------------------------------------------------------------- comprovante

class DetalheDaAutorizacao(AcessoMixin, DoServicoMixin, DetailView):
    """Comprovante de uma coleta: o que a família viu, quem autorizou, quem colheu, quando e a prova (LGPD-03)."""

    grupo = GRUPO
    modo = VER
    model = Autorizacao
    template_name = "autorizacoes/detalhe.html"
    context_object_name = "autorizacao"

    def tem_permissao(self, request):
        return super().tem_permissao(request) and request.acesso.pode_ver("identificacao")

    def get_queryset(self):
        return super().get_queryset().select_related("aluno", "termo", "colhida_por", "responsavel")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        autorizacao = self.object
        aluno = autorizacao.aluno
        atual = autorizacao_atual(aluno, autorizacao.tipo)
        e_atual = atual is not None and atual.pk == autorizacao.pk
        pode_editar = self.request.acesso.pode_editar(GRUPO)
        contexto.update({
            "aluno": aluno,
            "atual": atual,
            "e_atual": e_atual,
            "tipo_minusculo": regras.tipo_em_minusculas(autorizacao.tipo),
            "confere": regras.conferir_impressao_digital(autorizacao),
            "pode_revogar": pode_editar and regras.pode_revogar(autorizacao, atual),
            "pode_colher": pode_editar and e_atual and regras.pode_colher(atual),
            "pode_continuar": pode_editar and e_atual and regras.assinavel_no_tablet(autorizacao),
            "e_imagem": _e_imagem(autorizacao.arquivo),
            "eventos": eventos_do_objeto(self.request, autorizacao),
        })
        return contexto


def _e_imagem(campo):
    nome = (campo.name or "").lower() if campo else ""
    return nome.endswith((".jpg", ".jpeg", ".png", ".webp"))


# ---------------------------------------------------------------- arquivos

def _nome_para_baixar(autorizacao, campo, base):
    nome = campo.name or ""
    extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else "bin"
    return f"{base}-{autorizacao.pk}-{autorizacao.tipo.replace('_', '-')}.{extensao}"


@exige(VER, identificacao=False)
@require_safe
def arquivo(request, pk):
    """Foto do papel ou conversa do WhatsApp; cada abertura vai para a trilha (SEG-04)."""
    autorizacao = get_object_or_404(Autorizacao, pk=pk, servico=request.servico)
    if not autorizacao.arquivo:
        raise Http404("Esta autorização não tem arquivo.")
    base = "papel-assinado" if autorizacao.forma == Forma.PAPEL else "conversa-whatsapp"
    resposta = servir_arquivo(autorizacao.arquivo, _nome_para_baixar(autorizacao, autorizacao.arquivo, base))
    if request.method == "GET":
        descricao = "Abriu a foto do papel assinado" if autorizacao.forma == Forma.PAPEL else "Abriu a conversa do WhatsApp"
        auditoria.registrar(request, Acao.BAIXOU_ARQUIVO, autorizacao, descricao=descricao)
    return resposta


@exige(VER, identificacao=False)
@require_safe
def imagem_assinatura(request, pk):
    """A imagem da assinatura feita no tablet; mostrada no comprovante e registrada na trilha."""
    autorizacao = get_object_or_404(Autorizacao, pk=pk, servico=request.servico)
    if not autorizacao.assinatura:
        raise Http404("Esta autorização não tem assinatura desenhada.")
    resposta = servir_arquivo(
        autorizacao.assinatura, _nome_para_baixar(autorizacao, autorizacao.assinatura, "assinatura")
    )
    if request.method == "GET":
        auditoria.registrar(request, Acao.BAIXOU_ARQUIVO, autorizacao, descricao="Viu a imagem da assinatura")
    return resposta

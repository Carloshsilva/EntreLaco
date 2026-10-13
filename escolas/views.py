"""Telas das escolas de origem (RF-13, RF-14, SEG-05).

A base de escolas é comum a todos os serviços: qualquer serviço encontra a mesma
escola, com os dados públicos. O contato confirmado (`ContatoEscola`) é de cada
serviço e sempre se busca por `request.servico`; o de outro serviço nunca aparece.
As telas pedem ao menos ver "Contatos das escolas"; cadastrar escola e mexer no
contato pedem editar esse tipo de dado.
"""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView

from core import auditoria
from core.permissoes import EDITAR
from core.views import eventos_do_objeto
from core.views_base import AcessoMixin, CriarComAuditoriaMixin, DoServicoMixin, EditarComAuditoriaMixin

from . import consultas
from .formularios import FormularioContatoBase, FormularioEscola
from .models import ContatoEscola, Escola

GRUPO = "escola_contato"
POR_PAGINA = 30
CAMPOS_DO_CONTATO = ["quem_atende", "email", "telefone", "observacoes", "situacao"]


def _ve_alunos_da_escola(acesso):
    """Ligar aluno e escola mostra identificação e vida escolar: só quem vê os dois (RF-07)."""
    return acesso.pode_ver("identificacao") and acesso.pode_ver("escolar")


# ---------------------------------------------------------------- lista

class ListaDeEscolas(AcessoMixin, TemplateView):
    """Lista com busca enquanto digita (nome, código INEP ou município) e filtros (RF-13)."""

    grupo = GRUPO
    template_name = "escolas/lista.html"

    def get(self, request, *args, **kwargs):
        servico = request.servico
        q = request.GET.get("q", "").strip()[:100]
        ve_alunos = request.acesso.pode_ver("escolar")
        com_alunos = ve_alunos and request.GET.get("com_alunos") == "1"
        precisa = request.GET.get("precisa") == "1"

        escolas = consultas.filtrar_por_busca(Escola.objects.all(), q)
        if com_alunos:
            escolas = consultas.filtrar_com_alunos_ativos(escolas, servico)
        if precisa:
            escolas = consultas.filtrar_contato_pendente(escolas, servico)
        escolas = consultas.com_situacao_do_contato(escolas, servico).only(
            "codigo_inep", "nome", "rede", "municipio", "uf", "funcionamento"
        ).order_by("nome", "pk")
        pagina = Paginator(escolas, POR_PAGINA).get_page(request.GET.get("pagina"))

        contexto = self.get_context_data(
            pagina=pagina, q=q, ve_alunos=ve_alunos, com_alunos=com_alunos, precisa=precisa,
            filtrando=bool(q or com_alunos or precisa),
        )
        so_resultados = bool(request.htmx) and request.htmx.target == "resultados" and not (
            request.htmx.boosted or request.htmx.history_restore_request
        )
        template = "escolas/_resultados.html" if so_resultados else self.template_name
        resposta = render(request, template, contexto)
        patch_vary_headers(resposta, ["HX-Request", "HX-Target"])
        return resposta


# ---------------------------------------------------------------- detalhe

class DetalheDaEscola(AcessoMixin, DetailView):
    """Dados públicos, o contato deste serviço e os alunos ativos do serviço na escola (RF-13, RF-14)."""

    grupo = GRUPO
    model = Escola  # base comum: não se filtra por serviço; o contato, sim
    template_name = "escolas/detalhe.html"
    context_object_name = "escola"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        escola = self.object
        request = self.request
        contato = consultas.contato_do_servico(request.servico, escola)
        alunos = None
        if _ve_alunos_da_escola(request.acesso):
            alunos = list(
                consultas.alunos_ativos_do_servico(request.servico).filter(escola=escola)
                .only("nome", "nome_social", "ano_escolar", "turma").order_by("nome")
            )
        eventos = eventos_do_objeto(request, escola)
        if contato is not None:
            eventos += eventos_do_objeto(request, contato)
            eventos.sort(key=lambda e: (e.criado_em, e.pk), reverse=True)
        contexto.update({"contato": contato, "alunos": alunos, "eventos": eventos[:20]})
        return contexto


# ---------------------------------------------------------------- cadastrar escola

def _proximo_seguro(request):
    """Endereço de volta pedido por outra tela (?proximo=), só se for deste site."""
    proximo = request.POST.get("proximo") or request.GET.get("proximo") or ""
    if proximo and url_has_allowed_host_and_scheme(proximo, allowed_hosts={request.get_host()},
                                                   require_https=request.is_secure()):
        return proximo
    return ""


class NovaEscola(AcessoMixin, CreateView):
    """Cadastrar escola que não está na base comum (RF-13). Fica na trilha do serviço que cadastrou."""

    grupo = GRUPO
    modo = EDITAR
    model = Escola
    form_class = FormularioEscola
    template_name = "escolas/escola_form.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["proximo"] = _proximo_seguro(self.request)
        contexto["secoes"] = [
            {"titulo": "Identificação", "campos": ["codigo_inep", "nome", "rede"]},
            {"titulo": "Endereço e telefone", "campos": ["endereco", "bairro", "municipio", "uf", "cep", "telefone"]},
        ]
        return contexto

    def form_valid(self, form):
        request = self.request
        with transaction.atomic():
            escola = form.save(commit=False)
            # A base é comum: o nome do serviço que cadastrou não aparece para os outros (SEG-05).
            escola.fonte = "Cadastrada por um serviço da EntreLaço"
            escola.save()
            campos = [nome for nome in form.fields if nome in FormularioEscola.Meta.fields]
            mudancas = auditoria.comparar(Escola, {}, auditoria.fotografar(escola, campos))
            auditoria.registrar(
                request, auditoria.Acao.CRIOU, escola, mudancas=mudancas, servico=request.servico,
                descricao="Cadastrou a escola na base comum",
            )
        self.object = escola
        messages.success(request, "Escola cadastrada. Agora ela aparece na busca de todos os serviços.")
        return HttpResponseRedirect(_proximo_seguro(request) or reverse("escolas:detalhe", args=[escola.pk]))


# ---------------------------------------------------------------- contato do serviço

class ContatoMixin:
    """Comum a cadastrar e editar o contato. Vem antes de AcessoMixin nas classes, para valer o `grupo`."""

    grupo = GRUPO
    modo = EDITAR
    model = ContatoEscola
    campos = CAMPOS_DO_CONTATO
    form_base = FormularioContatoBase
    widgets = {"situacao": forms.RadioSelect, "observacoes": forms.Textarea(attrs={"rows": 3})}
    template_name = "escolas/contato_form.html"
    confirmou = False

    @cached_property
    def escola(self):
        return get_object_or_404(Escola, pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["escola"] = self.escola
        return contexto

    def get_success_url(self):
        return reverse("escolas:detalhe", args=[self.escola.pk])

    def marcar_confirmacao(self, obj, mudou):
        """Salvar como "Atualizado" é confirmar o contato: guarda quem e quando (SEG-03)."""
        if obj.situacao == ContatoEscola.Situacao.ATUALIZADO and (mudou or obj.confirmado_em is None):
            obj.confirmado_em = timezone.localdate()
            obj.confirmado_por = self.request.user
            self.confirmou = True

    def depois_de_salvar(self, obj, form, criado):
        if self.confirmou:
            auditoria.registrar(self.request, auditoria.Acao.VALIDOU, obj, descricao="Confirmou o contato da escola")


class CriarContato(ContatoMixin, AcessoMixin, CriarComAuditoriaMixin, CreateView):
    mensagem_sucesso = "Contato salvo."

    def preparar_objeto(self, obj, form):
        obj.escola = self.escola
        self.marcar_confirmacao(obj, mudou=True)

    def form_valid(self, form):
        if ContatoEscola.objects.filter(servico=self.request.servico, escola=self.escola).exists():
            return self._ja_existe()
        try:
            return super().form_valid(form)
        except IntegrityError:
            return self._ja_existe()

    def _ja_existe(self):
        messages.warning(
            self.request,
            "Outra pessoa do serviço cadastrou o contato desta escola enquanto você digitava. "
            "Confira o que ela salvou e edite, se precisar.",
        )
        return redirect("escolas:contato", pk=self.escola.pk)


class EditarContato(ContatoMixin, AcessoMixin, DoServicoMixin, EditarComAuditoriaMixin, UpdateView):
    mensagem_sucesso = "Contato salvo."

    def get_object(self, queryset=None):
        # Só o contato deste serviço (DoServicoMixin); o de outro serviço não existe para quem pede.
        return get_object_or_404(self.get_queryset().select_related("escola"), escola=self.escola)

    def preparar_objeto(self, obj, form):
        mudou_situacao = form.initial.get("situacao") != obj.situacao
        mudou_dados = any(nome in form.changed_data for nome in CAMPOS_DO_CONTATO if nome != "situacao")
        self.marcar_confirmacao(obj, mudou=mudou_situacao or mudou_dados)


_criar_contato = CriarContato.as_view()
_editar_contato = EditarContato.as_view()


def contato(request, pk):
    """Cadastrar ou editar o contato do serviço para a escola: um só endereço para as duas coisas."""
    servico = getattr(request, "servico", None)
    existe = (
        request.user.is_authenticated and servico is not None
        and ContatoEscola.objects.filter(servico=servico, escola_id=pk).exists()
    )
    return (_editar_contato if existe else _criar_contato)(request, pk=pk)


@login_required
@require_POST
def confirmar_contato(request, pk):
    """Confirma que o contato do serviço está certo: situação atualizado, hoje, por quem confirmou (RF-14)."""
    if request.servico is None:
        return render(request, "core/sem_vinculo.html", status=403)
    if not request.acesso.pode_editar(GRUPO):
        raise PermissionDenied("Seu papel não permite confirmar o contato das escolas.")
    escola = get_object_or_404(Escola, pk=pk)
    with transaction.atomic():
        contato_atual = ContatoEscola.objects.select_for_update().filter(servico=request.servico, escola=escola).first()
        if contato_atual is None or not (contato_atual.email or contato_atual.telefone):
            messages.warning(
                request, "Para confirmar, o contato precisa ter e-mail ou telefone. Preencha e salve o contato antes."
            )
            return redirect("escolas:contato", pk=escola.pk)
        antes = auditoria.fotografar(contato_atual, ["situacao"])
        contato_atual.situacao = ContatoEscola.Situacao.ATUALIZADO
        contato_atual.confirmado_em = timezone.localdate()
        contato_atual.confirmado_por = request.user
        contato_atual.atualizado_por = request.user
        contato_atual.versao += 1
        contato_atual.save()
        mudancas = auditoria.comparar(ContatoEscola, antes, auditoria.fotografar(contato_atual, ["situacao"]))
        auditoria.registrar(
            request, auditoria.Acao.VALIDOU, contato_atual, mudancas=mudancas, descricao="Confirmou o contato da escola"
        )
    messages.success(request, "Contato confirmado.")
    return redirect("escolas:detalhe", pk=escola.pk)


# ---------------------------------------------------------------- busca para outros formulários

@login_required
@require_GET
def buscar(request):
    """Trecho HTML com opções de escola, para campos de escola com busca em outros módulos.

    Parâmetros:
    - `q`: o que a pessoa digitou (nome, município ou código INEP; pelo menos 3 letras ou números).
      Com `campo=<nome>`, o texto vem do parâmetro com esse nome (é o que o HTMX manda de um input).
    - `formato`: `select` (padrão) devolve `<option value="<pk>">Nome · Município/UF · INEP</option>`,
      para trocar as opções de um `<select>`; `datalist` devolve `<option value="12345678 · Nome (Município/UF)">`,
      para o `<datalist>` do `CampoEscola`.

    Exige login e serviço. Só devolve dados públicos da base comum; nunca o contato de um serviço.
    """
    if request.servico is None:
        return render(request, "core/sem_vinculo.html", status=403)
    q = request.GET.get("q")
    campo = request.GET.get("campo", "")
    if q is None and campo:
        q = request.GET.get(campo, "")
    q = (q or "").strip()[:100]
    formato = "datalist" if request.GET.get("formato") == "datalist" else "select"
    escolas = consultas.buscar_escolas(q)
    resposta = render(request, "escolas/_opcoes.html", {
        "escolas": escolas,
        "formato": formato,
        "curta": not consultas.busca_suficiente(q),
        "q": q,
    })
    patch_vary_headers(resposta, ["HX-Request"])
    return resposta

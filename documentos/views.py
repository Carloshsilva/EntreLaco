"""Telas dos documentos digitalizados do aluno (RF-12).

- Ver pede ver "Documentos digitalizados"; enviar e editar os dados pedem editar.
- Toda consulta filtra por `request.servico`; documento ou aluno de outro serviço dá 404.
- O arquivo fica fora da pasta pública e só sai pela view `arquivo`, que confere login,
  serviço e permissão e registra cada abertura na trilha (`Acao.BAIXOU_ARQUIVO`).
- Não há exclusão nesta versão: a regra de guarda espera o advogado (LGPD-08).
"""
import datetime

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.text import slugify
from django.views.decorators.http import require_safe
from django.views.generic import CreateView, DetailView, UpdateView

from alunos.models import Aluno
from core import auditoria
from core.arquivos import e_imagem_guardada, resumo_sha256, servir_arquivo
from core.formularios import DATA
from core.models import EventoAuditoria
from core.permissoes import EDITAR
from core.views import eventos_do_objeto
from core.views_base import AcessoMixin, CriarComAuditoriaMixin, DoServicoMixin, EditarComAuditoriaMixin

from .formularios import TIPOS_ACEITOS, FormularioDocumentoBase
from .models import Documento

GRUPO = "documentos"
CAMPOS_DO_ENVIO = ["tipo", "titulo", "arquivo", "data_documento", "observacoes"]
CAMPOS_DA_EDICAO = ["tipo", "titulo", "data_documento", "observacoes"]


def e_imagem(documento):
    return e_imagem_guardada(documento.arquivo.name or "")


def nome_para_baixar(documento):
    """Nome do arquivo que a pessoa recebe: o título, sem o nome do aluno nem o caminho interno."""
    nome = documento.arquivo.name or ""
    extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    base = slugify(documento.titulo)[:80] or "documento"
    return f"{base}.{extensao}" if extensao else base


class DocumentoMixin:
    grupo = GRUPO
    modo = EDITAR
    model = Documento
    form_base = FormularioDocumentoBase
    widgets = {
        "arquivo": forms.FileInput(attrs={"accept": TIPOS_ACEITOS}),
        "data_documento": DATA,
        "observacoes": forms.Textarea(attrs={"rows": 3}),
    }
    template_name = "documentos/documento_form.html"

    def get_success_url(self):
        return reverse("documentos:detalhe", args=[self.object.pk])


class NovoDocumento(DocumentoMixin, AcessoMixin, CriarComAuditoriaMixin, CreateView):
    """Enviar a foto ou o PDF de um documento para o histórico do aluno (RF-12)."""

    campos = CAMPOS_DO_ENVIO
    mensagem_sucesso = "Documento guardado no histórico do aluno."

    @cached_property
    def aluno(self):
        return get_object_or_404(
            Aluno.objects.only("id", "nome", "nome_social", "servico_id"),
            pk=self.kwargs["aluno_pk"], servico=self.request.servico,
        )

    def get(self, request, *args, **kwargs):
        self.aluno  # noqa: B018 - 404 antes de montar a tela
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.aluno  # noqa: B018 - 404 antes de ler o arquivo enviado
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["aluno"] = self.aluno
        return contexto

    def preparar_objeto(self, obj, form):
        arquivo = form.cleaned_data["arquivo"]
        obj.aluno = self.aluno
        obj.tamanho = arquivo.size
        obj.impressao_digital = resumo_sha256(arquivo)


class EditarDocumento(DocumentoMixin, AcessoMixin, DoServicoMixin, EditarComAuditoriaMixin, UpdateView):
    """Editar os dados do documento, com motivo. O arquivo não muda: para outro arquivo, envie outro documento."""

    campos = CAMPOS_DA_EDICAO
    mensagem_sucesso = "Dados do documento salvos."

    def get_queryset(self):
        return super().get_queryset().select_related("aluno")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["aluno"] = self.object.aluno
        return contexto


class DetalheDoDocumento(AcessoMixin, DoServicoMixin, DetailView):
    grupo = GRUPO
    model = Documento
    template_name = "documentos/detalhe.html"
    context_object_name = "documento"

    def get_queryset(self):
        return super().get_queryset().select_related("aluno", "criado_por")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update({
            "aluno": self.object.aluno,
            "e_imagem": e_imagem(self.object),
            "eventos": eventos_do_objeto(self.request, self.object),
        })
        return contexto


def _ja_viu_a_previa(request, documento):
    """A mesma pessoa já viu a prévia deste documento há pouco (dentro do tempo de uma sessão)?"""
    desde = timezone.now() - datetime.timedelta(seconds=settings.SESSION_COOKIE_AGE)
    return EventoAuditoria.objects.filter(
        servico=request.servico, usuario=request.user, acao=auditoria.Acao.BAIXOU_ARQUIVO,
        modelo=Documento._meta.label, objeto_id=str(documento.pk), criado_em__gte=desde,
    ).exists()


@login_required
@require_safe
def arquivo(request, pk):
    """Entrega o arquivo e registra a abertura na trilha (SEG-04).

    Abrir ou baixar fica sempre na trilha. `?previa=1` é a foto mostrada na própria tela
    do documento: também fica na trilha, porque quem abriu a tela viu o conteúdo, mas uma
    vez por pessoa a cada sessão, para o histórico não se encher a cada visita.
    """
    if request.servico is None:
        return render(request, "core/sem_vinculo.html", status=403)
    if not request.acesso.pode_ver(GRUPO):
        raise PermissionDenied("Seu papel não permite abrir documentos digitalizados.")
    documento = get_object_or_404(Documento, pk=pk, servico=request.servico)
    previa = request.GET.get("previa") == "1"
    resposta = servir_arquivo(documento.arquivo, nome_para_baixar(documento))
    if request.method == "GET" and not (previa and _ja_viu_a_previa(request, documento)):
        auditoria.registrar(
            request, auditoria.Acao.BAIXOU_ARQUIVO, documento,
            descricao="Viu a prévia na tela do documento" if previa else "Abriu o arquivo",
        )
    return resposta

"""Telas de quem configura o serviço: papéis e permissões, parâmetros do serviço e componentes curriculares.

RF-06 (o serviço cadastra papéis e permissões), RF-07 (permissão por tipo de dado), RF-62 (parâmetros
do serviço) e SEG-04 (liberação de permissão na trilha). Todas exigem a permissão de configurar.
"""
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import NoReverseMatch, reverse
from django.utils.functional import cached_property
from django.views.generic import CreateView, FormView, ListView, TemplateView, UpdateView

from core import auditoria
from core.models import EventoAuditoria, Papel, Servico
from core.permissoes import ACOES, GRUPOS_DE_DADOS
from core.views import eventos_do_objeto
from core.views_base import AcessoMixin, CriarComAuditoriaMixin, DoServicoMixin, EditarComAuditoriaMixin

from .edicao import EdicaoSemVersaoMixin, mudancas_entre
from .formularios import ConfiguracaoForm, PapelEditarForm, PapelForm, formulario_de_componente
from .models import ComponenteCurricular

Acao = auditoria.Acao


def _url_se_existir(nome):
    """URL de uma tela de outro módulo, ou None se o módulo estiver desligado (RNF-08)."""
    try:
        return reverse(nome)
    except NoReverseMatch:
        return None


# ---------------------------------------------------------------- configuração do serviço

class ConfiguracaoView(AcessoMixin, EdicaoSemVersaoMixin, FormView):
    """Parâmetros do serviço (RF-62) e atalhos para os cadastros que quem configura mantém."""

    exige_configurar = True
    form_class = ConfiguracaoForm
    template_name = "equipe/configuracao.html"
    mensagem_sucesso = "Configuração salva."

    def get_initial(self):
        return self.valores_brutos(self.request.servico)

    def get_success_url(self):
        return reverse("equipe:configuracao")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        servico = self.request.servico
        atalhos = [
            {"titulo": "Papéis e permissões", "texto": "O que cada papel vê e edita, por tipo de dado.",
             "url": reverse("equipe:papeis"), "icone": "seguranca"},
            {"titulo": "Componentes curriculares", "texto": "O que os professores ensinam.",
             "url": reverse("equipe:componentes"), "icone": "aula"},
            {"titulo": "Termos de autorização", "texto": "Os textos que a família lê e assina.",
             "url": _url_se_existir("autorizacoes:termos"), "icone": "assinatura"},
            {"titulo": "Lista da BNCC", "texto": "Eixos e habilidades usados no registro de aula.",
             "url": _url_se_existir("aulas:habilidades"), "icone": "documento"},
        ]
        contexto.update({
            "servico": servico,
            "atalhos": [a for a in atalhos if a["url"]],
            "secoes": [
                {"titulo": "Aulas", "campos": ["minutos_por_aula", "bncc_ativa"]},
                {"titulo": "Alunos", "campos": ["prazo_revisao_ativo_dias", "motivos_saida"]},
            ],
            "eventos": eventos_do_objeto(self.request, servico),
        })
        return contexto

    def objeto_atual(self):
        return self.request.servico

    def travar(self):
        return Servico.objects.select_for_update().get(pk=self.request.servico.pk)

    def valores_salvos(self, servico):
        return ConfiguracaoForm.valores_salvos(servico)

    def valores_brutos(self, servico):
        return ConfiguracaoForm.valores_brutos(servico)

    def ultimo_evento(self, servico):
        return EventoAuditoria.objects.filter(
            servico=servico, modelo=Servico._meta.label, objeto_id=str(servico.pk), acao=Acao.ALTEROU
        ).first()

    def salvar(self, servico, form, mudancas):
        form.aplicar(servico)
        servico.save(update_fields=["minutos_por_aula", "bncc_ativa", "prazo_revisao_ativo_dias", "motivos_saida"])
        # Servico não herda ModeloDoServico: a trilha é gravada aqui, na mesma transação.
        auditoria.registrar(
            self.request, Acao.ALTEROU, servico, servico=servico, mudancas=mudancas,
            motivo=form.cleaned_data["motivo_alteracao"], descricao="Configuração do serviço",
        )


# ---------------------------------------------------------------- papéis

class PapeisView(AcessoMixin, TemplateView):
    exige_configurar = True
    template_name = "equipe/papeis.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["papeis"] = (
            Papel.objects.filter(servico=self.request.servico)
            .annotate(pessoas=Count("vinculos", filter=Q(vinculos__ativo=True)))
            .order_by("nome")
        )
        return contexto


class PapelFormularioMixin:
    template_name = "equipe/papel_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(servico=self.request.servico, papel=self.papel)
        return kwargs

    def get_success_url(self):
        return reverse("equipe:papeis")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update({
            "papel": self.papel,
            "tipos_de_dado": GRUPOS_DE_DADOS,
            "acoes_do_configurar": [nome for codigo, nome in ACOES
                                    if codigo in {"gerir_equipe", "ver_trilha", "ver_tarefas_de_todos"}],
        })
        return contexto


class PapelNovoView(AcessoMixin, PapelFormularioMixin, FormView):
    """Cria um papel. Nasce sem a permissão de configurar, mesmo que o envio tente mandar (RF-03)."""

    exige_configurar = True
    form_class = PapelForm
    papel = None

    def form_valid(self, form):
        with transaction.atomic():
            papel = form.aplicar(Papel(pode_configurar=False))
            papel.pode_configurar = False
            papel.save()
            auditoria.registrar(self.request, Acao.CRIOU, papel, descricao=f"Criou o papel {papel.nome}")
            auditoria.registrar(
                self.request, Acao.LIBEROU_PERMISSAO, papel,
                mudancas=mudancas_entre({}, form.valores_legiveis(), form),
                descricao=f"Permissões do papel {papel.nome}",
            )
        messages.success(self.request, f"Papel {papel.nome} criado.")
        return redirect(self.get_success_url())


class PapelEditarView(AcessoMixin, PapelFormularioMixin, EdicaoSemVersaoMixin, FormView):
    """Edita nome, acessos por tipo de dado e ações. Registra Acao.LIBEROU_PERMISSAO com o antes e o depois."""

    exige_configurar = True
    form_class = PapelEditarForm
    mensagem_sucesso = "Papel salvo."

    @cached_property
    def papel(self):
        return get_object_or_404(Papel, pk=self.kwargs["pk"], servico=self.request.servico)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["eventos"] = eventos_do_objeto(self.request, self.papel)
        contexto["pessoas_com_o_papel"] = self.papel.vinculos.filter(ativo=True).count()
        return contexto

    def objeto_atual(self):
        return self.papel

    def travar(self):
        return Papel.objects.select_for_update().get(pk=self.papel.pk)

    def valores_salvos(self, papel):
        return PapelForm.valores_salvos(papel)

    def valores_brutos(self, papel):
        return PapelForm.valores_brutos(papel)

    def ultimo_evento(self, papel):
        return EventoAuditoria.objects.filter(
            servico=self.request.servico, modelo=Papel._meta.label, objeto_id=str(papel.pk)
        ).first()

    def salvar(self, papel, form, mudancas):
        pode_configurar = papel.pode_configurar
        form.aplicar(papel)
        papel.pode_configurar = pode_configurar  # só o administrador da plataforma muda (RF-03)
        papel.save()
        permissoes = {nome: m for nome, m in mudancas.items() if nome not in {"nome", "descricao"}}
        auditoria.registrar(
            self.request, Acao.LIBEROU_PERMISSAO if permissoes else Acao.ALTEROU, papel,
            mudancas=mudancas, motivo=form.cleaned_data["motivo_alteracao"],
            descricao=f"Permissões do papel {papel.nome}" if permissoes else f"Dados do papel {papel.nome}",
        )


# ---------------------------------------------------------------- componentes curriculares

class ComponentesView(AcessoMixin, DoServicoMixin, ListView):
    exige_configurar = True
    model = ComponenteCurricular
    template_name = "equipe/componentes.html"
    context_object_name = "componentes"

    def get_queryset(self):
        return super().get_queryset().annotate(total_professores=Count("professores", distinct=True)).order_by("nome")


class ComponenteFormularioMixin:
    model = ComponenteCurricular
    template_name = "equipe/componente_form.html"

    def get_success_url(self):
        return reverse("equipe:componentes")


class ComponenteNovoView(AcessoMixin, ComponenteFormularioMixin, CriarComAuditoriaMixin, CreateView):
    exige_configurar = True
    mensagem_sucesso = "Componente curricular cadastrado."

    def get_form_class(self):
        return formulario_de_componente(self.request.servico)


class ComponenteEditarView(AcessoMixin, DoServicoMixin, ComponenteFormularioMixin, EditarComAuditoriaMixin, UpdateView):
    exige_configurar = True
    mensagem_sucesso = "Componente curricular salvo."

    def get_form_class(self):
        return formulario_de_componente(self.request.servico, edicao=True)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["eventos"] = eventos_do_objeto(self.request, self.object)
        return contexto

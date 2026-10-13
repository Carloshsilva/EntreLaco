"""Telas de aulas (RF-15, RF-16, RF-19, RF-44, RF-55).

- Lista com filtros e a conta de aulas pela regra do serviço.
- Registrar aula (a ação mais usada, no leito), marcar aula, registrar a aula
  marcada a partir da agenda e dizer que ela não aconteceu.
- Detalhe com fotos e histórico, edição com motivo e conflito (RNF-04).
- Fotos só saem por `foto`, que confere login, serviço e permissão.
- Lista da BNCC do serviço, para quem configura (RF-16).
"""
import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldDoesNotExist, PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView

from alunos.models import Aluno
from core import auditoria
from core.arquivos import servir_arquivo
from core.models import EventoAuditoria
from core.permissoes import EDITAR
from core.registro import pendencias_para
from core.views import eventos_do_objeto
from core.views_base import AcessoMixin, CriarComAuditoriaMixin, DoServicoMixin, EditarComAuditoriaMixin

from . import regras
from .formularios import (
    CAMPOS_DA_NAO_REALIZADA,
    CAMPOS_DE_MARCAR,
    CAMPOS_DO_REGISTRO,
    FotosForm,
    RegistroDeAulaForm,
    formulario_da_aula,
    formulario_da_habilidade,
)
from .models import Aula, FotoDaAula, HabilidadeBNCC

Acao = auditoria.Acao
Situacao = Aula.Situacao
logger = logging.getLogger(__name__)

SECOES_DO_REGISTRO = [
    {"titulo": "Aluno e horário", "campos": ["aluno", "aluno_novo", "professor", "data", "hora_inicio", "duracao_minutos"]},
    {"titulo": "O que foi trabalhado", "campos": ["componentes", "conteudo", "participacao", "habilidades"]},
    {"titulo": "Fotos das atividades", "campos": ["novas_fotos"],
     "ajuda": "Opcional. Também dá para adicionar fotos depois, no detalhe da aula."},
]
SECOES_DE_MARCAR = [{"titulo": "Aluno e horário", "campos": CAMPOS_DE_MARCAR}]

FILTROS_DE_SITUACAO = [
    ("", "Todas"),
    (Situacao.MARCADA, "Marcadas"),
    ("falta_registrar", "Marcadas que faltam registrar"),
    (Situacao.REGISTRADA, "Registradas"),
    (Situacao.NAO_REALIZADA, "Não aconteceram"),
]


# ---------------------------------------------------------------- ajudas

def _campos_auditados(form, extras=()):
    campos = [nome for nome in form.fields if nome != "motivo_alteracao" and _e_campo_da_aula(nome)]
    return campos + [c for c in extras if c not in campos]


def _e_campo_da_aula(nome):
    """Campo do próprio modelo (fora relações reversas, como Aula.fotos)."""
    try:
        return not Aula._meta.get_field(nome).auto_created
    except FieldDoesNotExist:
        return False


def salvar_fotos(request, aula, arquivos, legenda=""):
    """Uma FotoDaAula por foto já limpa (sem EXIF), cada uma com o seu evento na trilha."""
    fotos = []
    for arquivo in arquivos:
        foto = FotoDaAula(
            servico=request.servico, aula=aula, legenda=legenda, criado_por=request.user, atualizado_por=request.user,
        )
        foto.arquivo = arquivo
        foto.save()
        auditoria.registrar(
            request, Acao.CRIOU, foto, aluno=aula.aluno_id, descricao=f"Anexou uma foto à aula de {aula.data:%d/%m/%Y}",
            mudancas=auditoria.comparar(FotoDaAula, {}, auditoria.fotografar(foto, ["legenda"])),
        )
        fotos.append(foto)
    return fotos


def _texto_das_fotos(fotos):
    if not fotos:
        return ""
    return " com 1 foto" if len(fotos) == 1 else f" com {len(fotos)} fotos"


def aviso_da_ficha(request, aula):
    """Mensagem para quando o aluno da aula está com a ficha incompleta (RF-19).

    A pendência de completar a ficha é calculada pelo módulo de alunos; aqui só se
    confere, na lista de pendências de quem deu a aula, se ela está lá, para a
    mensagem nunca prometer o que não existe.
    """
    aluno = aula.aluno
    if aluno.ficha_completa:
        return None
    faltas = regras.faltas_da_ficha_visiveis(aluno, request.acesso)
    texto = "A ficha de " + aluno.nome_curto + " está incompleta"
    texto += f": falta {regras.juntar(faltas)}." if faltas else "."
    chave = f"ficha-{aluno.pk}-{aula.professor_id}"
    try:
        tem_pendencia = any(p.chave == chave for p in pendencias_para(request, usuario=aula.professor))
    except Exception:  # noqa: BLE001 - outro módulo com defeito não pode derrubar o registro já salvo
        logger.exception("Não deu para conferir a pendência da ficha do aluno %s", aluno.pk)
        tem_pendencia = False
    if tem_pendencia:
        quem = "você" if aula.professor_id == request.user.pk else aula.professor.nome_curto
        primeira = not Aula.objects.filter(aluno=aluno, situacao=Situacao.REGISTRADA).exclude(pk=aula.pk).exists()
        acao = "foi criada para" if primeira else "continua com"
        texto += " " + regras.frase(f"A pendência de completar a ficha {acao} {quem}")
    return texto


def eventos_da_aula(request, aula, limite=30):
    """Histórico da aula e das fotos dela, só com as mudanças que a pessoa pode ver."""
    fotos = [str(pk) for pk in aula.fotos.values_list("pk", flat=True)]
    filtro = Q(modelo=Aula._meta.label, objeto_id=str(aula.pk))
    if fotos:
        filtro |= Q(modelo=FotoDaAula._meta.label, objeto_id__in=fotos)
    eventos = list(EventoAuditoria.objects.filter(servico=request.servico).filter(filtro)[:limite])
    for evento in eventos:
        evento.mudancas_permitidas = auditoria.mudancas_visiveis(evento, request.acesso)
    return eventos


def _aluno_da_consulta(request):
    """Aluno pedido em ?aluno=, se for do serviço e puder receber aula."""
    valor = request.GET.get("aluno", "")
    if not valor.isdigit():
        return None
    return regras.alunos_que_recebem_aula(request.servico).filter(pk=int(valor)).first()


def _url_do_aluno(aluno):
    return regras.url_ou_none("alunos:detalhe", aluno.pk) if aluno else None


def _quando(aula):
    texto = f"{aula.data:%d/%m}"
    if aula.hora_inicio:
        texto += f" às {aula.hora_inicio:%H:%M}"
    return texto


# ---------------------------------------------------------------- lista

class ListaDeAulasView(AcessoMixin, TemplateView):
    """Aulas do período, com filtros e o total de aulas pela regra do serviço (RF-55)."""

    grupo = "aulas"
    template_name = "aulas/lista.html"
    por_pagina = 50

    def get_template_names(self):
        htmx = getattr(self.request, "htmx", None)
        if htmx and not htmx.boosted and htmx.target == "resultados":
            return ["aulas/_lista_resultados.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        request = self.request
        servico = request.servico
        hoje = regras.hoje()
        regra = regras.minutos_por_aula(servico)

        inicio_padrao, fim_padrao = regras.semana_de(hoje)
        de = regras.ler_data(request.GET.get("de"), inicio_padrao)
        ate = regras.ler_data(request.GET.get("ate"), fim_padrao)
        if de > ate:
            de, ate = ate, de

        pessoas = list(
            get_user_model().objects.filter(
                Q(vinculos__servico=servico, vinculos__ativo=True, is_active=True)
                | Q(pk__in=Aula.objects.filter(servico=servico).values("professor_id"))
            ).distinct().order_by("nome")
        )
        valor = request.GET.get("professor", "")
        professor = None
        if valor == "todos":
            escolha_professor = "todos"
        else:
            professor = next((p for p in pessoas if str(p.pk) == valor), None)
            if professor is None:
                professor = request.user if regras.da_aula(servico, request.user) else None
            escolha_professor = str(professor.pk) if professor else "todos"

        alunos = list(Aluno.objects.filter(servico=servico).only("pk", "nome", "nome_social", "leito").order_by("nome"))
        aluno = next((a for a in alunos if str(a.pk) == request.GET.get("aluno", "")), None)
        situacao = request.GET.get("situacao", "")
        if situacao not in dict(FILTROS_DE_SITUACAO):
            situacao = ""

        aulas = Aula.objects.filter(servico=servico, data__range=(de, ate))
        if professor is not None:
            aulas = aulas.filter(professor=professor)
        if aluno is not None:
            aulas = aulas.filter(aluno=aluno)
        if situacao == "falta_registrar":
            aulas = aulas.filter(situacao=Situacao.MARCADA, data__lt=hoje)
        elif situacao:
            aulas = aulas.filter(situacao=situacao)

        atendimentos, equivalentes = regras.somar_equivalentes(aulas, regra)
        por_situacao = dict(aulas.order_by().values_list("situacao").annotate(total=Count("id")))
        pagina = Paginator(
            aulas.select_related("aluno", "professor").order_by("-data", "-hora_inicio", "-pk"), self.por_pagina
        ).get_page(request.GET.get("pagina"))
        for aula in pagina:
            aula.equivalentes = (
                regras.aulas_equivalentes(aula.duracao_minutos, regra) if aula.situacao == Situacao.REGISTRADA else None
            )
            aula.falta_registrar = aula.situacao == Situacao.MARCADA and aula.data < hoje

        contexto.update({
            "de": de,
            "ate": ate,
            "pessoas": pessoas,
            "escolha_professor": escolha_professor,
            "professor": professor,
            "alunos": alunos,
            "aluno": aluno,
            "situacao": situacao,
            "situacoes": FILTROS_DE_SITUACAO,
            "pagina": pagina,
            "total": pagina.paginator.count,
            "resumo": regras.resumo_de_atendimentos(atendimentos, equivalentes, regra),
            "marcadas": por_situacao.get(Situacao.MARCADA, 0),
            "nao_realizadas": por_situacao.get(Situacao.NAO_REALIZADA, 0),
            "regra": regra,
            "e_esta_semana": (de, ate) == (inicio_padrao, fim_padrao),
        })
        return contexto


# ---------------------------------------------------------------- registrar e marcar

class RegistrarAulaView(AcessoMixin, CriarComAuditoriaMixin, CreateView):
    """Registrar aula dada (RF-15), inclusive de aluno ainda não cadastrado (RF-19)."""

    grupo = "aulas"
    modo = EDITAR
    model = Aula
    template_name = "aulas/registrar.html"
    mensagem_sucesso = "Aula registrada."

    def get_form_class(self):
        return formulario_da_aula(self.request, CAMPOS_DO_REGISTRO, base=RegistroDeAulaForm)

    @cached_property
    def aluno_pedido(self):
        return _aluno_da_consulta(self.request)

    def get_initial(self):
        inicial = {
            "data": regras.hoje(),
            "duracao_minutos": regras.minutos_por_aula(self.request.servico),
            "professor": self.request.user.pk,
        }
        if self.aluno_pedido:
            inicial["aluno"] = self.aluno_pedido.pk
        return inicial

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        url_aluno = _url_do_aluno(self.aluno_pedido)
        contexto.update({
            "titulo": "Registrar aula",
            "apoio": "O que aconteceu no atendimento. Só o aluno, a data e os minutos são obrigatórios.",
            "voltar_url": url_aluno or reverse("aulas:lista"),
            "voltar_rotulo": self.aluno_pedido.nome_curto if url_aluno else "Aulas",
            "secoes": SECOES_DO_REGISTRO,
            "botao": "Registrar aula",
            "fotos_perdidas": self._fotos_perdidas(contexto.get("form")),
        })
        return contexto

    def _fotos_perdidas(self, form):
        return bool(form is not None and form.is_bound and form.errors and self.request.FILES)

    def preparar_objeto(self, aula, form):
        aula.situacao = Situacao.REGISTRADA
        aula.registrada_em = timezone.now()
        aula.registrada_por = self.request.user
        if "professor" not in form.fields:
            aula.professor = self.request.user
        nome_novo = form.cleaned_data.get("aluno_novo")
        if nome_novo:
            aluno = Aluno(
                servico=self.request.servico, nome=nome_novo,
                criado_por=self.request.user, atualizado_por=self.request.user,
            )
            aluno.save()
            auditoria.registrar(
                self.request, Acao.CRIOU, aluno,
                mudancas=auditoria.comparar(Aluno, {}, auditoria.fotografar(aluno, ["nome"])),
                descricao="Cadastrou o aluno só com o nome, ao registrar uma aula",
            )
            aula.aluno = aluno
        self.aluno_criado = bool(nome_novo)

    def depois_de_salvar(self, aula, form, criado):
        fotos = salvar_fotos(self.request, aula, form.cleaned_data.get("novas_fotos") or [])
        mensagem = f"Aula de {aula.aluno.nome_curto} registrada{_texto_das_fotos(fotos)}."
        if self.aluno_criado:
            mensagem += f" O cadastro de {aula.aluno.nome_curto} foi criado só com o nome."
        self.mensagem_sucesso = mensagem
        self.aviso_ficha = aviso_da_ficha(self.request, aula)

    def form_valid(self, form):
        resposta = super().form_valid(form)
        if getattr(self, "aviso_ficha", None):
            messages.warning(self.request, self.aviso_ficha)
        return resposta

    def get_success_url(self):
        return reverse("aulas:detalhe", args=[self.object.pk])


class MarcarAulaView(AcessoMixin, CriarComAuditoriaMixin, CreateView):
    """Marcar aula: aparece na agenda de quem vai dar a aula e na tela inicial (RF-09, RF-44)."""

    grupo = "aulas"
    modo = EDITAR
    model = Aula
    template_name = "aulas/formulario.html"

    def get_form_class(self):
        return formulario_da_aula(self.request, CAMPOS_DE_MARCAR)

    @cached_property
    def aluno_pedido(self):
        return _aluno_da_consulta(self.request)

    def get_initial(self):
        inicial = {
            "data": regras.ler_data(self.request.GET.get("data"), regras.hoje()),
            "duracao_minutos": regras.minutos_por_aula(self.request.servico),
            "professor": self.request.user.pk,
        }
        if self.aluno_pedido:
            inicial["aluno"] = self.aluno_pedido.pk
        return inicial

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        url_aluno = _url_do_aluno(self.aluno_pedido)
        contexto.update({
            "titulo": "Marcar aula",
            "apoio": "A aula aparece na agenda de quem vai dar a aula. Depois do atendimento, é só registrar.",
            "voltar_url": url_aluno or reverse("aulas:lista"),
            "voltar_rotulo": self.aluno_pedido.nome_curto if url_aluno else "Aulas",
            "secoes": SECOES_DE_MARCAR,
            "botao": "Marcar aula",
            "colunas": True,
        })
        return contexto

    def preparar_objeto(self, aula, form):
        aula.situacao = Situacao.MARCADA
        if "professor" not in form.fields:
            aula.professor = self.request.user

    def depois_de_salvar(self, aula, form, criado):
        quem = "sua agenda" if aula.professor_id == self.request.user.pk else f"agenda de {aula.professor.nome_curto}"
        self.mensagem_sucesso = regras.frase(
            f"Aula com {aula.aluno.nome_curto} marcada para {_quando(aula)}. Ela já aparece na {quem}"
        )

    def get_success_url(self):
        return reverse("aulas:detalhe", args=[self.object.pk])


class AulaMarcadaMixin:
    """Telas que só valem para aula ainda marcada: registrar e dizer que não aconteceu."""

    def get_queryset(self):
        return super().get_queryset().select_related("aluno", "professor")

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.situacao != Situacao.MARCADA:
            return self.ja_resolvida(self.object)
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.situacao != Situacao.MARCADA:
            return self.ja_resolvida(self.object)
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    def ja_resolvida(self, aula, agora=False):
        if aula.situacao == Situacao.REGISTRADA:
            texto = "Esta aula já foi registrada. Para mudar algo, use Editar registro."
        else:
            texto = "Esta aula já está como não realizada. Para mudar algo, use Editar."
        if agora:
            texto = "Outra pessoa salvou esta aula enquanto você preenchia. " + texto
        messages.info(self.request, texto)
        return redirect("aulas:detalhe", pk=aula.pk)

    def travar(self):
        return Aula.objects.select_for_update().get(pk=self.object.pk)

    def get_success_url(self):
        return reverse("aulas:detalhe", args=[self.object.pk])


class RegistrarMarcadaView(AcessoMixin, DoServicoMixin, AulaMarcadaMixin, UpdateView):
    """Registrar a aula marcada, a partir da agenda, com aluno, data e hora já preenchidos (RF-15)."""

    grupo = "aulas"
    modo = EDITAR
    model = Aula
    template_name = "aulas/registrar.html"

    def get_form_class(self):
        return formulario_da_aula(self.request, CAMPOS_DO_REGISTRO, base=RegistroDeAulaForm)

    def get_initial(self):
        inicial = super().get_initial()
        hoje = regras.hoje()
        if self.object.data > hoje:
            # Marcada para depois, mas a aula aconteceu hoje.
            inicial["data"] = hoje
        return inicial

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        aula = self.object
        form = contexto.get("form")
        outro_professor = aula.professor_id != self.request.user.pk
        contexto.update({
            "titulo": f"Registrar a aula de {aula.aluno.nome_curto}",
            "apoio": f"Aula marcada com {aula.professor.nome_curto} para {_quando(aula)}. "
                     "Confira os dados e preencha o que foi trabalhado.",
            "voltar_url": reverse("aulas:detalhe", args=[aula.pk]),
            "voltar_rotulo": "Detalhe da aula",
            "secoes": SECOES_DO_REGISTRO,
            "botao": "Registrar aula",
            "aula_marcada": aula,
            "fica_em_seu_nome": outro_professor and form is not None and "professor" not in form.fields,
            "fotos_perdidas": bool(form is not None and form.is_bound and form.errors and self.request.FILES),
        })
        return contexto

    def form_valid(self, form):
        campos = _campos_auditados(form, extras=["professor", "situacao"])
        with transaction.atomic():
            atual = self.travar()
            if atual.situacao != Situacao.MARCADA:
                return self.ja_resolvida(atual, agora=True)
            antes = auditoria.fotografar(atual, campos)
            aula = form.save(commit=False)
            aula.situacao = Situacao.REGISTRADA
            aula.registrada_em = timezone.now()
            aula.registrada_por = self.request.user
            aula.versao = atual.versao + 1
            aula.atualizado_por = self.request.user
            if "professor" not in form.fields:
                aula.professor = self.request.user
            aula.save()
            form.save_m2m()
            fotos = salvar_fotos(self.request, aula, form.cleaned_data.get("novas_fotos") or [])
            auditoria.registrar(
                self.request, Acao.ALTEROU, aula, descricao="Registrou a aula marcada",
                mudancas=auditoria.comparar(Aula, antes, auditoria.fotografar(aula, campos)),
            )
            self.object = aula
        messages.success(self.request, f"Aula de {aula.aluno.nome_curto} registrada{_texto_das_fotos(fotos)}.")
        aviso = aviso_da_ficha(self.request, aula)
        if aviso:
            messages.warning(self.request, aviso)
        return redirect(self.get_success_url())


class NaoRealizadaView(AcessoMixin, DoServicoMixin, AulaMarcadaMixin, UpdateView):
    """A aula marcada não aconteceu: o motivo é obrigatório e vai para a trilha."""

    grupo = "aulas"
    modo = EDITAR
    model = Aula
    template_name = "aulas/nao_realizada.html"

    def get_form_class(self):
        return formulario_da_aula(self.request, ["motivo_nao_realizada"])

    def form_valid(self, form):
        campos = ["situacao", "motivo_nao_realizada"]
        with transaction.atomic():
            atual = self.travar()
            if atual.situacao != Situacao.MARCADA:
                return self.ja_resolvida(atual, agora=True)
            antes = auditoria.fotografar(atual, campos)
            aula = form.save(commit=False)
            aula.situacao = Situacao.NAO_REALIZADA
            aula.versao = atual.versao + 1
            aula.atualizado_por = self.request.user
            aula.save()
            auditoria.registrar(
                self.request, Acao.ALTEROU, aula, descricao="Registrou que a aula não aconteceu",
                mudancas=auditoria.comparar(Aula, antes, auditoria.fotografar(aula, campos)),
                motivo=aula.motivo_nao_realizada,
            )
            self.object = aula
        messages.success(self.request, f"Registrado que a aula de {aula.aluno.nome_curto} de {_quando(aula)} não aconteceu.")
        return redirect(self.get_success_url())


# ---------------------------------------------------------------- detalhe e edição

class DetalheDaAulaView(AcessoMixin, DoServicoMixin, DetailView):
    grupo = "aulas"
    model = Aula
    template_name = "aulas/detalhe.html"
    context_object_name = "aula"

    def get_queryset(self):
        return (
            super().get_queryset()
            .select_related("aluno", "professor", "registrada_por")
            .prefetch_related("componentes", "habilidades", "fotos")
        )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        aula = self.object
        regra = regras.minutos_por_aula(self.request.servico)
        aula.falta_registrar = aula.situacao == Situacao.MARCADA and aula.data < regras.hoje()
        contexto.update({
            "regra": regra,
            "texto_da_regra": regras.texto_da_regra(regra),
            "equivalentes": regras.aulas_equivalentes(aula.duracao_minutos, regra),
            "fotos": list(aula.fotos.all()),
            "eventos": eventos_da_aula(self.request, aula),
        })
        return contexto


class EditarAulaView(AcessoMixin, DoServicoMixin, EditarComAuditoriaMixin, UpdateView):
    """Editar com motivo; se outra pessoa salvou no meio do caminho, a tela mostra as duas versões (RNF-04)."""

    grupo = "aulas"
    modo = EDITAR
    model = Aula
    template_name = "aulas/formulario.html"

    def campos_da_situacao(self):
        if self.object.situacao == Situacao.REGISTRADA:
            return CAMPOS_DO_REGISTRO
        if self.object.situacao == Situacao.NAO_REALIZADA:
            return CAMPOS_DA_NAO_REALIZADA
        return CAMPOS_DE_MARCAR

    def get_form_class(self):
        return formulario_da_aula(
            self.request, self.campos_da_situacao(), edicao=True,
            exigir_data_passada=self.object.situacao == Situacao.REGISTRADA,
        )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        aula = self.object
        registrada = aula.situacao == Situacao.REGISTRADA
        secoes = [{"titulo": "Aluno e horário", "campos": CAMPOS_DE_MARCAR}]
        if registrada:
            secoes.append({"titulo": "O que foi trabalhado", "campos": ["componentes", "conteudo", "participacao", "habilidades"]})
        elif aula.situacao == Situacao.NAO_REALIZADA:
            secoes.append({"titulo": "Por que não aconteceu", "campos": ["motivo_nao_realizada"]})
        contexto.update({
            "titulo": f"Editar {'o registro da aula' if registrada else 'a aula'} de {aula.aluno.nome_curto}",
            "apoio": f"Aula de {_quando(aula)}, {aula.get_situacao_display().lower()}. "
                     "A alteração fica na trilha, com o motivo.",
            "voltar_url": reverse("aulas:detalhe", args=[aula.pk]),
            "voltar_rotulo": "Detalhe da aula",
            "secoes": secoes,
            "botao": "Salvar alterações",
        })
        return contexto

    def get_success_url(self):
        return reverse("aulas:detalhe", args=[self.object.pk])


# ---------------------------------------------------------------- fotos

class FotoNovaView(AcessoMixin, FormView):
    """Adicionar fotos a uma aula registrada (até 10 por envio)."""

    grupo = "aulas"
    modo = EDITAR
    form_class = FotosForm
    template_name = "aulas/foto_nova.html"

    @cached_property
    def aula(self):
        return get_object_or_404(Aula.objects.select_related("aluno"), pk=self.kwargs["pk"], servico=self.request.servico)

    def get(self, request, *args, **kwargs):
        if self.aula.situacao != Situacao.REGISTRADA:
            return self._so_registrada()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if self.aula.situacao != Situacao.REGISTRADA:
            return self._so_registrada()
        return super().post(request, *args, **kwargs)

    def _so_registrada(self):
        if self.aula.situacao == Situacao.MARCADA:
            messages.info(self.request, "As fotos entram junto com o registro. Registre a aula e anexe as fotos nele.")
            return redirect("aulas:registrar_marcada", pk=self.aula.pk)
        messages.info(self.request, "Esta aula não aconteceu, então não recebe fotos.")
        return redirect("aulas:detalhe", pk=self.aula.pk)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update({
            "aula": self.aula,
            "quando": _quando(self.aula),
            "fotos_perdidas": bool(self.request.method == "POST" and self.request.FILES),
        })
        return contexto

    def form_valid(self, form):
        with transaction.atomic():
            fotos = salvar_fotos(self.request, self.aula, form.cleaned_data["novas_fotos"], form.cleaned_data["legenda"])
        quantas = "1 foto adicionada" if len(fotos) == 1 else f"{len(fotos)} fotos adicionadas"
        messages.success(self.request, regras.frase(f"{quantas} à aula de {self.aula.aluno.nome_curto}"))
        return redirect(reverse("aulas:detalhe", args=[self.aula.pk]) + "#fotos")


@login_required
def foto(request, pk):
    """Entrega a foto de uma aula: só com login, do mesmo serviço e para quem vê aulas."""
    if request.servico is None:
        return render(request, "core/sem_vinculo.html", status=403)
    if not request.acesso.pode_ver("aulas"):
        raise PermissionDenied("Seu papel não permite ver as aulas.")
    foto_da_aula = get_object_or_404(FotoDaAula.objects.select_related("aula"), pk=pk, servico=request.servico)
    extensao = foto_da_aula.arquivo.name.rsplit(".", 1)[-1] if "." in foto_da_aula.arquivo.name else "jpg"
    nome = f"foto-da-aula-{foto_da_aula.aula.data:%Y-%m-%d}-{foto_da_aula.pk}.{extensao}"
    return servir_arquivo(foto_da_aula.arquivo, nome)


# ---------------------------------------------------------------- BNCC (RF-16)

class HabilidadesView(AcessoMixin, DoServicoMixin, ListView):
    """Lista de eixos e habilidades da BNCC mantida pelo serviço."""

    exige_configurar = True
    grupo = "aulas"
    model = HabilidadeBNCC
    template_name = "aulas/habilidades.html"
    context_object_name = "habilidades"
    paginate_by = 100
    page_kwarg = "pagina"

    def get_queryset(self):
        return super().get_queryset().annotate(total_aulas=Count("aulas", distinct=True)).order_by("codigo")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update({
            "bncc_ativa": self.request.servico.bncc_ativa,
            "url_configuracao": regras.url_ou_none("equipe:configuracao"),
            "pagina": contexto.get("page_obj"),
            "total_ativas": HabilidadeBNCC.objects.filter(servico=self.request.servico, ativa=True).count(),
        })
        return contexto


class HabilidadeNovaView(AcessoMixin, CriarComAuditoriaMixin, CreateView):
    exige_configurar = True
    grupo = "aulas"
    modo = EDITAR
    model = HabilidadeBNCC
    template_name = "aulas/habilidade_form.html"
    mensagem_sucesso = "Habilidade cadastrada na lista da BNCC."

    def get_form_class(self):
        return formulario_da_habilidade(self.request)

    def get_success_url(self):
        return reverse("aulas:habilidades")


class HabilidadeEditarView(AcessoMixin, DoServicoMixin, EditarComAuditoriaMixin, UpdateView):
    exige_configurar = True
    grupo = "aulas"
    modo = EDITAR
    model = HabilidadeBNCC
    template_name = "aulas/habilidade_form.html"
    mensagem_sucesso = "Habilidade salva."

    def get_form_class(self):
        return formulario_da_habilidade(self.request, edicao=True)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["eventos"] = eventos_do_objeto(self.request, self.object)
        return contexto

    def get_success_url(self):
        return reverse("aulas:habilidades")

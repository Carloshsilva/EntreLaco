"""Telas dos alunos: lista, cadastro, perfil, ficha, responsáveis, situação, professor domiciliar
e ordem de atendimento.

RF-10 (ficha e condições em destaque), RF-11 (situação com motivo), RF-19 (cadastro mínimo),
RF-21 (revisão de ativo), RF-22 (saída), RF-24 (professor domiciliar), RF-46 (ordem de atendimento),
RNF-04 (conflito de edição), SEG-02 (permissão por tipo de dado), SEG-03 (trilha), SEG-05 (serviço).

Toda consulta parte de `request.servico`: aluno de outro serviço dá 404. Cada tela confere
a permissão do papel e cada botão só aparece para quem pode usá-lo.
"""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.utils.functional import cached_property
from django.utils.text import capfirst
from django.views.generic import CreateView, DetailView, TemplateView, UpdateView

from core import auditoria
from core.permissoes import EDITAR, NOMES_DE_GRUPO
from core.registro import secoes_do_aluno
from core.views_base import AcessoMixin, CriarComAuditoriaMixin, DoServicoMixin, EditarComAuditoriaMixin

from . import consultas
from .formularios import (
    WIDGETS_DO_ALUNO,
    FormularioAlunoBase,
    FormularioDomiciliar,
    FormularioMudancaDeSituacao,
    FormularioResponsavelBase,
)
from .models import Aluno, MudancaDeSituacao, Responsavel

Acao = auditoria.Acao
Situacao = Aluno.Situacao

ALUNOS_POR_PAGINA = 30
FILA_POR_PAGINA = 50
# Tipos de dado da ficha (identificação, condições e aprendizagem, saúde, vida escolar).
GRUPOS_DA_FICHA = list(Aluno.GRUPOS_DE_CAMPOS)

AJUDAS_DAS_SECOES = {
    "aprendizagem": "Aparecem em destaque no perfil do aluno. Deixe “Ainda não avaliado” até conversar com a família.",
    "sensivel": "Dados de saúde: só quem tem permissão para este tipo de dado vê estes campos.",
    "escolar": "Sem matrícula em escola, marque a opção: a orientação pedagógica acompanha até a matrícula.",
}

# Condições em destaque no perfil (RF-10) e os valores que pedem atenção.
CONDICOES_EM_DESTAQUE = {
    "visao": {Aluno.Condicao.COM_ALTERACAO},
    "audicao": {Aluno.Condicao.COM_ALTERACAO},
    "fala": {Aluno.Condicao.COM_ALTERACAO},
    "motricidade": {Aluno.Condicao.COM_ALTERACAO},
    "alfabetizacao": {Aluno.Alfabetizacao.NAO_ALFABETIZADO},
    "reprovacao": {Aluno.Reprovacao.JA_REPROVOU},
}


# ---------------------------------------------------------------- regras e ajudas

def edita_a_ficha(acesso):
    """Edita a ficha quem vê o aluno e edita ao menos um tipo de dado dela."""
    return acesso.pode_ver("identificacao") and any(acesso.pode_editar(grupo) for grupo in GRUPOS_DA_FICHA)


def pode_registrar_domiciliar(request, mudanca):
    """Quem muda situação ou quem ficou responsável pela saída registra a decisão (RF-24)."""
    return request.acesso.tem("mudar_situacao") or (
        mudanca.responsavel_id is not None and mudanca.responsavel_id == request.user.pk
    )


def _so_resultados(request):
    """A busca enquanto digita pede só o trecho #resultados; navegação normal recebe a página inteira."""
    htmx = getattr(request, "htmx", None)
    return bool(htmx) and htmx.target == "resultados" and not (htmx.boosted or htmx.history_restore_request)


def _url(nome, *args, consulta=""):
    """Endereço de uma tela de outro módulo, ou "" se ela ainda não existe (o botão some)."""
    try:
        url = reverse(nome, args=args)
    except NoReverseMatch:
        return ""
    return f"{url}?{consulta}" if consulta else url


def _sem_servico(request):
    return render(request, "core/sem_vinculo.html", status=403)


def secoes_do_formulario(form, novo=False):
    """Uma seção por tipo de dado, só com os campos que o papel edita (RF-07)."""
    secoes = []
    for grupo, campos in Aluno.GRUPOS_DE_CAMPOS.items():
        nomes = [nome for nome in campos if nome in form.fields]
        if not nomes:
            continue
        ajuda = AJUDAS_DAS_SECOES.get(grupo, "")
        if grupo == "identificacao" and novo:
            ajuda = "Só o nome é obrigatório. O que faltar pode ser completado depois e vira pendência."
        secoes.append({"titulo": NOMES_DE_GRUPO[grupo], "campos": nomes, "ajuda": ajuda})
    return secoes


def condicoes_em_destaque(aluno):
    condicoes = []
    for nome, atencao in CONDICOES_EM_DESTAQUE.items():
        condicoes.append({
            "rotulo": capfirst(Aluno._meta.get_field(nome).verbose_name),
            "valor": getattr(aluno, f"get_{nome}_display")(),
            "atencao": getattr(aluno, nome) in atencao,
        })
    return condicoes


def acoes_rapidas(request, aluno):
    """Botões do topo do perfil, só os que a pessoa pode usar. O primeiro é o principal."""
    acesso = request.acesso
    acoes = []
    if aluno.situacao != Situacao.ENCERRADO and acesso.pode_editar("aulas"):
        acoes.append(("Registrar aula", _url("aulas:registrar", consulta=f"aluno={aluno.pk}"), "aula"))
        acoes.append(("Marcar aula", _url("aulas:marcar", consulta=f"aluno={aluno.pk}"), "calendario"))
    if acesso.pode_editar("documentos"):
        acoes.append(("Enviar documento", _url("documentos:novo", aluno.pk), "documento"))
    if edita_a_ficha(acesso):
        acoes.append(("Editar ficha", reverse("alunos:editar", args=[aluno.pk]), "editar"))
    return [{"rotulo": rotulo, "url": url, "icone": icone} for rotulo, url, icone in acoes if url]


# ---------------------------------------------------------------- lista

class ListaDeAlunos(AcessoMixin, TemplateView):
    """Lista com busca enquanto digita e filtros de situação e unidade."""

    grupo = "identificacao"
    template_name = "alunos/lista.html"

    def get(self, request, *args, **kwargs):
        servico = request.servico
        q = request.GET.get("q", "").strip()[:100]
        filtros = {codigo: (rotulo, situacao) for codigo, rotulo, situacao in consultas.FILTROS_DE_SITUACAO}
        filtro = request.GET.get("situacao", consultas.FILTRO_PADRAO)
        if filtro not in filtros:
            filtro = consultas.FILTRO_PADRAO
        unidades = consultas.unidades_do_servico(servico)
        unidade = request.GET.get("unidade", "")
        if unidade not in unidades:
            unidade = ""

        alunos = consultas.alunos_do_servico(servico)
        situacao = filtros[filtro][1]
        if situacao:
            alunos = alunos.filter(situacao=situacao)
        if unidade:
            alunos = alunos.filter(unidade=unidade)
        alunos = consultas.com_tem_responsavel(consultas.buscar_por_nome(alunos, q)).order_by("nome", "pk")
        pagina = Paginator(alunos, ALUNOS_POR_PAGINA).get_page(request.GET.get("pagina"))
        linhas = [{"aluno": aluno, "ficha_incompleta": bool(aluno.faltas_da_ficha_por_grupo())} for aluno in pagina]

        contexto = self.get_context_data(
            pagina=pagina, linhas=linhas, q=q, filtro=filtro, filtro_rotulo=filtros[filtro][0],
            filtros=[(codigo, rotulo) for codigo, rotulo, _ in consultas.FILTROS_DE_SITUACAO],
            unidades=unidades, unidade=unidade, ve_escolar=request.acesso.pode_ver("escolar"),
            filtrando=bool(q or unidade),
        )
        template = "alunos/_resultados.html" if _so_resultados(request) else self.template_name
        resposta = render(request, template, contexto)
        patch_vary_headers(resposta, ["HX-Request", "HX-Target"])
        return resposta


# ---------------------------------------------------------------- cadastrar e editar a ficha

class FichaMixin:
    """Comum a cadastrar e editar: campos por permissão, seções por tipo de dado e busca de escola."""

    model = Aluno
    form_base = FormularioAlunoBase
    widgets = WIDGETS_DO_ALUNO
    template_name = "alunos/aluno_form.html"
    novo = False
    botao = "Salvar ficha"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["secoes"] = secoes_do_formulario(contexto["form"], novo=self.novo)
        contexto["botao"] = self.botao
        return contexto

    def get_success_url(self):
        return reverse("alunos:detalhe", args=[self.object.pk])


class NovoAluno(FichaMixin, AcessoMixin, CriarComAuditoriaMixin, CreateView):
    """Cadastro mínimo: só o nome é obrigatório; o que faltar vira pendência (RF-19)."""

    grupo = "identificacao"
    modo = EDITAR
    novo = True
    botao = "Cadastrar aluno"

    def depois_de_salvar(self, obj, form, criado):
        faltas = obj.faltas_da_ficha_por_grupo()
        visiveis = [rotulo for grupo, rotulo in faltas if self.request.acesso.pode_ver(grupo)]
        if visiveis:
            self.mensagem_sucesso = f"Aluno cadastrado. Falta: {consultas.juntar(visiveis)}."
        elif faltas:
            self.mensagem_sucesso = "Aluno cadastrado. A ficha ainda está incompleta."
        else:
            self.mensagem_sucesso = "Aluno cadastrado."


class EditarAluno(FichaMixin, AcessoMixin, DoServicoMixin, EditarComAuditoriaMixin, UpdateView):
    """Editar a ficha: só os tipos de dado que o papel edita, com motivo e aviso de conflito (RNF-04)."""

    mensagem_sucesso = "Ficha salva."

    def tem_permissao(self, request):
        return super().tem_permissao(request) and edita_a_ficha(request.acesso)

    def get_queryset(self):
        return super().get_queryset().select_related("escola")

    def get_success_url(self):
        return reverse("alunos:detalhe", args=[self.object.pk]) + "#secao-ficha"


# ---------------------------------------------------------------- perfil

class DetalheDoAluno(AcessoMixin, DoServicoMixin, DetailView):
    """Perfil: resumo, condições em destaque (RF-10), ações rápidas e as seções de cada módulo."""

    grupo = "identificacao"
    model = Aluno
    template_name = "alunos/detalhe.html"
    context_object_name = "aluno"

    def get_queryset(self):
        return consultas.com_tem_responsavel(super().get_queryset().select_related("escola"))

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        request = self.request
        acesso = request.acesso
        aluno = self.object
        faltas = aluno.faltas_da_ficha_por_grupo()
        visiveis = [rotulo for grupo, rotulo in faltas if acesso.pode_ver(grupo)]
        contexto.update({
            "secoes": secoes_do_aluno(request, aluno),
            "condicoes": condicoes_em_destaque(aluno) if acesso.pode_ver("aprendizagem") else None,
            "ficha_incompleta": bool(faltas),
            "faltas": consultas.juntar(visiveis),
            "faltas_escondidas": len(visiveis) < len(faltas),
            "ve_escolar": acesso.pode_ver("escolar"),
            "acoes_rapidas": acoes_rapidas(request, aluno),
            "edita_a_ficha": edita_a_ficha(acesso),
        })
        return contexto


# ---------------------------------------------------------------- responsáveis

class ResponsavelMixin:
    """Comum a adicionar e editar responsável. Vem antes de AcessoMixin, para valer o `grupo` e o `modo`."""

    grupo = "familia"
    modo = EDITAR
    model = Responsavel
    form_base = FormularioResponsavelBase
    widgets = {"observacoes": forms.TextInput(attrs={"autocomplete": "off"})}
    template_name = "alunos/responsavel_form.html"
    mensagem_sucesso = "Responsável salvo."

    def tem_permissao(self, request):
        return super().tem_permissao(request) and request.acesso.pode_ver("identificacao")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["aluno"] = self.aluno
        return contexto

    def get_success_url(self):
        return reverse("alunos:detalhe", args=[self.aluno.pk]) + "#secao-responsaveis"


class NovoResponsavel(ResponsavelMixin, AcessoMixin, CriarComAuditoriaMixin, CreateView):
    @cached_property
    def aluno(self):
        return get_object_or_404(Aluno, pk=self.kwargs["pk"], servico=self.request.servico)

    def get(self, request, *args, **kwargs):
        self.aluno  # noqa: B018 - aluno de outro serviço dá 404 antes de abrir o formulário
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.aluno  # noqa: B018
        return super().post(request, *args, **kwargs)

    def preparar_objeto(self, obj, form):
        obj.aluno = self.aluno


class EditarResponsavel(ResponsavelMixin, AcessoMixin, DoServicoMixin, EditarComAuditoriaMixin, UpdateView):
    def get_queryset(self):
        return super().get_queryset().select_related("aluno")

    @property
    def aluno(self):
        return self.object.aluno


# ---------------------------------------------------------------- situação (RF-11, RF-21, RF-22)

def _registrar_mudanca(request, aluno, dados):
    """Grava a mudança, atualiza o aluno e registra na trilha. Chame dentro de uma transação."""
    de, para = aluno.situacao, dados["para"]
    campos = ["situacao", "situacao_desde"]
    antes = auditoria.fotografar(aluno, campos)
    mudanca = MudancaDeSituacao.objects.create(
        servico=request.servico, criado_por=request.user, atualizado_por=request.user,
        aluno=aluno, de=de, para=para, data=dados["data"], motivo=dados["motivo"],
        motivo_saida=dados["motivo_saida"] or "", responsavel=dados["responsavel"],
    )
    aluno.situacao = para
    if para != de:
        aluno.situacao_desde = dados["data"]
    aluno.versao += 1
    aluno.atualizado_por = request.user
    aluno.save(update_fields=["situacao", "situacao_desde", "versao", "atualizado_por", "atualizado_em"])
    depois = auditoria.fotografar(aluno, campos)
    mudancas = auditoria.comparar(Aluno, antes, depois)
    # A trilha sempre leva de onde para onde, inclusive na revisão que mantém o aluno ativo.
    mudancas.setdefault("situacao", {
        "rotulo": "situação", "grupo": "identificacao", "de": antes["situacao"], "para": depois["situacao"],
    })
    if para == Situacao.ENCERRADO:
        mudancas["motivo_saida"] = {
            "rotulo": "motivo de saída", "grupo": "identificacao", "de": "", "para": dados["motivo_saida"],
        }
        mudancas["responsavel_saida"] = {
            "rotulo": "responsável pela saída", "grupo": "identificacao", "de": "", "para": str(dados["responsavel"]),
        }
    if de == para:
        descricao = "Revisou a situação: continua ativo"
    else:
        descricao = f"Situação: {Situacao(de).label} → {Situacao(para).label}"
    auditoria.registrar(request, Acao.MUDOU_SITUACAO, aluno, mudancas=mudancas, motivo=dados["motivo"],
                        descricao=descricao)
    return mudanca


@login_required
def mudar_situacao(request, pk):
    """Mudar a situação: ativo, em pausa ou encerrado, sempre com motivo (RF-11, RF-22).

    Com o aluno ativo, "Continua ativo" registra a revisão (RF-21). Se outra pessoa mudou
    a situação enquanto esta preenchia, nada é salvo e a tela avisa (RNF-04).
    """
    if request.servico is None:
        return _sem_servico(request)
    if not (request.acesso.pode_ver("identificacao") and request.acesso.tem("mudar_situacao")):
        raise PermissionDenied("Seu papel não permite mudar a situação do aluno.")
    aluno = get_object_or_404(Aluno, pk=pk, servico=request.servico)
    dados_enviados = request.POST if request.method == "POST" else None
    form = FormularioMudancaDeSituacao(dados_enviados, aluno=aluno, servico=request.servico, usuario=request.user)
    aviso = ""
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            atual = Aluno.objects.select_for_update().get(pk=aluno.pk)
            vista = form.cleaned_data.get("situacao_vista") or atual.situacao
            if vista == atual.situacao:
                mudanca = _registrar_mudanca(request, atual, form.cleaned_data)
            else:
                mudanca = None
        if mudanca is not None:
            messages.success(request, _mensagem_da_mudanca(mudanca, atual))
            return redirect(reverse("alunos:detalhe", args=[atual.pk]) + "#secao-situacao")
        ultima = atual.mudancas_de_situacao.select_related("criado_por").order_by("-criado_em", "-pk").first()
        quem = ultima.criado_por.nome_curto if ultima and ultima.criado_por else "Outra pessoa"
        aviso = (
            f"Enquanto você preenchia, {quem} mudou a situação para {atual.get_situacao_display()}. "
            "Nada do que você enviou foi salvo. Confira a nova situação e envie de novo, se ainda for preciso."
        )
        dados = request.POST.copy()
        dados["situacao_vista"] = atual.situacao
        aluno = atual
        form = FormularioMudancaDeSituacao(dados, aluno=aluno, servico=request.servico, usuario=request.user)
    return render(request, "alunos/situacao_form.html", {
        "aluno": aluno,
        "form": form,
        "aviso": aviso,
        "url_volta": reverse("alunos:detalhe", args=[aluno.pk]) + "#secao-situacao",
    })


def _mensagem_da_mudanca(mudanca, aluno):
    if mudanca.de == mudanca.para:
        return "Revisão registrada: o aluno continua ativo."
    texto = f"Situação mudada para {mudanca.get_para_display().lower()}."
    if mudanca.e_alta and aluno.tmo and mudanca.responsavel:
        texto += (f" Falta ver se a criança precisa de professor domiciliar: a pendência ficou com "
                  f"{mudanca.responsavel.nome_curto}.")
    return texto


@login_required
def domiciliar(request, pk):
    """Registrar o que se decidiu sobre o professor domiciliar na alta do TMO (RF-24)."""
    if request.servico is None:
        return _sem_servico(request)
    if not request.acesso.pode_ver("identificacao"):
        raise PermissionDenied("Seu papel não permite ver os alunos.")
    mudanca = get_object_or_404(
        MudancaDeSituacao.objects.select_related("aluno", "responsavel"), pk=pk, servico=request.servico
    )
    if not pode_registrar_domiciliar(request, mudanca):
        raise PermissionDenied("Só quem cuida da saída ou muda a situação dos alunos registra esta decisão.")
    aluno = mudanca.aluno
    url_volta = reverse("alunos:detalhe", args=[aluno.pk]) + "#secao-situacao"
    if not (mudanca.e_alta and aluno.tmo):
        messages.info(request, "Esta saída não pede a verificação do professor domiciliar.")
        return redirect(url_volta)
    if mudanca.domiciliar_verificado_em:
        messages.info(request, "A decisão sobre o professor domiciliar já foi registrada.")
        return redirect(url_volta)
    form = FormularioDomiciliar(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        campos = ["domiciliar_verificado_em", "domiciliar_verificado_por", "domiciliar_observacao"]
        with transaction.atomic():
            atual = MudancaDeSituacao.objects.select_for_update().get(pk=mudanca.pk)
            if atual.domiciliar_verificado_em is None:
                antes = auditoria.fotografar(atual, campos)
                atual.domiciliar_verificado_em = timezone.localdate()
                atual.domiciliar_verificado_por = request.user
                atual.domiciliar_observacao = form.cleaned_data["observacao"]
                atual.versao += 1
                atual.atualizado_por = request.user
                atual.save()
                mudancas = auditoria.comparar(MudancaDeSituacao, antes, auditoria.fotografar(atual, campos))
                auditoria.registrar(request, Acao.ALTEROU, atual, mudancas=mudancas,
                                    descricao="Registrou a decisão sobre o professor domiciliar")
                messages.success(request, "Decisão sobre o professor domiciliar registrada.")
            else:
                messages.info(request, "Outra pessoa registrou a decisão sobre o professor domiciliar antes de você.")
        return redirect(url_volta)
    return render(request, "alunos/domiciliar_form.html", {
        "aluno": aluno, "mudanca": mudanca, "form": form, "url_volta": url_volta,
        "ve_sensivel": request.acesso.pode_ver("sensivel"),
    })


# ---------------------------------------------------------------- ordem de atendimento (RF-46)

class FilaDeAtendimento(AcessoMixin, TemplateView):
    """Alunos ativos na ordem de atendimento, com o motivo de cada posição.

    Pede ver os alunos e as aulas: a ordem se baseia nas datas das aulas registradas.
    """

    grupo = "identificacao"
    template_name = "alunos/fila.html"

    def tem_permissao(self, request):
        return super().tem_permissao(request) and request.acesso.pode_ver("aulas")

    def get(self, request, *args, **kwargs):
        servico = request.servico
        unidades = consultas.unidades_do_servico(servico, situacao=Situacao.ATIVO)
        unidade = request.GET.get("unidade", "")
        if unidade not in unidades:
            unidade = ""
        usar_risco = request.acesso.pode_ver("escolar")
        fila = consultas.fila_de_atendimento(servico, unidade=unidade, usar_risco=usar_risco)
        pagina = Paginator(fila, FILA_POR_PAGINA).get_page(request.GET.get("pagina"))
        hoje = timezone.localdate()
        linhas = [
            {"aluno": aluno, "posicao": pagina.start_index() + indice,
             "motivos": consultas.motivos_na_fila(aluno, hoje, usar_risco)}
            for indice, aluno in enumerate(pagina)
        ]
        contexto = self.get_context_data(
            pagina=pagina, linhas=linhas, unidades=unidades, unidade=unidade, usar_risco=usar_risco,
            url_registrar=_url("aulas:registrar") if request.acesso.pode_editar("aulas") else "",
        )
        template = "alunos/_fila_resultados.html" if _so_resultados(request) else self.template_name
        resposta = render(request, template, contexto)
        patch_vary_headers(resposta, ["HX-Request", "HX-Target"])
        return resposta

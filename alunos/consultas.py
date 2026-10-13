"""Consultas do módulo alunos, usadas pelas telas, pela ordem de atendimento e pelas pendências.

Toda consulta parte de um serviço (SEG-05) e é feita de uma vez para a lista
inteira, sem uma consulta por aluno: com 300 alunos, a tela continua leve.
"""
import datetime
import re

from django.contrib.auth import get_user_model
from django.db.models import Exists, F, Max, OuterRef, Q, Subquery
from django.utils import timezone

from core.models import Vinculo
from core.permissoes import ACESSO_VAZIO, Acesso

from .models import Aluno, MudancaDeSituacao, Responsavel

Situacao = Aluno.Situacao

# Filtro de situação da lista: código na URL → situação do aluno (None = todas).
FILTROS_DE_SITUACAO = [
    ("ativos", "Ativos", Situacao.ATIVO),
    ("pausa", "Em pausa", Situacao.PAUSA),
    ("encerrados", "Encerrados", Situacao.ENCERRADO),
    ("todos", "Todos", None),
]
FILTRO_PADRAO = "ativos"

# Ficha incompleta: o prazo para completar conta da primeira aula ou do cadastro (RF-19).
DIAS_PARA_COMPLETAR_A_FICHA = 3


def _aula():
    from aulas.models import Aula

    return Aula


def juntar(itens):
    """"data de nascimento, ano escolar e um responsável"."""
    itens = [str(item) for item in itens]
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


# ---------------------------------------------------------------- alunos

def alunos_do_servico(servico):
    return Aluno.objects.filter(servico=servico)


def com_tem_responsavel(queryset):
    """Anota `tem_responsavel`, que a ficha usa para dizer se falta um responsável, sem consulta por aluno."""
    return queryset.annotate(tem_responsavel=Exists(Responsavel.objects.filter(aluno=OuterRef("pk"))))


def termos_da_busca(texto):
    return re.findall(r"\w+", texto or "")[:6]


def buscar_por_nome(queryset, texto):
    """Cada palavra precisa aparecer no nome completo ou no nome social."""
    for termo in termos_da_busca(texto):
        queryset = queryset.filter(Q(nome__icontains=termo) | Q(nome_social__icontains=termo))
    return queryset


def unidades_do_servico(servico, situacao=None):
    """Unidades de atendimento em uso, para o filtro das listas."""
    alunos = alunos_do_servico(servico).exclude(unidade="")
    if situacao:
        alunos = alunos.filter(situacao=situacao)
    return list(alunos.order_by("unidade").values_list("unidade", flat=True).distinct())


# ---------------------------------------------------------------- pessoas

def pessoas_do_servico(servico):
    """Pessoas com vínculo ativo no serviço, para campos de escolha (SEG-05)."""
    return (
        get_user_model().objects
        .filter(vinculos__servico=servico, vinculos__ativo=True, is_active=True)
        .order_by("nome")
        .distinct()
    )


def pessoas_com_acao(servico, acao):
    """Pessoas do serviço cujo papel tem a ação (por exemplo, mudar_situacao). Uma consulta."""
    vinculos = (
        Vinculo.objects.filter(servico=servico, ativo=True, usuario__is_active=True)
        .select_related("usuario", "papel")
        .order_by("usuario__nome")
    )
    return [vinculo.usuario for vinculo in vinculos if Acesso.do_papel(vinculo.papel).tem(acao)]


def acesso_de(request, usuario):
    """O que `usuario` pode fazer no serviço atual (quase sempre é a própria pessoa logada)."""
    if usuario is None or usuario.pk == getattr(request.user, "pk", None):
        return request.acesso
    vinculo = (
        Vinculo.objects.filter(usuario=usuario, servico=request.servico, ativo=True).select_related("papel").first()
    )
    return Acesso.do_papel(vinculo.papel) if vinculo else ACESSO_VAZIO


# ---------------------------------------------------------------- ordem de atendimento (RF-46)

def fila_de_atendimento(servico, unidade="", usar_risco=True):
    """Alunos ativos na ordem de atendimento, numa consulta só.

    1. mais dias sem aula registrada (quem nunca teve aula vem antes de todos);
    2. marca de risco de evasão (só quando a pessoa vê a vida escolar);
    3. mais dias de internação (data de internação mais antiga);
    4. nome, para desempatar sempre do mesmo jeito.
    """
    Aula = _aula()
    alunos = alunos_do_servico(servico).filter(situacao=Situacao.ATIVO)
    if unidade:
        alunos = alunos.filter(unidade=unidade)
    alunos = alunos.annotate(
        ultima_aula=Max("aulas__data", filter=Q(aulas__situacao=Aula.Situacao.REGISTRADA)),
    )
    ordem = [F("ultima_aula").asc(nulls_first=True)]
    if usar_risco:
        ordem.append(F("risco_evasao").desc())
    ordem += [F("data_internacao").asc(nulls_last=True), "nome", "pk"]
    return alunos.order_by(*ordem)


def _dias(quantidade):
    return "1 dia" if quantidade == 1 else f"{quantidade} dias"


def motivos_na_fila(aluno, hoje, usar_risco=True):
    """Por que o aluno está nesta posição: "12 dias sem aula · risco de evasão · internado há 30 dias"."""
    motivos = []
    if aluno.ultima_aula is None:
        motivos.append("nunca teve aula registrada")
    else:
        dias = max((hoje - aluno.ultima_aula).days, 0)
        motivos.append("teve aula hoje" if dias == 0 else f"{_dias(dias)} sem aula")
    if usar_risco and aluno.risco_evasao:
        motivos.append("risco de evasão")
    if aluno.data_internacao:
        dias = max((hoje - aluno.data_internacao).days, 0)
        motivos.append("internado hoje" if dias == 0 else f"internado há {_dias(dias)}")
    texto = " · ".join(motivos)
    return texto[:1].upper() + texto[1:]


# ---------------------------------------------------------------- pendências

def _data_local(momento):
    return timezone.localdate(momento) if momento else None


def alunos_com_ficha_incompleta(servico, responsavel=None):
    """Alunos ativos ou em pausa com a ficha incompleta e quem deve completá-la (RF-19).

    O responsável é o professor da primeira aula registrada do aluno ou, sem aula,
    quem cadastrou. Devolve uma lista de (aluno, id do responsável, data da primeira
    aula ou None), numa consulta só. Com `responsavel`, só as dessa pessoa.
    """
    Aula = _aula()
    primeiras = (
        Aula.objects.filter(aluno=OuterRef("pk"), situacao=Aula.Situacao.REGISTRADA)
        .order_by("data", F("hora_inicio").asc(nulls_last=True), "pk")
    )
    alunos = com_tem_responsavel(
        alunos_do_servico(servico).filter(situacao__in=[Situacao.ATIVO, Situacao.PAUSA])
    ).annotate(
        primeira_aula_data=Subquery(primeiras.values("data")[:1]),
        primeira_aula_professor=Subquery(primeiras.values("professor_id")[:1]),
    )
    if responsavel is not None:
        alunos = alunos.filter(
            Q(primeira_aula_professor=responsavel.pk)
            | Q(primeira_aula_professor__isnull=True, criado_por=responsavel.pk)
        )
    resultado = []
    for aluno in alunos.order_by("nome", "pk"):
        if not aluno.faltas_da_ficha_por_grupo():
            continue
        dono = aluno.primeira_aula_professor or aluno.criado_por_id
        resultado.append((aluno, dono, aluno.primeira_aula_data))
    return resultado


def referencia_da_revisao(aluno):
    """A data mais recente entre a última aula marcada ou registrada, a última mudança de situação e o cadastro."""
    datas = [aluno.ultima_aula_ou_marcada, aluno.ultima_mudanca, _data_local(aluno.criado_em)]
    return max(d for d in datas if d is not None)


def alunos_para_revisar(servico, hoje=None):
    """Alunos ativos sem aula registrada ou marcada dentro do prazo do serviço (RF-21).

    Devolve uma lista de (aluno, data em que o prazo venceu), numa consulta só.
    "Ativo é quem teve aula nas últimas três semanas": com o prazo de 21 dias, a
    revisão nasce no 22º dia sem aula.
    """
    Aula = _aula()
    hoje = hoje or timezone.localdate()
    prazo = datetime.timedelta(days=servico.prazo_revisao_ativo_dias)
    limite = hoje - prazo  # referência antes deste dia: o prazo já venceu
    ultima_aula = (
        Aula.objects.filter(aluno=OuterRef("pk"), situacao__in=[Aula.Situacao.MARCADA, Aula.Situacao.REGISTRADA])
        .order_by("-data").values("data")[:1]
    )
    ultima_mudanca = MudancaDeSituacao.objects.filter(aluno=OuterRef("pk")).order_by("-data").values("data")[:1]
    alunos = (
        alunos_do_servico(servico).filter(situacao=Situacao.ATIVO)
        .annotate(ultima_aula_ou_marcada=Subquery(ultima_aula), ultima_mudanca=Subquery(ultima_mudanca))
        .filter(Q(ultima_aula_ou_marcada__isnull=True) | Q(ultima_aula_ou_marcada__lt=limite))
        .filter(Q(ultima_mudanca__isnull=True) | Q(ultima_mudanca__lt=limite))
        .order_by("nome", "pk")
    )
    resultado = []
    for aluno in alunos:
        referencia = referencia_da_revisao(aluno)
        if referencia < limite:
            resultado.append((aluno, referencia + prazo))
    return resultado


def alunos_sem_matricula(servico):
    """Alunos ativos marcados como sem matrícula, que a orientação acompanha até a matrícula (RF-20)."""
    return list(
        alunos_do_servico(servico).filter(situacao=Situacao.ATIVO, sem_matricula=True).order_by("nome", "pk")
    )


def saidas_que_pedem_professor_domiciliar(servico, responsavel=None):
    """Saídas por alta de aluno do TMO sem a verificação do professor domiciliar (RF-24).

    Só conta enquanto o aluno continua encerrado. Com `responsavel`, só as dessa pessoa.
    """
    mudancas = (
        MudancaDeSituacao.objects.filter(
            servico=servico, para=Situacao.ENCERRADO, motivo_saida__istartswith="alta",
            domiciliar_verificado_em__isnull=True, aluno__tmo=True, aluno__situacao=Situacao.ENCERRADO,
        )
        .select_related("aluno", "responsavel")
        .order_by("data", "pk")
    )
    if responsavel is not None:
        mudancas = mudancas.filter(responsavel=responsavel)
    return list(mudancas)

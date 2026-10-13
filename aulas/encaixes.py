"""O que este módulo acrescenta às telas comuns (veja core/registro.py).

- Menu: "Aulas", para quem vê aulas.
- Agenda (RF-09, RF-44): aulas marcadas, registradas e as que não aconteceram,
  de uma pessoa (o calendário do professor) ou de todo o serviço.
- Pendências:
  - aula marcada que passou do dia e não foi registrada, para o professor da aula;
  - ficha incompleta de aluno com aula registrada, para quem deu a aula (RF-19).
- Seção "Aulas" no perfil do aluno, com as contas pela regra do serviço (RF-55).
"""
import datetime

from django.contrib.auth import get_user_model
from django.db.models import Max, Min
from django.urls import reverse

from core.registro import (
    EventoDaAgenda,
    ItemDeMenu,
    Pendencia,
    SecaoDoAluno,
    registrar_fonte_da_agenda,
    registrar_fonte_de_pendencias,
    registrar_menu,
    registrar_secao_do_aluno,
)

GRUPO = "aulas"
UM_DIA = datetime.timedelta(days=1)
PRAZO_DA_FICHA_DIAS = 7

registrar_menu(ItemDeMenu("Aulas", "aulas:lista", "aula", ordem=40, principal=True, grupo="aulas", ativo_em=("aulas:",)))


# ---------------------------------------------------------------- agenda

def eventos_de_aulas(request, inicio, fim, usuario):
    """Aulas do período. Com `usuario`, só as que ele dá; com None, as do serviço todo."""
    from .models import Aula

    servico = getattr(request, "servico", None)
    acesso = getattr(request, "acesso", None)
    if servico is None or acesso is None or not acesso.pode_ver(GRUPO):
        return []
    aulas = (
        Aula.objects.filter(servico=servico, data__range=(inicio, fim))
        .select_related("aluno", "professor")
        .prefetch_related("componentes")
    )
    if usuario is not None:
        aulas = aulas.filter(professor=usuario)
    pode_registrar = acesso.pode_editar(GRUPO)
    eventos = []
    for aula in aulas:
        marcada = aula.situacao == Aula.Situacao.MARCADA
        if marcada and pode_registrar:
            url = reverse("aulas:registrar_marcada", args=[aula.pk])
        else:
            url = reverse("aulas:detalhe", args=[aula.pk])
        if aula.situacao == Aula.Situacao.NAO_REALIZADA:
            detalhe = f"Não aconteceu: {aula.motivo_nao_realizada}" if aula.motivo_nao_realizada else ""
        else:
            componentes = [c.nome for c in aula.componentes.all()]
            detalhe = ", ".join(componentes)
        eventos.append(EventoDaAgenda(
            data=aula.data,
            titulo=f"Aula com {aula.aluno.nome_curto}",
            url=url,
            tipo="aula",
            hora=aula.hora_inicio,
            duracao_minutos=aula.duracao_minutos,
            detalhe=detalhe,
            situacao=aula.get_situacao_display(),
            cancelado=aula.situacao == Aula.Situacao.NAO_REALIZADA,
            pessoas=[aula.professor.nome_curto],
        ))
    return eventos


# ---------------------------------------------------------------- pendências

def pendencias_de_aulas(request, usuario, todas):
    """Aula marcada com data anterior a hoje e ainda sem registro.

    Nasce no dia seguinte ao da aula, com prazo nesse mesmo dia, para o
    professor da aula. Com `todas`, vem a de todo o serviço, com o responsável.
    """
    from . import regras
    from .models import Aula

    servico = getattr(request, "servico", None)
    if servico is None or usuario is None or not request.acesso.pode_ver(GRUPO):
        return []
    aulas = Aula.objects.filter(
        servico=servico, situacao=Aula.Situacao.MARCADA, data__lt=regras.hoje()
    ).select_related("aluno", "professor").order_by("data", "hora_inicio")
    if not todas:
        if not regras.acesso_de(request, usuario).pode_editar(GRUPO):
            return []
        aulas = aulas.filter(professor=usuario)
    pendencias = []
    for aula in aulas:
        horario = f" às {aula.hora_inicio:%H:%M}" if aula.hora_inicio else ""
        pendencias.append(Pendencia(
            titulo=f"Registrar a aula de {aula.aluno.nome_curto} de {aula.data:%d/%m}",
            url=reverse("aulas:registrar_marcada", args=[aula.pk]),
            tipo="Aula sem registro",
            prazo=aula.data + UM_DIA,
            aluno=aula.aluno.nome_curto,
            detalhe="Registre o que foi trabalhado ou diga que a aula não aconteceu.",
            origem=f"Aula marcada para {aula.data:%d/%m}{horario}",
            responsavel=aula.professor.nome_curto if todas else "",
            chave=f"aula-{aula.pk}",
        ))
    return pendencias


def pendencias_da_ficha(request, usuario, todas):
    """Ficha incompleta de aluno com aula registrada: pendência de quem deu a aula (RF-19).

    Uma por aluno e professor (chave "ficha-<aluno>-<professor>", a mesma do
    módulo de alunos, para não repetir). Só para quem pode editar a
    identificação do aluno, e só alunos ativos ou em pausa.
    """
    from alunos.models import Aluno

    from . import regras
    from .models import Aula

    servico = getattr(request, "servico", None)
    acesso = request.acesso
    if servico is None or usuario is None or not acesso.pode_ver(GRUPO) or not acesso.pode_ver("identificacao"):
        return []
    aulas = Aula.objects.filter(
        servico=servico, situacao=Aula.Situacao.REGISTRADA, aluno__situacao__in=regras.SITUACOES_QUE_RECEBEM_AULA,
    )
    if not todas:
        if not regras.recebe_pendencia_da_ficha(request, usuario):
            return []
        aulas = aulas.filter(professor=usuario)
    pares = list(aulas.order_by().values("aluno_id", "professor_id").annotate(primeira=Min("data")))
    if not pares:
        return []
    alunos = Aluno.objects.filter(servico=servico, pk__in={p["aluno_id"] for p in pares}).prefetch_related("responsaveis")
    faltas = {aluno.pk: (aluno, aluno.faltas_da_ficha()) for aluno in alunos}
    professores = get_user_model().objects.in_bulk({p["professor_id"] for p in pares}) if todas else {usuario.pk: usuario}
    recebe = {}  # professor → pode completar a ficha (uma consulta por professor, não por aluno)
    pendencias = []
    for par in sorted(pares, key=lambda p: p["primeira"]):
        aluno, o_que_falta = faltas.get(par["aluno_id"], (None, []))
        professor = professores.get(par["professor_id"])
        if aluno is None or not o_que_falta or professor is None:
            continue
        if todas:
            if professor.pk not in recebe:
                recebe[professor.pk] = regras.recebe_pendencia_da_ficha(request, professor)
            if not recebe[professor.pk]:
                continue
        url = regras.url_ou_none("alunos:editar", aluno.pk) or regras.url_ou_none("alunos:detalhe", aluno.pk)
        if url is None:
            continue
        pendencias.append(Pendencia(
            titulo=f"Completar a ficha de {aluno.nome_curto}",
            url=url,
            tipo="Ficha incompleta",
            prazo=par["primeira"] + datetime.timedelta(days=PRAZO_DA_FICHA_DIAS),
            aluno=aluno.nome_curto,
            detalhe=f"Falta {regras.juntar(o_que_falta)}.",
            origem=f"Aula de {par['primeira']:%d/%m} registrada sem a ficha completa",
            responsavel=professor.nome_curto if todas else "",
            chave=f"ficha-{aluno.pk}-{professor.pk}",
        ))
    return pendencias


# ---------------------------------------------------------------- perfil do aluno

QUANTAS_ULTIMAS = 10
QUANTAS_PROXIMAS = 5


def secao_aulas_do_aluno(request, aluno):
    """Totais pela regra do serviço, próximas aulas marcadas e as últimas aulas, com atalhos."""
    from . import regras
    from .models import Aula

    servico = getattr(request, "servico", None)
    if servico is None or aluno.servico_id != servico.pk or not request.acesso.pode_ver(GRUPO):
        return None
    hoje = regras.hoje()
    regra = regras.minutos_por_aula(servico)
    aulas = Aula.objects.filter(servico=servico, aluno=aluno)
    registradas, equivalentes = regras.somar_equivalentes(aulas, regra)
    proximas = list(
        aulas.filter(situacao=Aula.Situacao.MARCADA, data__gte=hoje)
        .select_related("professor").order_by("data", "hora_inicio")[:QUANTAS_PROXIMAS]
    )
    ultimas = list(
        aulas.exclude(situacao=Aula.Situacao.MARCADA, data__gte=hoje)
        .select_related("professor").prefetch_related("componentes")
        .order_by("-data", "-hora_inicio", "-pk")[:QUANTAS_ULTIMAS]
    )
    for aula in ultimas:
        aula.equivalentes = regras.aulas_equivalentes(aula.duracao_minutos, regra) if aula.situacao == Aula.Situacao.REGISTRADA else None
        aula.falta_registrar = aula.situacao == Aula.Situacao.MARCADA
    pode_editar = request.acesso.pode_editar(GRUPO)
    recebe_aula = aluno.situacao in regras.SITUACOES_QUE_RECEBEM_AULA
    periodo = aulas.aggregate(primeira=Min("data"), ultima=Max("data"))
    de, ate = periodo["primeira"] or hoje, max(periodo["ultima"] or hoje, hoje)
    return {
        "registradas": registradas,
        "equivalentes": equivalentes,
        "resumo": regras.resumo_de_atendimentos(registradas, equivalentes, regra),
        "proximas": proximas,
        "ultimas": ultimas,
        "pode_registrar": pode_editar and recebe_aula,
        "url_registrar": f"{reverse('aulas:registrar')}?aluno={aluno.pk}",
        "url_marcar": f"{reverse('aulas:marcar')}?aluno={aluno.pk}",
        "url_lista": f"{reverse('aulas:lista')}?aluno={aluno.pk}&professor=todos&de={de:%Y-%m-%d}&ate={ate:%Y-%m-%d}",
        "tem_aulas": bool(periodo["primeira"]),
    }


registrar_fonte_da_agenda(eventos_de_aulas)
registrar_fonte_de_pendencias(pendencias_de_aulas)
registrar_fonte_de_pendencias(pendencias_da_ficha)
registrar_secao_do_aluno(SecaoDoAluno(
    chave="aulas",
    titulo="Aulas",
    template="aulas/_secao_aluno.html",
    contexto=secao_aulas_do_aluno,
    grupo=GRUPO,
    ordem=40,
))

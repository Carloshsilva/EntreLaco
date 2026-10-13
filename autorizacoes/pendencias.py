"""Pendências das autorizações da família, calculadas a partir dos dados (RF-19, RF-27, RF-64).

1. Autorização atual pendente ou provisória: tarefa de quem colheu, com prazo de
   7 dias depois da coleta. "Colher o sim definitivo de Lia M. (contato com a escola)"
   ou "Colher a autorização de Lia M. (uso dos dados)". Some quando a coleta mais
   recente passa a válida ou recusada (RF-64).
2. Aluno ativo sem nenhuma coleta de um tipo: tarefa do professor da primeira aula
   registrada ou, sem aula, de quem cadastrou o aluno (RF-19, "a pendência da ficha e
   do termo"). Uma por aluno e pessoa, com os tipos que faltam.

Só aparecem para quem vê "Autorizações" e a identificação dos alunos (o título traz o
nome do aluno). Com `todas=True`, vêm as de todo o serviço, com o responsável.
Cada consulta é feita de uma vez para todos os alunos, sem consulta por aluno.
"""
import datetime

from django.contrib.auth import get_user_model
from django.db.models import F, OuterRef, Q, Subquery
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from core.models import Vinculo
from core.permissoes import ACESSO_VAZIO, Acesso
from core.registro import Pendencia

from . import regras
from .models import Autorizacao, Tipo

Situacao = Autorizacao.Situacao
SEM_RESPONSAVEL = "Sem responsável"
TIPO_DA_PENDENCIA = "Autorização"
# Pendente e provisória só viram tarefa enquanto o aluno é atendido.
SITUACOES_DO_ALUNO = [Aluno.Situacao.ATIVO, Aluno.Situacao.PAUSA]


def _prazo(momento_ou_data):
    data = timezone.localdate(momento_ou_data) if isinstance(momento_ou_data, datetime.datetime) else momento_ou_data
    return data + datetime.timedelta(days=regras.PRAZO_DA_PENDENCIA_DIAS)


def _acessos(request, ids):
    """O que cada pessoa pode no serviço atual, numa consulta só."""
    ids = {pk for pk in ids if pk}
    if not ids:
        return {}
    vinculos = Vinculo.objects.filter(
        servico=request.servico, ativo=True, usuario_id__in=ids, usuario__is_active=True
    ).select_related("papel")
    return {vinculo.usuario_id: Acesso.do_papel(vinculo.papel) for vinculo in vinculos}


def _acesso_de(request, usuario):
    if usuario.pk == getattr(request.user, "pk", None):
        return request.acesso
    return _acessos(request, [usuario.pk]).get(usuario.pk, ACESSO_VAZIO)


def _nomes(ids):
    ids = {pk for pk in ids if pk}
    if not ids:
        return {}
    return {p.pk: p.nome_curto for p in get_user_model().objects.filter(pk__in=ids).only("nome", "email")}


def _responsavel(dono_id, acessos, nomes):
    """Nome de quem deve agir, na visão de todas; sem quem veja as autorizações, fica sem responsável."""
    if dono_id is None or not acessos.get(dono_id, ACESSO_VAZIO).pode_ver(regras.GRUPO):
        return SEM_RESPONSAVEL
    return nomes.get(dono_id, SEM_RESPONSAVEL)


def pendencias_de_autorizacoes(request, usuario, todas):
    servico = getattr(request, "servico", None)
    acesso = getattr(request, "acesso", None)
    if servico is None or usuario is None or acesso is None:
        return []
    if not acesso.pode_ver(regras.GRUPO) or not acesso.pode_ver("identificacao"):
        return []
    if not todas and not _acesso_de(request, usuario).pode_ver(regras.GRUPO):
        return []
    return _pendentes_e_provisorias(request, usuario, todas) + _sem_coleta(request, usuario, todas)


# ---------------------------------------------------------------- 1. pendente ou provisória (RF-64)

def _pendentes_e_provisorias(request, usuario, todas):
    atuais = (
        regras.atuais_do_servico(request.servico)
        .filter(situacao__in=regras.SITUACOES_QUE_VIRAM_PENDENCIA, aluno__situacao__in=SITUACOES_DO_ALUNO)
        .select_related("aluno")
        .order_by("criado_em", "id")
    )
    if not todas:
        atuais = atuais.filter(colhida_por=usuario)
    atuais = list(atuais)
    donos = {a.colhida_por_id for a in atuais}
    acessos = _acessos(request, donos) if todas else {}
    nomes = _nomes(donos) if todas else {}
    pendencias = []
    for autorizacao in atuais:
        aluno = autorizacao.aluno
        tipo = regras.tipo_em_minusculas(autorizacao.tipo)
        base = autorizacao.colhida_em or autorizacao.criado_em
        if autorizacao.situacao == Situacao.PROVISORIA:
            titulo = f"Colher o sim definitivo de {aluno.nome_curto} ({tipo})"
            detalhe = "O sim por WhatsApp é provisório. Colha o sim definitivo no tablet ou no papel."
            origem = f"Sim provisório por WhatsApp em {timezone.localdate(base):%d/%m}"
        else:
            titulo = f"Colher a autorização de {aluno.nome_curto} ({tipo})"
            if autorizacao.forma == Autorizacao.Forma.TABLET:
                detalhe = "A assinatura no tablet não foi concluída."
            else:
                detalhe = "A família ainda vai decidir."
            origem = f"Registrada como pendente em {timezone.localdate(base):%d/%m}"
        pendencias.append(Pendencia(
            titulo=titulo,
            url=reverse("autorizacoes:colher", args=[aluno.pk, autorizacao.tipo]),
            tipo=TIPO_DA_PENDENCIA,
            prazo=_prazo(base),
            aluno=aluno.nome_curto,
            detalhe=detalhe,
            origem=origem,
            responsavel=_responsavel(autorizacao.colhida_por_id, acessos, nomes) if todas else "",
            chave=f"autorizacao-{aluno.pk}-{autorizacao.tipo}-{autorizacao.colhida_por_id or 0}",
        ))
    return pendencias


# ---------------------------------------------------------------- 2. aluno ativo sem coleta (RF-19)

def _sem_coleta(request, usuario, todas):
    from aulas.models import Aula

    primeiras = (
        Aula.objects.filter(aluno=OuterRef("pk"), situacao=Aula.Situacao.REGISTRADA)
        .order_by("data", F("hora_inicio").asc(nulls_last=True), "pk")
    )
    alunos = regras.com_tem_coleta(
        Aluno.objects.filter(servico=request.servico, situacao=Aluno.Situacao.ATIVO)
    ).annotate(
        primeira_aula_data=Subquery(primeiras.values("data")[:1]),
        primeira_aula_professor=Subquery(primeiras.values("professor_id")[:1]),
    )
    falta_algum = Q()
    for codigo in Tipo.values:
        falta_algum |= Q(**{f"tem_{codigo}": False})
    alunos = alunos.filter(falta_algum)
    if not todas:
        alunos = alunos.filter(
            Q(primeira_aula_professor=usuario.pk)
            | Q(primeira_aula_professor__isnull=True, criado_por=usuario.pk)
        )
    alunos = list(alunos.order_by("nome", "pk"))
    donos = {aluno.primeira_aula_professor or aluno.criado_por_id for aluno in alunos}
    acessos = _acessos(request, donos) if todas else {}
    nomes = _nomes(donos) if todas else {}
    pendencias = []
    for aluno in alunos:
        faltam = [codigo for codigo in Tipo.values if not getattr(aluno, f"tem_{codigo}")]
        dono = aluno.primeira_aula_professor or aluno.criado_por_id
        if aluno.primeira_aula_data:
            base = aluno.primeira_aula_data
            origem = f"Aula de {base:%d/%m} registrada sem as autorizações da família"
        else:
            base = timezone.localdate(aluno.criado_em)
            origem = f"Cadastro de {base:%d/%m}, ainda sem as autorizações da família"
        rotulos = [regras.tipo_em_minusculas(codigo) for codigo in faltam]
        if len(faltam) == 1:
            titulo = f"Colher a autorização de {aluno.nome_curto} ({rotulos[0]})"
            detalhe = f"Falta a autorização de {rotulos[0]}."
        else:
            titulo = f"Colher as autorizações de {aluno.nome_curto}"
            detalhe = "Faltam as autorizações de " + ", ".join(rotulos[:-1]) + " e " + rotulos[-1] + "."
        pendencias.append(Pendencia(
            titulo=titulo,
            url=reverse("alunos:detalhe", args=[aluno.pk]) + "#secao-autorizacoes",
            tipo=TIPO_DA_PENDENCIA,
            prazo=_prazo(base),
            aluno=aluno.nome_curto,
            detalhe=detalhe,
            origem=origem,
            responsavel=_responsavel(dono, acessos, nomes) if todas else "",
            chave=f"autorizacao-{aluno.pk}-{'-'.join(faltam)}-{dono or 0}",
        ))
    return pendencias

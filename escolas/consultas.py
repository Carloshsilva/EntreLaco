"""Consultas da base de escolas usadas pelas telas, pelas pendências e pelo perfil do aluno.

A base de escolas (`Escola`) é comum a todos os serviços; o contato (`ContatoEscola`)
é de cada serviço e sempre se filtra por ele (SEG-05).
"""
import re

from django.db.models import Exists, OuterRef, Q, Subquery

from .models import ContatoEscola, Escola

Situacao = ContatoEscola.Situacao

# Situação do contato vista pelo serviço, para o selo: "atualizado", "precisa_atualizar" ou None (sem contato).
SEM_CONTATO = None


def termos_da_busca(texto):
    """Palavras e números de uma busca, sem pontuação: "12345678 · Escola (Cidade/SP)" → [...]."""
    return re.findall(r"\w+", texto or "")[:8]


def filtrar_por_busca(queryset, texto):
    """Filtra escolas pelo nome, pelo código INEP ou pelo município (RF-13).

    Cada palavra precisa aparecer no nome, no município ou na UF; um número de
    8 algarismos é o código INEP exato, e um número menor é o começo do código.
    """
    for termo in termos_da_busca(texto):
        if termo.isdigit():
            if len(termo) == 8:
                queryset = queryset.filter(codigo_inep=termo)
            else:
                queryset = queryset.filter(codigo_inep__startswith=termo)
            continue
        filtro = Q(nome__icontains=termo) | Q(municipio__icontains=termo)
        if len(termo) == 2:
            filtro |= Q(uf__iexact=termo)
        queryset = queryset.filter(filtro)
    return queryset


def busca_suficiente(texto):
    """Busca com pelo menos 3 letras ou números, para não devolver a base inteira."""
    return len("".join(termos_da_busca(texto))) >= 3


def com_situacao_do_contato(queryset, servico):
    """Acrescenta `situacao_contato` (do serviço) a cada escola, numa consulta só."""
    contato = ContatoEscola.objects.filter(servico=servico, escola=OuterRef("pk"))
    return queryset.annotate(situacao_contato=Subquery(contato.values("situacao")[:1]))


def contato_atualizado(servico):
    return ContatoEscola.objects.filter(servico=servico, escola=OuterRef("pk"), situacao=Situacao.ATUALIZADO)


def alunos_ativos_do_servico(servico):
    from alunos.models import Aluno

    return Aluno.objects.filter(servico=servico, situacao=Aluno.Situacao.ATIVO)


def filtrar_com_alunos_ativos(queryset, servico):
    alunos = alunos_ativos_do_servico(servico).filter(escola=OuterRef("pk"))
    return queryset.filter(Exists(alunos))


def filtrar_contato_pendente(queryset, servico):
    """Escolas cujo contato precisa atualizar ou ainda não existe no serviço (RF-14)."""
    return queryset.exclude(Exists(contato_atualizado(servico)))


def contato_do_servico(servico, escola):
    """O contato que este serviço confirmou para a escola, ou None. Nunca o de outro serviço."""
    if servico is None or escola is None:
        return None
    return (
        ContatoEscola.objects.filter(servico=servico, escola=escola)
        .select_related("confirmado_por", "atualizado_por")
        .first()
    )


def escolas_com_contato_pendente(servico):
    """Escolas com aluno ativo do serviço e contato a confirmar.

    Devolve uma lista de (escola, alunos ativos, tem_contato), em duas consultas,
    na ordem do nome da escola.
    """
    alunos = (
        alunos_ativos_do_servico(servico)
        .filter(escola__isnull=False)
        .exclude(escola_id__in=ContatoEscola.objects.filter(servico=servico, situacao=Situacao.ATUALIZADO)
                 .values("escola_id"))
        .select_related("escola")
        .only("nome", "nome_social", "escola", "escola__nome", "escola__municipio", "escola__uf",
              "escola__codigo_inep")
        .order_by("escola__nome", "escola_id", "nome")
    )
    grupos = {}
    for aluno in alunos:
        escola, lista = grupos.setdefault(aluno.escola_id, (aluno.escola, []))
        lista.append(aluno)
    if not grupos:
        return []
    com_contato = set(
        ContatoEscola.objects.filter(servico=servico, escola_id__in=list(grupos)).values_list("escola_id", flat=True)
    )
    return [(escola, lista, escola.pk in com_contato) for escola, lista in grupos.values()]


# Começos de nome que pedem "do" (masculino); os demais pedem "da".
_MASCULINOS = (
    "colégio", "colegio", "centro", "instituto", "educandário", "educandario", "liceu", "ginásio", "ginasio",
    "ciep", "ceu", "cei", "cmei", "núcleo", "nucleo", "grupo", "complexo", "jardim", "lar", "sesi", "senai",
)
_FEMININOS = (
    "escola", "ee", "eeef", "eef", "em", "emef", "emei", "emeief", "eeefm", "creche", "unidade", "fundação",
    "fundacao", "faculdade", "universidade", "associação", "associacao", "casa", "obra", "rede",
)


def com_artigo(nome):
    """"da Escola Municipal X", "do Colégio Y" ou "da escola Z", para frases como "Confirmar o contato …"."""
    primeira = (nome.split() or [""])[0].strip(".,").lower()
    if primeira in _MASCULINOS:
        return f"do {nome}"
    if primeira in _FEMININOS:
        return f"da {nome}"
    return f"da escola {nome}"


def texto_da_escola(escola):
    """Como a escola aparece num campo de busca: "12345678 · Nome (Município/UF)"."""
    return f"{escola.codigo_inep} · {escola.nome} ({escola.municipio}/{escola.uf})"


def buscar_escolas(texto, limite=20):
    """Escolas para um campo de busca, em ordem de nome. Lista vazia quando a busca é curta."""
    if not busca_suficiente(texto):
        return []
    campos = ["codigo_inep", "nome", "municipio", "uf", "funcionamento"]
    return list(filtrar_por_busca(Escola.objects.only(*campos), texto).order_by("nome", "pk")[:limite])

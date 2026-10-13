"""O que este módulo acrescenta às telas comuns (veja core/registro.py).

- Menu: "Reuniões", para quem vê as atas.
- Seção "Citações em reuniões" no perfil do aluno (RF-17), só com as citações que a pessoa vê.
- Pendência: o encaminhamento de uma citação, para o responsável, até ser concluído (RF-17).
- Agenda: as reuniões de quem participa, ou de todo o serviço (RF-44).
"""
from django.urls import reverse
from django.utils.text import Truncator

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

GRUPO = "atas"
TAMANHO_DO_RESUMO = 70

registrar_menu(ItemDeMenu("Reuniões", "reunioes:lista", "reuniao", ordem=50, grupo=GRUPO, ativo_em=("reunioes:",)))


def _resumo(texto):
    return Truncator(" ".join((texto or "").split())).chars(TAMANHO_DO_RESUMO)


# ---------------------------------------------------------------- perfil do aluno

def secao_citacoes_do_aluno(request, aluno):
    """As citações do aluno que a pessoa vê, da reunião mais recente para a mais antiga."""
    from .consultas import citacoes_visiveis, preparar_citacoes

    servico = getattr(request, "servico", None)
    if servico is None or not request.acesso.pode_ver(GRUPO):
        return None
    citacoes = list(
        citacoes_visiveis(servico, request.acesso).filter(aluno=aluno)
        .select_related("reuniao", "responsavel").order_by("-reuniao__data", "-criado_em")
    )
    preparar_citacoes(citacoes, request.user, request.acesso)
    return {
        "citacoes": citacoes,
        "pode_citar": request.acesso.pode_editar(GRUPO),
        "url_citar": f"{reverse('reunioes:lista')}?aluno={aluno.pk}",
        "proximo": f"{request.get_full_path()}#secao-citacoes",
    }


registrar_secao_do_aluno(SecaoDoAluno(
    chave="citacoes", titulo="Citações em reuniões", template="reunioes/_secao_aluno.html",
    contexto=secao_citacoes_do_aluno, grupo=GRUPO, ordem=50,
))


# ---------------------------------------------------------------- pendências

def pendencias_de_encaminhamento(request, usuario, todas):
    """Um encaminhamento com responsável e não concluído vira pendência dele (RF-17).

    Só entram as citações que a pessoa logada pode ver. Com `todas`, vêm as de todo o
    serviço, com o nome de quem é responsável.
    """
    from .consultas import citacoes_visiveis

    servico = getattr(request, "servico", None)
    if servico is None or usuario is None or not request.acesso.pode_ver(GRUPO):
        return []
    citacoes = citacoes_visiveis(servico, request.acesso).filter(concluida=False, responsavel__isnull=False)
    if not todas:
        citacoes = citacoes.filter(responsavel=usuario)
    citacoes = citacoes.select_related("aluno", "reuniao", "responsavel").order_by("prazo", "pk")
    pendencias = []
    for citacao in citacoes:
        nome = citacao.aluno.nome_curto
        resumo = _resumo(citacao.encaminhamento)
        reuniao = citacao.reuniao
        pendencias.append(Pendencia(
            titulo=f"Encaminhamento de {nome}: {resumo}" if resumo else f"Encaminhamento de {nome}",
            url=reverse("reunioes:detalhe", args=[reuniao.pk]) + f"#citacao-{citacao.pk}",
            tipo="Encaminhamento de reunião",
            prazo=citacao.prazo,
            aluno=nome,
            origem=f"Reunião {reuniao.titulo} de {reuniao.data:%d/%m}",
            responsavel=citacao.responsavel.nome_curto if todas else "",
            chave=f"citacao-{citacao.pk}",
        ))
    return pendencias


registrar_fonte_de_pendencias(pendencias_de_encaminhamento)


# ---------------------------------------------------------------- agenda

def eventos_de_reuniao(request, inicio, fim, usuario):
    """Reuniões do período: as de que `usuario` participa, ou todas do serviço com `usuario=None` (RF-44)."""
    from .consultas import participantes_em_ordem
    from .models import Reuniao

    servico = getattr(request, "servico", None)
    if servico is None or not request.acesso.pode_ver(GRUPO):
        return []
    reunioes = Reuniao.objects.filter(servico=servico, data__gte=inicio, data__lte=fim)
    if usuario is not None:
        reunioes = reunioes.filter(participantes=usuario)
    reunioes = reunioes.prefetch_related(participantes_em_ordem())
    return [
        EventoDaAgenda(
            data=reuniao.data,
            titulo=reuniao.titulo,
            url=reverse("reunioes:detalhe", args=[reuniao.pk]),
            tipo="reuniao",
            hora=reuniao.hora_inicio,
            duracao_minutos=reuniao.duracao_minutos,
            detalhe=f"Local: {reuniao.local}" if reuniao.local else "",
            situacao=reuniao.get_situacao_display(),
            cancelado=reuniao.situacao == Reuniao.Situacao.CANCELADA,
            pessoas=[pessoa.nome_curto for pessoa in reuniao.participantes.all()],
        )
        for reuniao in reunioes
    ]


registrar_fonte_da_agenda(eventos_de_reuniao)

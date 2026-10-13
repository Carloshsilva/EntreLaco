"""Pendências do módulo alunos (RF-19, RF-20, RF-21, RF-24), calculadas a partir dos dados.

`pendencias_de_alunos(request, usuario, todas)` é a fonte registrada no núcleo. Sem
`todas`, devolve as de `usuario`; com `todas`, as de todo o serviço, com o responsável
preenchido. Pendência de aluno só aparece para quem vê a identificação dos alunos, e
cada tipo de consulta é feito de uma vez para todos os alunos.
"""
import datetime

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from core.registro import Pendencia

from . import consultas

SEM_RESPONSAVEL = "Sem responsável"


def pendencias_de_alunos(request, usuario, todas):
    servico = getattr(request, "servico", None)
    if servico is None or usuario is None or not request.acesso.pode_ver("identificacao"):
        return []
    acesso_do_dono = None
    if not todas:
        acesso_do_dono = consultas.acesso_de(request, usuario)
        if not acesso_do_dono.pode_ver("identificacao"):
            return []
    hoje = timezone.localdate()
    return (
        pendencias_de_ficha(request, usuario, todas, hoje)
        + pendencias_de_revisao(request, usuario, todas, hoje, acesso_do_dono)
        + pendencias_de_matricula(request, usuario, todas, acesso_do_dono)
        + pendencias_de_domiciliar(request, usuario, todas)
    )


def _nomes_curtos(ids):
    ids = {pk for pk in ids if pk}
    if not ids:
        return {}
    return {pessoa.pk: pessoa.nome_curto for pessoa in get_user_model().objects.filter(pk__in=ids).only("nome", "email")}


def _donos(request, usuario, todas, acesso_do_dono, acao):
    """Quem recebe as pendências de uma ação: a própria pessoa, se tem a ação, ou todos que a têm."""
    if todas:
        return consultas.pessoas_com_acao(request.servico, acao) or [None]
    return [usuario] if acesso_do_dono.tem(acao) else []


def _responsavel(todas, dono):
    if not todas:
        return ""
    return dono.nome_curto if dono is not None else SEM_RESPONSAVEL


# ---------------------------------------------------------------- ficha incompleta (RF-19)

def pendencias_de_ficha(request, usuario, todas, hoje):
    """Completar a ficha: do professor da primeira aula registrada ou, sem aula, de quem cadastrou."""
    itens = consultas.alunos_com_ficha_incompleta(request.servico, responsavel=None if todas else usuario)
    nomes = _nomes_curtos(dono for _, dono, _ in itens) if todas else {}
    pendencias = []
    for aluno, dono, primeira_aula in itens:
        faltas = aluno.faltas_visiveis(request.acesso)
        if primeira_aula:
            base = primeira_aula
            origem = f"Aula de {primeira_aula:%d/%m} registrada antes do cadastro completo"
        else:
            base = timezone.localdate(aluno.criado_em)
            origem = f"Cadastro de {base:%d/%m}"
        pendencias.append(Pendencia(
            titulo=f"Completar a ficha de {aluno.nome_curto}",
            url=reverse("alunos:editar", args=[aluno.pk]),
            tipo="Ficha incompleta",
            prazo=base + datetime.timedelta(days=consultas.DIAS_PARA_COMPLETAR_A_FICHA),
            aluno=aluno.nome_curto,
            detalhe=f"Falta: {consultas.juntar(faltas)}." if faltas else "Falta completar dados da ficha.",
            origem=origem,
            responsavel=(nomes.get(dono, SEM_RESPONSAVEL) if todas else ""),
            chave=f"ficha-{aluno.pk}-{dono or 0}",
        ))
    return pendencias


# ---------------------------------------------------------------- revisão de aluno ativo (RF-21)

def _origem_da_revisao(aluno):
    referencia = consultas.referencia_da_revisao(aluno)
    if aluno.ultima_aula_ou_marcada == referencia:
        return f"Última aula em {referencia:%d/%m/%Y}"
    if aluno.ultima_mudanca == referencia:
        return f"Situação revista em {referencia:%d/%m/%Y}, sem aula desde então"
    return f"Cadastro de {referencia:%d/%m/%Y}, sem aula desde então"


def pendencias_de_revisao(request, usuario, todas, hoje, acesso_do_dono):
    """Aluno ativo sem aula no prazo do serviço: quem muda situação decide se continua ativo."""
    donos = _donos(request, usuario, todas, acesso_do_dono, "mudar_situacao")
    if not donos:
        return []
    prazo = request.servico.prazo_revisao_ativo_dias
    pendencias = []
    for aluno, venceu in consultas.alunos_para_revisar(request.servico, hoje):
        for dono in donos:
            pendencias.append(Pendencia(
                titulo=f"Revisar a situação de {aluno.nome_curto}",
                url=reverse("alunos:situacao", args=[aluno.pk]),
                tipo="Revisão de ativo",
                prazo=venceu,
                aluno=aluno.nome_curto,
                detalhe=(f"Sem aula registrada ou marcada há mais de {prazo} dias. "
                         "Decida se continua ativo, entra em pausa ou é encerrado."),
                origem=_origem_da_revisao(aluno),
                responsavel=_responsavel(todas, dono),
                chave=f"revisao-{aluno.pk}-{dono.pk if dono else 0}",
            ))
    return pendencias


# ---------------------------------------------------------------- sem matrícula (RF-20)

def pendencias_de_matricula(request, usuario, todas, acesso_do_dono):
    """Criança sem matrícula: a orientação acompanha até a matrícula. Mostra dado da vida escolar."""
    if not request.acesso.pode_ver("escolar"):
        return []
    if not todas and not acesso_do_dono.pode_ver("escolar"):
        return []
    donos = _donos(request, usuario, todas, acesso_do_dono, "mudar_situacao")
    if not donos:
        return []
    pendencias = []
    for aluno in consultas.alunos_sem_matricula(request.servico):
        for dono in donos:
            pendencias.append(Pendencia(
                titulo=f"Acompanhar a matrícula de {aluno.nome_curto}",
                url=reverse("alunos:detalhe", args=[aluno.pk]) + "#secao-ficha",
                tipo="Matrícula",
                aluno=aluno.nome_curto,
                detalhe=("A criança não tem matrícula em escola. Acompanhe até a matrícula sair e, "
                         "depois, preencha a escola de origem na ficha."),
                origem="Ficha marcada como sem matrícula",
                responsavel=_responsavel(todas, dono),
                chave=f"matricula-{aluno.pk}-{dono.pk if dono else 0}",
            ))
    return pendencias


# ---------------------------------------------------------------- professor domiciliar (RF-24)

def pendencias_de_domiciliar(request, usuario, todas):
    """Alta do TMO: o responsável pela saída vê se a criança precisa de professor domiciliar."""
    ve_saude = request.acesso.pode_ver("sensivel")
    pendencias = []
    for mudanca in consultas.saidas_que_pedem_professor_domiciliar(
        request.servico, responsavel=None if todas else usuario
    ):
        aluno = mudanca.aluno
        pendencias.append(Pendencia(
            titulo=f"Ver se {aluno.nome_curto} precisa de professor domiciliar",
            url=reverse("alunos:detalhe", args=[aluno.pk]) + "#secao-situacao",
            tipo="Professor domiciliar",
            aluno=aluno.nome_curto,
            detalhe="Converse com a família e registre o que foi decidido na seção Situação do perfil.",
            origem=f"Saída por alta{' do TMO' if ve_saude else ''} em {mudanca.data:%d/%m/%Y}",
            responsavel=_responsavel(todas, mudanca.responsavel),
            chave=f"domiciliar-{mudanca.pk}",
        ))
    return pendencias

"""Regras do módulo de aulas que mais de uma tela usa.

- Equivalência em aulas (RF-55): cada serviço diz quantos minutos de
  atendimento contam 1 aula; na Escola Móvel, 30 minutos = 1 aula.
- Quem recebe aula, quem pode dar aula e quem pode registrar em nome de outra
  pessoa (só quem tem a ação ver_tarefas_de_todos).
"""
import datetime

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from alunos.models import Aluno
from core.models import Vinculo
from core.permissoes import ACESSO_VAZIO, Acesso

from .models import Aula

REGRA_PADRAO_MINUTOS = 30
SITUACOES_QUE_RECEBEM_AULA = [Aluno.Situacao.ATIVO, Aluno.Situacao.PAUSA]


# ---------------------------------------------------------------- equivalência (RF-55)

def minutos_por_aula(servico):
    return (getattr(servico, "minutos_por_aula", None) or REGRA_PADRAO_MINUTOS)


def aulas_equivalentes(minutos, regra):
    """Quantas aulas um atendimento de `minutos` conta. O resto não arredonda para cima."""
    if not minutos or not regra:
        return 0
    return minutos // regra


def plural(numero, singular, plural_):
    return f"{numero} {singular if numero == 1 else plural_}"


def texto_da_regra(regra):
    return f"pela regra de {plural(regra, 'minuto', 'minutos')}"


def resumo_de_atendimentos(atendimentos, equivalentes, regra):
    """ "12 atendimentos, 15 aulas pela regra de 30 minutos"."""
    return (
        f"{plural(atendimentos, 'atendimento', 'atendimentos')}, "
        f"{plural(equivalentes, 'aula', 'aulas')} {texto_da_regra(regra)}"
    )


def somar_equivalentes(consulta, regra):
    """Soma das aulas equivalentes das aulas registradas de uma consulta, sem carregar os objetos."""
    minutos = consulta.filter(situacao=Aula.Situacao.REGISTRADA).values_list("duracao_minutos", flat=True)
    lista = list(minutos)
    return len(lista), sum(aulas_equivalentes(m, regra) for m in lista)


# ---------------------------------------------------------------- pessoas e alunos

def pessoas_do_servico(servico, incluir_pk=None):
    """Pessoas ativas com vínculo ativo no serviço (quem pode dar aula).

    `incluir_pk` mantém o professor atual de uma aula já salva, mesmo que tenha saído da equipe.
    """
    filtro = Q(vinculos__servico=servico, vinculos__ativo=True, is_active=True)
    if incluir_pk:
        filtro |= Q(pk=incluir_pk, vinculos__servico=servico)
    return get_user_model().objects.filter(filtro).distinct().order_by("nome")


def alunos_que_recebem_aula(servico, incluir_pk=None):
    """Alunos ativos e em pausa do serviço, por nome. `incluir_pk` mantém o aluno atual de uma aula já salva."""
    filtro = Q(situacao__in=SITUACOES_QUE_RECEBEM_AULA)
    if incluir_pk:
        filtro |= Q(pk=incluir_pk)
    return Aluno.objects.filter(servico=servico).filter(filtro).order_by("nome")


def rotulo_do_aluno(aluno):
    """Nome para escolher o aluno numa lista de opções: completo, com o nome social e o leito, para não confundir."""
    nome = f"{aluno.nome_social} ({aluno.nome})" if aluno.nome_social else aluno.nome
    return f"{nome} · leito {aluno.leito}" if aluno.leito else nome


def pode_escolher_professor(acesso):
    """Registrar ou marcar aula em nome de outra pessoa pede a ação ver_tarefas_de_todos."""
    return bool(acesso) and acesso.tem("ver_tarefas_de_todos")


def da_aula(servico, usuario):
    """A pessoa dá aula no serviço: tem perfil de professor ou já tem aula em seu nome."""
    from equipe.models import PerfilProfessor

    return (
        PerfilProfessor.objects.filter(servico=servico, usuario=usuario).exists()
        or Aula.objects.filter(servico=servico, professor=usuario).exists()
    )


def acesso_de(request, usuario):
    """O que `usuario` pode no serviço atual (quase sempre é a própria pessoa logada)."""
    if usuario is None or usuario.pk == getattr(request.user, "pk", None):
        return request.acesso
    vinculo = (
        Vinculo.objects.filter(usuario=usuario, servico=request.servico, ativo=True).select_related("papel").first()
    )
    return Acesso.do_papel(vinculo.papel) if vinculo else ACESSO_VAZIO


# ---------------------------------------------------------------- textos

def frase(texto):
    """Fecha a frase com ponto, sem repetir o ponto de um nome abreviado ("Ana P.")."""
    texto = texto.rstrip()
    return texto if texto.endswith((".", "!", "?")) else texto + "."


def faltas_da_ficha_visiveis(aluno, acesso):
    """O que falta na ficha, só nos tipos de dado que a pessoa vê (RF-07).

    O módulo de alunos sabe o tipo de dado de cada item (`faltas_visiveis`); sem ele, vale a lista simples.
    """
    if hasattr(aluno, "faltas_visiveis"):
        return aluno.faltas_visiveis(acesso)
    return aluno.faltas_da_ficha()


def juntar(itens):
    """ "a, b e c"."""
    itens = list(itens)
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


# ---------------------------------------------------------------- datas e endereços

def hoje():
    return timezone.localdate()


def ler_data(texto, padrao=None):
    try:
        return datetime.date.fromisoformat((texto or "").strip())
    except ValueError:
        return padrao


def semana_de(dia):
    inicio = dia - datetime.timedelta(days=dia.weekday())
    return inicio, inicio + datetime.timedelta(days=6)


def url_ou_none(nome, *args):
    """Endereço de uma tela de outro módulo, ou None se ela ainda não existe (RNF-08)."""
    try:
        return reverse(nome, args=args)
    except NoReverseMatch:
        return None

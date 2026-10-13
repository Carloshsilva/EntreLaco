"""Consultas e regras comuns às telas e aos encaixes das reuniões (RF-17, SEG-05, RF-07).

Toda consulta parte de `servico`; a citação de um aluno só aparece para quem vê as
atas e o tipo de dado dela (`CitacaoDeAluno.visivel_para`). As funções daqui fazem o
mesmo filtro direto no banco, para não carregar citações que a pessoa não pode ver.
"""
from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Q
from django.utils import timezone

from core.models import Vinculo
from core.permissoes import ACESSO_VAZIO, EDITAR, VER, Acesso

from .models import GRUPOS_DE_CITACAO, CitacaoDeAluno

GRUPO = "atas"

# Do mais ao menos restrito: o tipo de dado que marca as mudanças de uma citação na trilha.
_ORDEM_DE_RESTRICAO = ["sensivel", "aprendizagem", "familia", "escolar"]


def grupos_visiveis(acesso):
    """Tipos de dado de citação que a pessoa vê. Sem ver as atas, nenhum."""
    if acesso is None or not acesso.pode_ver(GRUPO):
        return []
    return [codigo for codigo, _ in GRUPOS_DE_CITACAO if acesso.pode_ver(codigo)]


def citacoes_visiveis(servico, acesso):
    """Citações do serviço que a pessoa pode ver: o mesmo que `CitacaoDeAluno.visivel_para`, no banco."""
    if servico is None:
        return CitacaoDeAluno.objects.none()
    return CitacaoDeAluno.objects.filter(servico=servico, grupo_de_dado__in=grupos_visiveis(acesso))


def pessoas_ativas(servico, que_veem=None):
    """Pessoas com vínculo ativo no serviço e login ativo.

    Com `que_veem`, só as que, pelo papel no serviço, veem esse tipo de dado.
    """
    Usuario = get_user_model()
    if servico is None:
        return Usuario.objects.none()
    # Num filter() só, para o papel ser o do vínculo com este serviço, e não o de outro.
    condicoes = {"vinculos__servico": servico, "vinculos__ativo": True, "is_active": True}
    if que_veem:
        condicoes[f"vinculos__papel__acessos__{que_veem}__in"] = [VER, EDITAR]
    return Usuario.objects.filter(**condicoes)


def pessoas_para_escolher(servico, incluir=(), que_veem=None):
    """Pessoas do serviço para um campo de escolha.

    As ativas (e, com `que_veem`, só as que veem esse tipo de dado), mais as já escolhidas
    no cadastro (`incluir`), para que quem saiu da equipe não suma de uma reunião antiga ao
    editá-la. Nunca entra pessoa de outro serviço.
    """
    Usuario = get_user_model()
    if servico is None:
        return Usuario.objects.none()
    filtro = Q(pk__in=pessoas_ativas(servico, que_veem).values("pk"))
    ids = [pk for pk in incluir if pk]
    if ids:
        do_servico = Usuario.objects.filter(vinculos__servico=servico).values("pk")
        filtro |= Q(pk__in=ids) & Q(pk__in=do_servico)
    return Usuario.objects.filter(filtro).order_by("nome")


def participantes_em_ordem():
    """Prefetch dos participantes só com o que as telas mostram (nome e nome curto)."""
    Usuario = get_user_model()
    return Prefetch("participantes", queryset=Usuario.objects.only("id", "nome", "email").order_by("nome"))


def acesso_de(usuario, servico):
    """O que `usuario` pode no serviço, pelo papel do vínculo ativo dele."""
    if usuario is None or servico is None:
        return ACESSO_VAZIO
    vinculo = Vinculo.objects.filter(usuario=usuario, servico=servico, ativo=True).select_related("papel").first()
    return Acesso.do_papel(vinculo.papel) if vinculo else ACESSO_VAZIO


def grupo_da_trilha(*grupos):
    """O tipo de dado mais restrito entre os da citação, antes e depois de salvar."""
    for grupo in _ORDEM_DE_RESTRICAO:
        if grupo in grupos:
            return grupo
    return GRUPO


def proteger_mudancas(mudancas, *grupos):
    """Marca as mudanças de uma citação com o tipo de dado dela, para a trilha (RF-07).

    Os campos da citação são todos do tipo "atas" no modelo, mas o que foi dito e o
    encaminhamento de uma citação de saúde são dado de saúde: quem não vê saúde não
    pode ler essas mudanças no histórico do aluno nem na trilha.
    """
    grupo = grupo_da_trilha(*grupos)
    if grupo == GRUPO:
        return mudancas
    return {nome: {**mudanca, "grupo": grupo} for nome, mudanca in mudancas.items()}


def pode_concluir(citacao, usuario, acesso):
    """Conclui o encaminhamento quem é o responsável por ele ou quem edita as atas."""
    if citacao.concluida:
        return False
    if acesso.pode_editar(GRUPO):
        return True
    return bool(citacao.responsavel_id) and citacao.responsavel_id == getattr(usuario, "pk", None)


def preparar_citacoes(citacoes, usuario, acesso):
    """Acrescenta a cada citação o que as telas precisam saber, sem consulta a mais.

    - `vencida`: tem prazo, já passou e o encaminhamento não foi concluído;
    - `mostrar_concluir`: há encaminhamento a concluir e a pessoa pode concluí-lo.
    """
    hoje = timezone.localdate()
    for citacao in citacoes:
        tem_encaminhamento = bool(citacao.encaminhamento.strip() or citacao.responsavel_id)
        citacao.vencida = bool(tem_encaminhamento and citacao.prazo and citacao.prazo < hoje and not citacao.concluida)
        citacao.mostrar_concluir = tem_encaminhamento and pode_concluir(citacao, usuario, acesso)
    return citacoes

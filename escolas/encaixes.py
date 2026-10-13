"""O que este módulo acrescenta às telas comuns (veja core/registro.py).

- Menu: "Escolas", para quem vê os contatos das escolas.
- Pendência: confirmar o contato de cada escola com aluno ativo do serviço cujo
  contato precisa atualizar ou ainda não existe (RF-14), para quem edita os contatos.
- Seção "Escola de origem" no perfil do aluno, com o contato do serviço.
"""
from django.urls import reverse

from core.models import Vinculo
from core.permissoes import ACESSO_VAZIO, Acesso
from core.registro import (
    ItemDeMenu,
    Pendencia,
    SecaoDoAluno,
    registrar_fonte_de_pendencias,
    registrar_menu,
    registrar_secao_do_aluno,
)

GRUPO = "escola_contato"
NOMES_NA_ORIGEM = 3

registrar_menu(ItemDeMenu("Escolas", "escolas:lista", "escola", ordem=60, grupo=GRUPO, ativo_em=("escolas:",)))


def _acesso_de(request, usuario):
    """O que `usuario` pode no serviço atual (é o da própria pessoa logada quase sempre)."""
    if usuario is None or usuario.pk == getattr(request.user, "pk", None):
        return request.acesso
    vinculo = (
        Vinculo.objects.filter(usuario=usuario, servico=request.servico, ativo=True).select_related("papel").first()
    )
    return Acesso.do_papel(vinculo.papel) if vinculo else ACESSO_VAZIO


def _origem(alunos, ve_nomes):
    if not ve_nomes:
        total = len(alunos)
        return f"{total} aluno ativo desta escola" if total == 1 else f"{total} alunos ativos desta escola"
    nomes = [aluno.nome_curto for aluno in alunos[:NOMES_NA_ORIGEM]]
    if len(alunos) == 1:
        return f"Aluno ativo desta escola: {nomes[0]}"
    resto = len(alunos) - len(nomes)
    lista = ", ".join(nomes) + (f" e mais {resto}" if resto else "")
    return f"Alunos ativos desta escola: {lista}"


def pendencias_de_contato(request, usuario, todas):
    """Uma pendência por escola com aluno ativo do serviço e contato a confirmar (RF-14).

    É de quem edita os contatos das escolas (o apoio administrativo). Com `todas`,
    vem uma por escola, com o responsável "Apoio administrativo".
    """
    from .consultas import com_artigo, escolas_com_contato_pendente

    servico = getattr(request, "servico", None)
    if servico is None or usuario is None:
        return []
    if todas:
        if not request.acesso.pode_ver(GRUPO):
            return []
        responsavel = "Apoio administrativo"
    else:
        if not _acesso_de(request, usuario).pode_editar(GRUPO):
            return []
        responsavel = ""
    # Nome do aluno ligado à escola: identificação e vida escolar (RF-07).
    ve_nomes = request.acesso.pode_ver("identificacao") and request.acesso.pode_ver("escolar")
    pendencias = []
    for escola, alunos, tem_contato in escolas_com_contato_pendente(servico):
        pendencias.append(Pendencia(
            titulo=f"Confirmar o contato {com_artigo(escola.nome)}",
            url=reverse("escolas:detalhe", args=[escola.pk]),
            tipo="Contato da escola",
            detalhe=(
                "O contato está marcado como precisa atualizar." if tem_contato
                else "O serviço ainda não tem o contato desta escola."
            ),
            origem=_origem(alunos, ve_nomes),
            responsavel=responsavel,
            chave=f"contato-{escola.pk}-{usuario.pk}",
        ))
    return pendencias


def secao_escola_do_aluno(request, aluno):
    """Escola de origem, ano, turma, RA e o contato do serviço com a escola (perfil do aluno)."""
    from .consultas import contato_do_servico

    servico = getattr(request, "servico", None)
    if servico is None or aluno.servico_id != servico.pk:
        return None
    escola = aluno.escola if aluno.escola_id else None
    ve_contato = request.acesso.pode_ver(GRUPO)
    return {
        "escola": escola,
        "sem_matricula": aluno.sem_matricula,
        "ano_escolar": aluno.get_ano_escolar_display() if aluno.ano_escolar else "",
        "turma": aluno.turma,
        "ra": aluno.ra,
        "ve_contato": ve_contato,
        "contato": contato_do_servico(servico, escola) if ve_contato else None,
    }


registrar_fonte_de_pendencias(pendencias_de_contato)
registrar_secao_do_aluno(SecaoDoAluno(
    chave="escola",
    titulo="Escola de origem",
    template="escolas/_secao_aluno.html",
    contexto=secao_escola_do_aluno,
    grupo="escolar",
    ordem=15,
))

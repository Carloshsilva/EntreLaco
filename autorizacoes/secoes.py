"""Seção "Autorizações da família" do perfil do aluno (veja core/registro.py).

O núcleo só chama `contexto_das_autorizacoes` para quem vê "Autorizações". Para cada
tipo, a situação atual (a coleta mais recente), quem colheu e quando, as coletas
anteriores (guardadas como prova) e as ações de quem edita as autorizações.
"""
from django.urls import reverse

from . import regras
from .models import Autorizacao, Tipo

Situacao = Autorizacao.Situacao


def _acoes(aluno, codigo, atual, pode_editar):
    """Botões de cada tipo, na ordem em que aparecem. Quem só vê recebe só o comprovante."""
    acoes = []
    if pode_editar and regras.pode_colher(atual):
        provisoria = atual is not None and atual.situacao == Situacao.PROVISORIA
        acoes.append({
            "rotulo": "Colher o sim definitivo" if provisoria else "Colher",
            "url": reverse("autorizacoes:colher", args=[aluno.pk, codigo]),
            "icone": "assinatura",
            "classe": "el-btn-secondary",
        })
    if pode_editar and atual is not None and atual.situacao in regras.SITUACOES_QUE_SE_REVOGAM:
        acoes.append({
            "rotulo": "Registrar revogação",
            "url": reverse("autorizacoes:revogar", args=[atual.pk]),
            "icone": "fechar",
            "classe": "el-btn-danger",
        })
    if atual is not None:
        acoes.append({
            "rotulo": "Ver comprovante",
            "url": reverse("autorizacoes:detalhe", args=[atual.pk]),
            "icone": "ver",
            "classe": "el-btn-quiet",
        })
    return acoes


def contexto_das_autorizacoes(request, aluno):
    servico = getattr(request, "servico", None)
    if servico is None or aluno.servico_id != servico.pk or not request.acesso.pode_ver(regras.GRUPO):
        return None
    pode_editar = request.acesso.pode_editar(regras.GRUPO)
    coletas = regras.coletas_do_aluno(servico, aluno)
    tipos = []
    for codigo, rotulo in Tipo.choices:
        do_tipo = coletas[codigo]
        atual = do_tipo[0] if do_tipo else None
        tipos.append({
            "codigo": codigo,
            "rotulo": rotulo,
            "rotulo_minusculo": regras.tipo_em_minusculas(codigo),
            "atual": atual,
            "anteriores": do_tipo[1:],
            "acoes": _acoes(aluno, codigo, atual, pode_editar),
        })
    contato = coletas[Tipo.CONTATO_ESCOLA][0] if coletas[Tipo.CONTATO_ESCOLA] else None
    return {
        "tipos": tipos,
        "libera_contato": contato is not None and contato.situacao in regras.SITUACOES_QUE_LIBERAM_CONTATO,
        "contato_provisorio": contato is not None and contato.situacao == Situacao.PROVISORIA,
        "pode_editar": pode_editar,
    }

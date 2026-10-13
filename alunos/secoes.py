"""Seções do perfil do aluno que este módulo acrescenta (veja core/registro.py).

Cada função recebe (request, aluno) e devolve o dicionário `dados` do template da seção.
O núcleo só chama a função para quem vê o tipo de dado da seção; dentro dela, cada
tipo de dado da ficha também é conferido (RF-07).
"""
from django.urls import reverse
from django.utils.text import capfirst

from core import auditoria
from core.permissoes import NOMES_DE_GRUPO
from core.views import eventos_do_aluno

from .formularios import FormularioDomiciliar
from .models import Aluno

Situacao = Aluno.Situacao

# A situação tem seção própria; o nome já está no topo do perfil, mas a ficha mostra tudo de novo.
CAMPOS_FORA_DA_FICHA = {"situacao", "situacao_desde"}
CAMPOS_LONGOS = {"condicoes_observacoes", "diagnostico", "observacoes_saude", "risco_evasao_motivo"}


def _idade_por_extenso(idade):
    if idade is None:
        return ""
    if idade < 1:
        return "menos de 1 ano"
    return "1 ano" if idade == 1 else f"{idade} anos"


def contexto_da_ficha(request, aluno):
    """Os dados da ficha de cada tipo que a pessoa vê."""
    from .views import edita_a_ficha

    acesso = request.acesso
    grupos = []
    for grupo, campos in Aluno.GRUPOS_DE_CAMPOS.items():
        if not acesso.pode_ver(grupo):
            continue
        itens = []
        for nome in campos:
            if nome in CAMPOS_FORA_DA_FICHA:
                continue
            valor = auditoria.valor_do_campo(aluno, nome)
            if nome == "data_nascimento" and aluno.idade is not None:
                valor = f"{valor} ({_idade_por_extenso(aluno.idade)})"
            itens.append({
                "rotulo": capfirst(Aluno._meta.get_field(nome).verbose_name),
                "valor": valor,
                "longo": nome in CAMPOS_LONGOS,
            })
        grupos.append({"chave": grupo, "titulo": NOMES_DE_GRUPO[grupo], "itens": itens})
    return {
        "grupos": grupos,
        "pode_editar": edita_a_ficha(acesso),
        "url_editar": reverse("alunos:editar", args=[aluno.pk]),
    }


def contexto_dos_responsaveis(request, aluno):
    return {
        "responsaveis": list(aluno.responsaveis.all()),
        "pode_editar": request.acesso.pode_editar("familia"),
    }


def contexto_da_situacao(request, aluno):
    """Situação atual, histórico com motivo, pessoa e data (RF-11) e o professor domiciliar (RF-24)."""
    pode_mudar = request.acesso.tem("mudar_situacao")
    ve_sensivel = request.acesso.pode_ver("sensivel")
    mudancas = list(
        aluno.mudancas_de_situacao.select_related("criado_por", "responsavel", "domiciliar_verificado_por")
        .order_by("-data", "-criado_em", "-pk")
    )
    for mudanca in mudancas:
        mudanca.aluno = aluno  # evita buscar o aluno de novo para cada mudança
        verificar = (
            mudanca.e_alta and aluno.tmo and mudanca.domiciliar_verificado_em is None
            and aluno.situacao == Situacao.ENCERRADO
        )
        responsavel_pela_saida = mudanca.responsavel_id is not None and mudanca.responsavel_id == request.user.pk
        # O bloco só existe para quem fez TMO: quem não vê saúde só o vê se precisa registrar a decisão,
        # senão o bloco contaria a essa pessoa quem fez TMO (RF-07).
        mudanca.mostrar_domiciliar = (
            mudanca.e_alta and aluno.tmo and (mudanca.domiciliar_verificado_em is not None or verificar)
            and (ve_sensivel or pode_mudar or responsavel_pela_saida)
        )
        mudanca.pode_registrar_domiciliar = verificar and (pode_mudar or responsavel_pela_saida)
        if mudanca.pode_registrar_domiciliar:
            mudanca.form_domiciliar = FormularioDomiciliar(auto_id=f"id_domiciliar_{mudanca.pk}_%s")
    return {
        "mudancas": mudancas,
        "pode_mudar": pode_mudar,
        "ve_sensivel": ve_sensivel,
    }


def contexto_do_historico(request, aluno):
    """Tudo o que aconteceu com o aluno; mudanças de tipos de dado que a pessoa não vê ficam de fora."""
    return {"eventos": eventos_do_aluno(request, aluno.pk)}

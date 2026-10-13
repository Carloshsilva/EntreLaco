"""Filtros das telas de autorizações: {% load autorizacoes_extras %}."""
from django import template

from autorizacoes.regras import CLASSES_DO_SELO

register = template.Library()


@register.filter
def classe_do_selo(situacao):
    """Classe do selo de cada situação: válida success, provisória e pendente fita, recusada e revogada danger."""
    return CLASSES_DO_SELO.get(situacao, "")

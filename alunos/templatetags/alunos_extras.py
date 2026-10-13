"""Filtros dos templates do módulo alunos: {% load alunos_extras %}."""
import re

from django import template

register = template.Library()


@register.filter
def idade_por_extenso(idade):
    """8 → "8 anos"; 1 → "1 ano"; 0 → "menos de 1 ano"; sem data → ""."""
    if idade is None or idade == "":
        return ""
    if idade < 1:
        return "menos de 1 ano"
    return "1 ano" if idade == 1 else f"{idade} anos"


@register.filter
def link_de_telefone(telefone):
    """Só os números, para o link tel: do celular."""
    return re.sub(r"\D", "", telefone or "")

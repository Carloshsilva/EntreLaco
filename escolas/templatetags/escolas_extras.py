"""Filtros das telas de escolas: {% load escolas_extras %}."""
import re

from django import template

register = template.Library()


@register.filter
def link_de_telefone(telefone):
    """Número para o link tel:, só com dígitos (e o + do código do país, se houver)."""
    return re.sub(r"[^\d+]", "", telefone or "")

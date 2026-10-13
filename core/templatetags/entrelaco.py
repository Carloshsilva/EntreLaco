"""Tags e filtros comuns dos templates: {% load entrelaco %}."""
from django import template
from django.templatetags.static import static
from django.utils.html import format_html

from core.permissoes import EDITAR, VER

register = template.Library()


@register.simple_tag
def icone(nome, classe=""):
    """Ícone decorativo do conjunto Lucide: {% icone "aluno" %}. Sempre ao lado de um texto."""
    classes = ("el-icon " + classe).strip()
    return format_html(
        '<svg class="{}" aria-hidden="true" focusable="false"><use href="{}#{}"></use></svg>',
        classes, static("img/icones.svg"), nome,
    )


@register.filter
def com_aria(campo):
    """Desenha o campo ligado à dica e ao erro por aria-describedby, e com aria-invalid quando há erro."""
    attrs = {}
    descritores = []
    if campo.help_text:
        descritores.append(f"{campo.auto_id}_dica")
    if campo.errors:
        descritores.append(f"{campo.auto_id}_erro")
        attrs["aria-invalid"] = "true"
    if descritores:
        attrs["aria-describedby"] = " ".join(descritores)
    return campo.as_widget(attrs=attrs)


@register.filter
def e_caixa(campo):
    """Campo de marcar único (sim ou não)."""
    return campo.widget_type == "checkbox"


@register.filter
def e_lista_de_opcoes(campo):
    """Grupo de opções (rádio ou várias caixas): pede fieldset e legend."""
    return campo.widget_type in {"radioselect", "checkboxselectmultiple"}


@register.filter
def e_largo(campo):
    """Campo que ocupa a linha inteira no formulário de duas colunas."""
    from django import forms

    return isinstance(
        campo.field.widget,
        (forms.Textarea, forms.FileInput, forms.CheckboxSelectMultiple, forms.RadioSelect, forms.SelectMultiple),
    )


@register.filter
def pode_ver(acesso, grupo):
    return bool(acesso) and acesso.pode(grupo, VER)


@register.filter
def pode_editar(acesso, grupo):
    return bool(acesso) and acesso.pode(grupo, EDITAR)


@register.filter
def tem_acao(acesso, acao):
    return bool(acesso) and acesso.tem(acao)


@register.simple_tag(takes_context=True)
def com_parametros(context, **kwargs):
    """Repete a busca atual trocando alguns parâmetros: href="?{% com_parametros pagina=2 %}"."""
    consulta = context["request"].GET.copy()
    for chave, valor in kwargs.items():
        if valor in (None, ""):
            consulta.pop(chave, None)
        else:
            consulta[chave] = valor
    return consulta.urlencode()


@register.filter
def get_item(dicionario, chave):
    return dicionario.get(chave) if dicionario else None


@register.filter
def campo(form, nome):
    """O campo `nome` do formulário, ou None se o papel não pode editá-lo: {% with c=form|campo:"leito" %}."""
    try:
        return form[nome]
    except KeyError:
        return None


@register.simple_tag
def campos_restantes(form, secoes):
    """Campos do formulário que não aparecem em nenhuma seção (fora o motivo da alteração)."""
    listados = {nome for secao in (secoes or []) for nome in secao.get("campos", [])}
    return [form[nome] for nome in form.fields if nome not in listados and nome != "motivo_alteracao"]

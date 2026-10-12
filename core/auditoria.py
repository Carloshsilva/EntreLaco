"""Registro e leitura da trilha de auditoria (SEG-03, SEG-04)."""
import datetime
import decimal

from django.db import models

from .models import EventoAuditoria
from .permissoes import grupo_do_campo

Acao = EventoAuditoria.Acao


def _ip(request):
    if request is None:
        return None
    encaminhado = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if encaminhado:
        return encaminhado.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def valor_legivel(valor):
    """Converte um valor de campo em algo que cabe em JSON e se lê na tela."""
    if valor is None or valor == "":
        return ""
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if isinstance(valor, datetime.datetime):
        return valor.strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, datetime.date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, datetime.time):
        return valor.strftime("%H:%M")
    if isinstance(valor, decimal.Decimal):
        return str(valor)
    if isinstance(valor, models.Model):
        return str(valor)
    if isinstance(valor, (list, tuple, set)) or hasattr(valor, "all"):
        itens = valor.all() if hasattr(valor, "all") else valor
        return ", ".join(sorted(str(item) for item in itens))
    if hasattr(valor, "name"):  # arquivos
        return valor.name.rsplit("/", 1)[-1] if valor.name else ""
    return str(valor)


def valor_do_campo(obj, nome):
    campo = obj._meta.get_field(nome)
    if campo.choices:
        return getattr(obj, f"get_{nome}_display")()
    if campo.many_to_many:
        return valor_legivel(getattr(obj, nome).all()) if obj.pk else ""
    return valor_legivel(getattr(obj, nome))


def fotografar(obj, campos):
    """Valores legíveis dos campos de um objeto, para comparar antes e depois."""
    return {nome: valor_do_campo(obj, nome) for nome in campos}


def comparar(modelo, antes, depois):
    """Monta o dicionário de mudanças só com os campos que mudaram."""
    mudancas = {}
    for nome, novo in depois.items():
        velho = antes.get(nome, "")
        if velho != novo:
            campo = modelo._meta.get_field(nome)
            mudancas[nome] = {
                "rotulo": str(campo.verbose_name),
                "grupo": grupo_do_campo(modelo, nome),
                "de": velho,
                "para": novo,
            }
    return mudancas


def registrar(request, acao, obj=None, *, mudancas=None, motivo="", descricao="", servico=None, aluno=None, usuario=None):
    """Grava um evento na trilha. Chame dentro da mesma transação da mudança."""
    usuario = usuario or (getattr(request, "user", None) if request is not None else None)
    if usuario is not None and not getattr(usuario, "is_authenticated", False):
        usuario = None
    if servico is None:
        servico = getattr(obj, "servico", None) or getattr(request, "servico", None)
    if aluno is None and obj is not None:
        aluno_id = _aluno_id(obj)
    else:
        aluno_id = getattr(aluno, "pk", aluno)
    return EventoAuditoria.objects.create(
        servico=servico,
        usuario=usuario,
        usuario_nome=(usuario.nome if usuario else ""),
        acao=acao,
        modelo=obj._meta.label if obj is not None else "",
        objeto_id=str(obj.pk) if obj is not None and obj.pk is not None else "",
        objeto_repr=str(obj)[:200] if obj is not None else "",
        aluno_id=aluno_id,
        mudancas=mudancas or {},
        motivo=motivo or "",
        descricao=descricao[:255],
        ip=_ip(request),
    )


def _aluno_id(obj):
    if obj._meta.label == "alunos.Aluno":
        return obj.pk
    return getattr(obj, "aluno_id", None)


def mudancas_visiveis(evento, acesso):
    """Só as mudanças de tipos de dado que a pessoa pode ver (RF-07 vale também na trilha)."""
    visiveis = {}
    for nome, mudanca in (evento.mudancas or {}).items():
        grupo = mudanca.get("grupo")
        if grupo is None or acesso.pode_ver(grupo):
            visiveis[nome] = mudanca
    return visiveis

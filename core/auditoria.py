"""Registro e leitura da trilha de auditoria (SEG-03, SEG-04)."""
import datetime
import decimal

from django.db import models
from django.utils import timezone

from .models import EventoAuditoria
from .permissoes import CODIGOS_DE_GRUPO, grupo_do_campo

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
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
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


SEPARADOR_DE_GRUPOS = "+"


def grupo_do_registro(obj):
    """Tipo de dado do registro inteiro, quando dá para dizer: o modelo pode definir `grupo_na_trilha()`;
    senão, vale o único tipo de GRUPOS_DE_CAMPOS. Modelo com vários tipos (a ficha do aluno) fica sem grupo
    e a visibilidade é decidida campo a campo.

    `grupo_na_trilha()` pode devolver vários tipos (por exemplo, a citação de saúde numa ata): o evento
    fica gravado como "atas+sensivel" e só aparece para quem vê todos eles."""
    if obj is None:
        return ""
    if hasattr(obj, "grupo_na_trilha"):
        grupo = obj.grupo_na_trilha() or ""
        if isinstance(grupo, (list, tuple, set, frozenset)):
            return SEPARADOR_DE_GRUPOS.join(sorted(set(grupo)))
        return grupo
    grupos = list(getattr(obj, "GRUPOS_DE_CAMPOS", {}) or {})
    return grupos[0] if len(grupos) == 1 else ""


def grupos_do_evento(evento):
    return [g for g in (evento.grupo or "").split(SEPARADOR_DE_GRUPOS) if g]


def filtrar_visiveis(eventos, acesso):
    """Tira do queryset os eventos de registros cujo tipo de dado a pessoa não vê (RF-07 na trilha)."""
    for grupo in CODIGOS_DE_GRUPO:
        if not acesso.pode_ver(grupo):
            eventos = eventos.exclude(grupo__regex=rf"(^|\{SEPARADOR_DE_GRUPOS}){grupo}(\{SEPARADOR_DE_GRUPOS}|$)")
    return eventos


def registrar(request, acao, obj=None, *, mudancas=None, motivo="", descricao="", servico=None, aluno=None, usuario=None,
              grupo=None):
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
        grupo=grupo if grupo is not None else grupo_do_registro(obj),
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


def evento_visivel(evento, acesso):
    """O evento inteiro some para quem não vê o tipo de dado do registro."""
    return all(acesso.pode_ver(grupo) for grupo in grupos_do_evento(evento))


def preparar_para_exibir(eventos, acesso):
    """Filtra os eventos visíveis e marca o que de cada um a pessoa pode ver.

    - `mudancas_permitidas`: só as mudanças em tipos de dado que ela vê;
    - `motivo_visivel`: o motivo aparece só se ela vê alguma das mudanças (ou se o evento não tem mudanças),
      porque o motivo de uma edição de saúde pode falar de saúde.
    """
    visiveis = []
    for evento in eventos:
        if not evento_visivel(evento, acesso):
            continue
        evento.mudancas_permitidas = mudancas_visiveis(evento, acesso)
        evento.mudancas_escondidas = len(evento.mudancas or {}) - len(evento.mudancas_permitidas)
        evento.motivo_visivel = bool(evento.mudancas_permitidas) or not evento.mudancas
        # O nome do registro de um aluno (objeto_repr) só aparece para quem vê a identificação.
        evento.objeto_visivel = not evento.aluno_id or acesso.pode_ver("identificacao")
        visiveis.append(evento)
    return visiveis

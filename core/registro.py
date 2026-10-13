"""Pontos de encaixe entre os módulos (RNF-08).

Cada app registra, no `ready()` do seu AppConfig, o que ela acrescenta às telas
comuns: itens do menu, seções do perfil do aluno, pendências da tela inicial e
eventos da agenda. Assim o núcleo não importa as apps, e ligar ou desligar uma
app não mexe nas outras.
"""
from dataclasses import dataclass, field
import datetime

from django.urls import NoReverseMatch, reverse


# ---------------------------------------------------------------- menu

@dataclass(frozen=True)
class ItemDeMenu:
    rotulo: str
    url_nome: str
    icone: str
    ordem: int = 50
    principal: bool = False  # aparece na barra de baixo do celular (no máximo 4)
    grupo: str | None = None  # tipo de dado que a pessoa precisa ao menos ver
    grupos: tuple = ()  # vários tipos de dado, todos exigidos (além de `grupo`)
    acao: str | None = None  # ação de ACOES exigida
    configurar: bool = False  # só quem configura o serviço
    ativo_em: tuple = ()  # prefixos de nome de URL que marcam o item como atual


_MENU: list[ItemDeMenu] = []


def registrar_menu(item: ItemDeMenu):
    if all(existente.url_nome != item.url_nome for existente in _MENU):
        _MENU.append(item)


def menu_para(request):
    """Itens que a pessoa pode ver, com a URL resolvida e a marca de item atual."""
    acesso = getattr(request, "acesso", None)
    if acesso is None or getattr(request, "servico", None) is None:
        return []
    atual = getattr(getattr(request, "resolver_match", None), "view_name", "") or ""
    itens = []
    for item in sorted(_MENU, key=lambda i: (i.ordem, i.rotulo)):
        if item.configurar and not acesso.configurar:
            continue
        if item.acao and not acesso.tem(item.acao):
            continue
        if item.grupo and not acesso.pode_ver(item.grupo):
            continue
        if any(not acesso.pode_ver(g) for g in item.grupos):
            continue
        try:
            url = reverse(item.url_nome)
        except NoReverseMatch:
            continue
        prefixos = item.ativo_em or (item.url_nome,)
        casamento = max((len(p) for p in prefixos if atual == p or atual.startswith(p)), default=0)
        itens.append({
            "rotulo": item.rotulo,
            "url": url,
            "icone": item.icone,
            "principal": item.principal,
            "casamento": casamento,
        })
    # Só o item que casa com mais precisão fica marcado como atual.
    melhor = max((i["casamento"] for i in itens), default=0)
    for i in itens:
        i["atual"] = melhor > 0 and i.pop("casamento") == melhor
        i.pop("casamento", None)
    return itens


# ---------------------------------------------------------------- perfil do aluno

@dataclass(frozen=True)
class SecaoDoAluno:
    """Uma seção do perfil do aluno.

    `contexto(request, aluno)` devolve um dicionário para o template, ou None
    para esconder a seção. A seção só aparece para quem vê o `grupo`.
    """

    chave: str
    titulo: str
    template: str
    contexto: object
    grupo: str
    ordem: int = 50


_SECOES_DO_ALUNO: list[SecaoDoAluno] = []


def registrar_secao_do_aluno(secao: SecaoDoAluno):
    if all(existente.chave != secao.chave for existente in _SECOES_DO_ALUNO):
        _SECOES_DO_ALUNO.append(secao)


def secoes_do_aluno(request, aluno):
    secoes = []
    for secao in sorted(_SECOES_DO_ALUNO, key=lambda s: (s.ordem, s.titulo)):
        if not request.acesso.pode_ver(secao.grupo):
            continue
        contexto = secao.contexto(request, aluno)
        if contexto is None:
            continue
        secoes.append({"chave": secao.chave, "titulo": secao.titulo, "template": secao.template, "contexto": contexto})
    return secoes


# ---------------------------------------------------------------- pendências

@dataclass
class Pendencia:
    """Uma pendência calculada a partir dos dados (RF-43).

    Nesta versão as pendências não são guardadas: cada app diz o que está
    faltando, e a tela inicial junta tudo. O quadro com Kanban, backlog e
    regras configuráveis (RF-38 a RF-42, RF-60) vem depois.
    """

    titulo: str
    url: str
    tipo: str  # rótulo curto do tipo, ex.: "Ficha incompleta"
    prazo: datetime.date | None = None
    aluno: str = ""  # nome curto do aluno, quando houver
    detalhe: str = ""
    origem: str = ""  # por que a pendência existe, ex.: "Aula de 10/10 registrada sem ficha"
    responsavel: str = ""  # nome de quem deve agir, na visão de todas as pendências
    chave: str = field(default="")  # identifica a pendência para não repetir

    @property
    def situacao_do_prazo(self):
        if self.prazo is None:
            return "sem_prazo"
        from django.utils import timezone

        hoje = timezone.localdate()
        if self.prazo < hoje:
            return "vencida"
        if self.prazo == hoje:
            return "hoje"
        return "no_prazo"


# Função(request, usuario, todas) -> lista de Pendencia.
# `usuario` é de quem são as pendências; `todas=True` pede as de todo o serviço
# (só para quem tem a ação ver_tarefas_de_todos).
_FONTES_DE_PENDENCIA: list = []


def registrar_fonte_de_pendencias(funcao):
    if funcao not in _FONTES_DE_PENDENCIA:
        _FONTES_DE_PENDENCIA.append(funcao)


def pendencias_para(request, usuario=None, todas=False):
    usuario = usuario or request.user
    vistas = set()
    resultado = []
    for funcao in _FONTES_DE_PENDENCIA:
        for pendencia in funcao(request, usuario, todas) or []:
            chave = pendencia.chave or (pendencia.tipo, pendencia.url, pendencia.responsavel)
            if chave in vistas:
                continue
            vistas.add(chave)
            resultado.append(pendencia)
    ordem = {"vencida": 0, "hoje": 1, "no_prazo": 2, "sem_prazo": 3}
    resultado.sort(key=lambda p: (ordem[p.situacao_do_prazo], p.prazo or datetime.date.max, p.titulo))
    return resultado


# ---------------------------------------------------------------- agenda

@dataclass
class EventoDaAgenda:
    data: datetime.date
    titulo: str
    url: str
    tipo: str  # "aula" ou "reuniao"
    hora: datetime.time | None = None
    duracao_minutos: int | None = None
    detalhe: str = ""
    situacao: str = ""  # rótulo legível, ex.: "Marcada", "Registrada"
    cancelado: bool = False
    pessoas: list = field(default_factory=list)  # nomes curtos de quem participa


# Função(request, inicio, fim, usuario) -> lista de EventoDaAgenda.
# `usuario=None` pede os eventos de todo o serviço.
_FONTES_DA_AGENDA: list = []


def registrar_fonte_da_agenda(funcao):
    if funcao not in _FONTES_DA_AGENDA:
        _FONTES_DA_AGENDA.append(funcao)


def eventos_da_agenda(request, inicio, fim, usuario=None):
    eventos = []
    for funcao in _FONTES_DA_AGENDA:
        eventos.extend(funcao(request, inicio, fim, usuario) or [])
    eventos.sort(key=lambda e: (e.data, e.hora or datetime.time.min, e.titulo))
    return eventos


def conferir_secoes_do_aluno(app_configs=None, **kwargs):
    """System check: toda seção registrada aponta para um template que existe."""
    from django.core.checks import Error
    from django.template import TemplateDoesNotExist
    from django.template.loader import get_template

    erros = []
    for secao in _SECOES_DO_ALUNO:
        try:
            get_template(secao.template)
        except TemplateDoesNotExist:
            erros.append(Error(
                f"A seção do aluno '{secao.chave}' aponta para o template {secao.template}, que não existe.",
                id="entrelaco.E001",
            ))
    return erros

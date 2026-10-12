"""Permissões da EntreLaço.

Cada papel de um serviço define, para cada *tipo de dado*, se a pessoa não vê,
vê ou edita (RF-07), e quais *ações* ela pode fazer. A permissão de configurar o
serviço é à parte e só o administrador da plataforma libera (RF-03, RF-04).

Os modelos dizem a que tipo de dado pertence cada campo em `GRUPOS_DE_CAMPOS`;
formulários, telas, PDFs e a trilha de auditoria usam essa mesma tabela para
decidir o que mostrar.
"""
from dataclasses import dataclass, field

NENHUM, VER, EDITAR = "nenhum", "ver", "editar"
NIVEIS = [(NENHUM, "Não vê"), (VER, "Vê"), (EDITAR, "Vê e edita")]
_ORDEM = {NENHUM: 0, VER: 1, EDITAR: 2}

GRUPOS_DE_DADOS = [
    ("identificacao", "Identificação do aluno", "Nome, nascimento, unidade, leito, internação e situação."),
    ("aprendizagem", "Condições e aprendizagem", "Visão, audição, fala, motricidade, alfabetização e reprovação."),
    ("sensivel", "Saúde e dados sensíveis", "Diagnóstico, tratamento, TMO, raça ou cor e observações de saúde."),
    ("familia", "Família e responsáveis", "Nome e contatos dos responsáveis."),
    ("escolar", "Vida escolar", "Escola de origem, matrícula, ano escolar e risco de evasão."),
    ("autorizacoes", "Autorizações", "Uso dos dados e contato com a escola."),
    ("aulas", "Aulas", "Agenda e registros de aula, com fotos das atividades."),
    ("atas", "Reuniões e atas", "Calendário de reuniões, atas e citações de alunos."),
    ("documentos", "Documentos digitalizados", "Fotos e scans guardados no histórico do aluno."),
    ("escola_contato", "Contatos das escolas", "E-mail, telefone e quem atende em cada escola."),
]
CODIGOS_DE_GRUPO = [codigo for codigo, _, _ in GRUPOS_DE_DADOS]
NOMES_DE_GRUPO = {codigo: nome for codigo, nome, _ in GRUPOS_DE_DADOS}

ACOES = [
    ("gerir_equipe", "Cadastrar pessoas da equipe e atribuir papéis"),
    ("mudar_situacao", "Mudar a situação do aluno (ativo, em pausa, encerrado)"),
    ("ver_trilha", "Ver a trilha de auditoria"),
    ("ver_tarefas_de_todos", "Ver as pendências de todas as pessoas"),
]
CODIGOS_DE_ACAO = [codigo for codigo, _ in ACOES]


def nivel_valido(nivel):
    return nivel if nivel in _ORDEM else NENHUM


@dataclass
class Acesso:
    """O que a pessoa logada pode fazer no serviço atual."""

    niveis: dict = field(default_factory=dict)
    acoes: frozenset = frozenset()
    configurar: bool = False

    @classmethod
    def do_papel(cls, papel):
        if papel is None:
            return cls()
        niveis = {grupo: nivel_valido((papel.acessos or {}).get(grupo, NENHUM)) for grupo in CODIGOS_DE_GRUPO}
        acoes = frozenset(a for a in (papel.acoes or []) if a in CODIGOS_DE_ACAO)
        if papel.pode_configurar:
            # Quem configura o serviço também cuida da equipe e vê a trilha.
            acoes = acoes | {"gerir_equipe", "ver_trilha", "ver_tarefas_de_todos"}
        return cls(niveis=niveis, acoes=acoes, configurar=papel.pode_configurar)

    def nivel(self, grupo):
        return self.niveis.get(grupo, NENHUM)

    def pode_ver(self, grupo):
        return _ORDEM[self.nivel(grupo)] >= _ORDEM[VER]

    def pode_editar(self, grupo):
        return _ORDEM[self.nivel(grupo)] >= _ORDEM[EDITAR]

    def tem(self, acao):
        return acao in self.acoes

    def pode(self, grupo, modo):
        return self.pode_editar(grupo) if modo == EDITAR else self.pode_ver(grupo)


ACESSO_VAZIO = Acesso()


def grupo_do_campo(modelo, campo):
    for grupo, campos in getattr(modelo, "GRUPOS_DE_CAMPOS", {}).items():
        if campo in campos:
            return grupo
    return None


def campos_permitidos(modelo, acesso, modo=VER, campos=None):
    """Campos do modelo que a pessoa pode ver (modo='ver') ou editar (modo='editar').

    Campos que não pertencem a nenhum grupo em GRUPOS_DE_CAMPOS ficam de fora:
    todo campo exibível precisa ter um tipo de dado declarado.
    """
    permitidos = []
    for grupo, campos_do_grupo in getattr(modelo, "GRUPOS_DE_CAMPOS", {}).items():
        if acesso.pode(grupo, modo):
            permitidos.extend(campos_do_grupo)
    if campos is not None:
        permitidos = [c for c in campos if c in permitidos]
    return permitidos

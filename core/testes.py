"""Ajudas para os testes de todas as apps. Só dados inventados.

Exemplo:
    servico = criar_servico()
    professor = criar_pessoa(servico, papel=criar_papel(servico, "Professor", editar=["identificacao", "aulas"]))
    self.client.force_login(professor)
"""
import itertools

from core.models import Papel, Servico, Usuario, Vinculo
from core.permissoes import CODIGOS_DE_GRUPO, EDITAR, NENHUM, VER

_contador = itertools.count(1)


def criar_servico(nome=None, **extra):
    numero = next(_contador)
    nome = nome or f"Serviço de teste {numero}"
    return Servico.objects.create(nome=nome, slug=f"servico-teste-{numero}", **extra)


def criar_papel(servico, nome=None, *, editar=(), ver=(), acoes=(), configurar=False, tudo=None):
    """Papel com os tipos de dado pedidos. `tudo="editar"` ou `tudo="ver"` libera todos os tipos."""
    acessos = {grupo: NENHUM for grupo in CODIGOS_DE_GRUPO}
    if tudo:
        acessos = {grupo: tudo for grupo in CODIGOS_DE_GRUPO}
    for grupo in ver:
        acessos[grupo] = VER
    for grupo in editar:
        acessos[grupo] = EDITAR
    return Papel.objects.create(
        servico=servico, nome=nome or f"Papel {next(_contador)}", acessos=acessos, acoes=list(acoes),
        pode_configurar=configurar,
    )


def criar_pessoa(servico=None, papel=None, *, nome=None, email=None, senha="senha-de-teste-123", **extra):
    """Pessoa com vínculo ao serviço. Quem configura já vem com a verificação em duas etapas ativa."""
    numero = next(_contador)
    usuario = Usuario.objects.create_user(
        email=email or f"pessoa{numero}@exemplo.org", password=senha, nome=nome or f"Pessoa Inventada {numero}",
        **extra,
    )
    if servico is not None:
        papel = papel or criar_papel(servico)
        Vinculo.objects.create(usuario=usuario, servico=servico, papel=papel)
        if papel.pode_configurar:
            usuario.totp_ativo = True
            usuario.totp_segredo = "JBSWY3DPEHPK3PXP"
            usuario.save(update_fields=["totp_ativo", "totp_segredo"])
    return usuario


def criar_professor(servico, **kwargs):
    papel = Papel.objects.filter(servico=servico, nome="Professor").first() or criar_papel(
        servico, "Professor",
        editar=["identificacao", "aprendizagem", "sensivel", "familia", "escolar", "autorizacoes", "aulas",
                "documentos"],
        ver=["atas", "escola_contato"],
    )
    return criar_pessoa(servico, papel, **kwargs)


def criar_supervisao(servico, **kwargs):
    papel = Papel.objects.filter(servico=servico, nome="Supervisão").first() or criar_papel(
        servico, "Supervisão", tudo=EDITAR, acoes=["gerir_equipe", "mudar_situacao", "ver_trilha",
                                                   "ver_tarefas_de_todos"], configurar=True,
    )
    return criar_pessoa(servico, papel, **kwargs)


def criar_apoio(servico, **kwargs):
    """Apoio administrativo: não vê saúde nem aprendizagem (RF-07)."""
    papel = Papel.objects.filter(servico=servico, nome="Apoio administrativo").first() or criar_papel(
        servico, "Apoio administrativo",
        editar=["escolar", "documentos", "escola_contato"], ver=["identificacao", "familia", "autorizacoes"],
    )
    return criar_pessoa(servico, papel, **kwargs)


def criar_aluno(servico, nome="Aluno Inventado da Silva", **extra):
    from alunos.models import Aluno

    return Aluno.objects.create(servico=servico, nome=nome, **extra)


def criar_escola(nome="Escola Municipal Inventada", codigo=None, **extra):
    from escolas.models import Escola

    codigo = codigo or f"9{next(_contador):07d}"
    extra.setdefault("municipio", "Cidade Fictícia")
    extra.setdefault("uf", "SP")
    return Escola.objects.create(codigo_inep=codigo, nome=nome, **extra)

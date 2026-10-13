"""O que este módulo acrescenta às telas comuns (veja core/registro.py).

- Menu: "Alunos" (quem vê a identificação) e "Ordem de atendimento" (quem vê as aulas;
  a tela também pede a identificação).
- Seções do perfil do aluno: Ficha (10), Responsáveis (20), Situação (70) e Histórico de alterações (90).
- Pendências: ficha incompleta (RF-19), matrícula (RF-20), revisão de ativo (RF-21) e
  professor domiciliar na alta do TMO (RF-24).
"""
from core.registro import (
    ItemDeMenu,
    SecaoDoAluno,
    registrar_fonte_de_pendencias,
    registrar_menu,
    registrar_secao_do_aluno,
)

from .pendencias import pendencias_de_alunos
from .secoes import contexto_da_ficha, contexto_da_situacao, contexto_do_historico, contexto_dos_responsaveis

registrar_menu(ItemDeMenu("Alunos", "alunos:lista", "alunos", ordem=20, principal=True, grupo="identificacao", ativo_em=("alunos:",)))
registrar_menu(ItemDeMenu("Ordem de atendimento", "alunos:fila", "fila", ordem=25, grupos=("identificacao", "aulas"), ativo_em=("alunos:fila",)))

registrar_secao_do_aluno(SecaoDoAluno(
    chave="ficha", titulo="Ficha", template="alunos/_secao_ficha.html",
    contexto=contexto_da_ficha, grupo="identificacao", ordem=10,
))
registrar_secao_do_aluno(SecaoDoAluno(
    chave="responsaveis", titulo="Responsáveis", template="alunos/_secao_responsaveis.html",
    contexto=contexto_dos_responsaveis, grupo="familia", ordem=20,
))
registrar_secao_do_aluno(SecaoDoAluno(
    chave="situacao", titulo="Situação", template="alunos/_secao_situacao.html",
    contexto=contexto_da_situacao, grupo="identificacao", ordem=70,
))
registrar_secao_do_aluno(SecaoDoAluno(
    chave="historico", titulo="Histórico de alterações", template="alunos/_secao_historico.html",
    contexto=contexto_do_historico, grupo="identificacao", ordem=90,
))

registrar_fonte_de_pendencias(pendencias_de_alunos)

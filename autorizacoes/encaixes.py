"""O que este módulo acrescenta às telas comuns (veja core/registro.py).

- Seção "Autorizações da família" no perfil do aluno (ordem 30), para quem vê "Autorizações".
- Pendências: autorização pendente ou provisória, de quem colheu (RF-64, RF-27), e aluno
  ativo sem nenhuma coleta de um tipo, do professor da primeira aula ou de quem cadastrou (RF-19).
- Sem item de menu próprio: os termos ficam em Configuração, e as autorizações no perfil do aluno.
"""
from core.registro import SecaoDoAluno, registrar_fonte_de_pendencias, registrar_secao_do_aluno

from .pendencias import pendencias_de_autorizacoes
from .secoes import contexto_das_autorizacoes

registrar_secao_do_aluno(SecaoDoAluno(
    chave="autorizacoes",
    titulo="Autorizações da família",
    template="autorizacoes/_secao_aluno.html",
    contexto=contexto_das_autorizacoes,
    grupo="autorizacoes",
    ordem=30,
))

registrar_fonte_de_pendencias(pendencias_de_autorizacoes)

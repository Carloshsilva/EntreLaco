"""O que este módulo acrescenta às telas comuns (veja core/registro.py)."""
from core.registro import ItemDeMenu, registrar_menu

registrar_menu(ItemDeMenu("Alunos", "alunos:lista", "alunos", ordem=20, principal=True, grupo="identificacao", ativo_em=("alunos:",)))
registrar_menu(ItemDeMenu("Ordem de atendimento", "alunos:fila", "fila", ordem=25, grupo="identificacao", ativo_em=("alunos:fila",)))

"""O que este módulo acrescenta às telas comuns (veja core/registro.py)."""
from core.registro import ItemDeMenu, registrar_menu

registrar_menu(ItemDeMenu("Escolas", "escolas:lista", "escola", ordem=60, grupo="escola_contato", ativo_em=("escolas:",)))

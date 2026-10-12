"""O que este módulo acrescenta às telas comuns (veja core/registro.py)."""
from core.registro import ItemDeMenu, registrar_menu

registrar_menu(ItemDeMenu("Reuniões", "reunioes:lista", "reuniao", ordem=50, grupo="atas", ativo_em=("reunioes:",)))

"""O que este módulo acrescenta às telas comuns (veja core/registro.py)."""
from core.registro import ItemDeMenu, registrar_menu

registrar_menu(ItemDeMenu("Aulas", "aulas:lista", "aula", ordem=40, principal=True, grupo="aulas", ativo_em=("aulas:",)))

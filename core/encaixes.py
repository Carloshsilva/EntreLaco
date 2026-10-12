"""O que este módulo acrescenta às telas comuns (veja core/registro.py)."""
from core.registro import ItemDeMenu, registrar_menu

registrar_menu(ItemDeMenu("Início", "inicio", "inicio", ordem=10, principal=True, ativo_em=("inicio",)))
registrar_menu(ItemDeMenu("Agenda", "agenda", "agenda", ordem=30, principal=True, ativo_em=("agenda",)))
registrar_menu(ItemDeMenu("Trilha de auditoria", "trilha", "trilha", ordem=90, acao="ver_trilha", ativo_em=("trilha",)))

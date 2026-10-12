"""O que este módulo acrescenta às telas comuns (veja core/registro.py)."""
from core.registro import ItemDeMenu, registrar_menu

registrar_menu(ItemDeMenu("Equipe", "equipe:pessoas", "equipe", ordem=70, acao="gerir_equipe", ativo_em=("equipe:pessoa", "equipe:pessoas", "equipe:professor")))
registrar_menu(ItemDeMenu("Configuração", "equipe:configuracao", "config", ordem=80, configurar=True, ativo_em=("equipe:configuracao", "equipe:papel", "equipe:papeis", "equipe:componente", "autorizacoes:termo", "aulas:habilidade")))

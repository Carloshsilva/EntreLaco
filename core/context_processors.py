from django.conf import settings

from .permissoes import NOMES_DE_GRUPO
from .registro import menu_para

# Cada módulo tem static/css/modulos/<app>.css e static/js/modulos/<app>.js, carregados em todas as telas.
MODULOS = ["equipe", "escolas", "alunos", "autorizacoes", "aulas", "reunioes", "documentos"]


def entrelaco(request):
    menu = menu_para(request) if getattr(request, "user", None) is not None and request.user.is_authenticated else []
    vinculo = getattr(request, "vinculo", None)
    outros_servicos = []
    if vinculo is not None:
        outros_servicos = [
            v.servico for v in request.user.vinculos.filter(ativo=True, servico__ativo=True).select_related("servico")
            if v.servico_id != vinculo.servico_id
        ]
    return {
        "AMBIENTE_DE_TESTE": settings.AMBIENTE_DE_TESTE,
        "MODULOS": MODULOS,
        "servico_atual": getattr(request, "servico", None),
        "vinculo_atual": vinculo,
        "outros_servicos": outros_servicos,
        "acesso": getattr(request, "acesso", None),
        "NOMES_DE_GRUPO": NOMES_DE_GRUPO,
        "menu": menu,
        "menu_principal": [item for item in menu if item["principal"]][:4],
    }

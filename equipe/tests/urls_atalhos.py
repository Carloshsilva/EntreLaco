"""URLs só para testar os atalhos da configuração do serviço.

As telas de termos de autorização e da lista da BNCC são de outras apps e podem ainda não existir
quando os testes da equipe rodam. Aqui elas viram marcadores, com os nomes do contrato de URLs.
"""
from django.urls import include, path

from core.views import em_construcao

termos = ([path("termos/", em_construcao, name="termos")], "autorizacoes")
bncc = ([path("bncc/", em_construcao, name="habilidades")], "aulas")

urlpatterns = [
    path("equipe/", include("equipe.urls")),
    path("autorizacoes/", include(termos)),
    path("aulas/", include(bncc)),
    path("", include("core.urls")),
]

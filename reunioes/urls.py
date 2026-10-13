from django.urls import path

from . import views

app_name = "reunioes"

urlpatterns = [
    path("", views.ListaDeReunioes.as_view(), name="lista"),
    path("nova/", views.NovaReuniao.as_view(), name="nova"),
    path("<int:pk>/", views.DetalheDaReuniao.as_view(), name="detalhe"),
    path("<int:pk>/editar/", views.EditarReuniao.as_view(), name="editar"),
    path("<int:pk>/citacoes/nova/", views.NovaCitacao.as_view(), name="citacao_nova"),
    path("citacoes/<int:pk>/editar/", views.EditarCitacao.as_view(), name="citacao_editar"),
    path("citacoes/<int:pk>/concluir/", views.concluir_citacao, name="citacao_concluir"),
]

from django.urls import path

from . import views

app_name = "autorizacoes"

urlpatterns = [
    path("aluno/<int:aluno_pk>/<str:tipo>/", views.colher, name="colher"),
    path("<int:pk>/", views.DetalheDaAutorizacao.as_view(), name="detalhe"),
    path("<int:pk>/assinar/", views.assinar, name="assinar"),
    path("<int:pk>/revogar/", views.revogar, name="revogar"),
    path("<int:pk>/arquivo/", views.arquivo, name="arquivo"),
    path("<int:pk>/assinatura/", views.imagem_assinatura, name="imagem_assinatura"),
    path("termos/", views.ListaDeTermos.as_view(), name="termos"),
    path("termos/novo/", views.NovoTermo.as_view(), name="termo_novo"),
    path("termos/<int:pk>/", views.DetalheDoTermo.as_view(), name="termo_detalhe"),
    path("termos/<int:pk>/editar/", views.EditarTermo.as_view(), name="termo_editar"),
]

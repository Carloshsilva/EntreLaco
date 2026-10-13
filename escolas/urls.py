from django.urls import path

from . import views

app_name = "escolas"

urlpatterns = [
    path("", views.ListaDeEscolas.as_view(), name="lista"),
    path("nova/", views.NovaEscola.as_view(), name="nova"),
    path("buscar/", views.buscar, name="buscar"),
    path("<int:pk>/", views.DetalheDaEscola.as_view(), name="detalhe"),
    path("<int:pk>/contato/", views.contato, name="contato"),
    path("<int:pk>/contato/confirmar/", views.confirmar_contato, name="confirmar_contato"),
]

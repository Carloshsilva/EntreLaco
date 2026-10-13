from django.urls import path

from . import views

app_name = "documentos"

urlpatterns = [
    path("aluno/<int:aluno_pk>/novo/", views.NovoDocumento.as_view(), name="novo"),
    path("<int:pk>/", views.DetalheDoDocumento.as_view(), name="detalhe"),
    path("<int:pk>/editar/", views.EditarDocumento.as_view(), name="editar"),
    path("<int:pk>/arquivo/", views.arquivo, name="arquivo"),
]

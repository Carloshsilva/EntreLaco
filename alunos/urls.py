from django.urls import path

from . import views

app_name = "alunos"

urlpatterns = [
    path("", views.ListaDeAlunos.as_view(), name="lista"),
    path("novo/", views.NovoAluno.as_view(), name="novo"),
    path("fila/", views.FilaDeAtendimento.as_view(), name="fila"),
    path("<int:pk>/", views.DetalheDoAluno.as_view(), name="detalhe"),
    path("<int:pk>/editar/", views.EditarAluno.as_view(), name="editar"),
    path("<int:pk>/situacao/", views.mudar_situacao, name="situacao"),
    path("<int:pk>/responsaveis/novo/", views.NovoResponsavel.as_view(), name="responsavel_novo"),
    path("responsaveis/<int:pk>/editar/", views.EditarResponsavel.as_view(), name="responsavel_editar"),
    path("saidas/<int:pk>/domiciliar/", views.domiciliar, name="domiciliar"),
]

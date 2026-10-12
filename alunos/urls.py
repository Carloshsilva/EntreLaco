from django.urls import path

from core.views import em_construcao

app_name = "alunos"

urlpatterns = [
    path("", em_construcao, name="lista"),
    path("novo/", em_construcao, name="novo"),
    path("fila/", em_construcao, name="fila"),
]

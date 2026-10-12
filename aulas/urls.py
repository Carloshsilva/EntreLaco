from django.urls import path

from core.views import em_construcao

app_name = "aulas"

urlpatterns = [
    path("", em_construcao, name="lista"),
    path("marcar/", em_construcao, name="marcar"),
    path("registrar/", em_construcao, name="registrar"),
]

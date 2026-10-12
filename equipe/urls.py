from django.urls import path

from core.views import em_construcao

app_name = "equipe"

urlpatterns = [
    path("pessoas/", em_construcao, name="pessoas"),
    path("configuracao/", em_construcao, name="configuracao"),
]

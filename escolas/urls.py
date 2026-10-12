from django.urls import path

from core.views import em_construcao

app_name = "escolas"

urlpatterns = [
    path("", em_construcao, name="lista"),
]

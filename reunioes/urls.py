from django.urls import path

from core.views import em_construcao

app_name = "reunioes"

urlpatterns = [
    path("", em_construcao, name="lista"),
    path("nova/", em_construcao, name="nova"),
]

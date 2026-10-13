from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("entrar/", views.entrar, name="entrar"),
    path("entrar/codigo/", views.entrar_codigo, name="entrar_codigo"),
    path("sair/", views.sair, name="sair"),
    path("conta/", views.minha_conta, name="minha_conta"),
    path("conta/senha/", views.trocar_senha, name="trocar_senha"),
    path("conta/duas-etapas/", views.duas_etapas, name="duas_etapas"),
    path("senha/esqueci/", views.RedefinirSenhaView.as_view(), name="senha_esqueci"),
    path(
        "senha/esqueci/enviado/",
        auth_views.PasswordResetDoneView.as_view(template_name="core/senha/enviado.html"),
        name="senha_pedido_enviado",
    ),
    path("senha/definir/<uidb64>/<token>/", views.DefinirSenhaView.as_view(), name="senha_definir"),
    path(
        "senha/definida/",
        auth_views.PasswordResetCompleteView.as_view(template_name="core/senha/definida.html"),
        name="senha_definida",
    ),
    path("servico/trocar/", views.trocar_servico, name="trocar_servico"),
    path("agenda/", views.agenda, name="agenda"),
    path("trilha/", views.trilha, name="trilha"),
]

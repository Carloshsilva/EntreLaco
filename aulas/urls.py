from django.urls import path

from . import views

app_name = "aulas"

urlpatterns = [
    path("", views.ListaDeAulasView.as_view(), name="lista"),
    path("marcar/", views.MarcarAulaView.as_view(), name="marcar"),
    path("registrar/", views.RegistrarAulaView.as_view(), name="registrar"),
    path("<int:pk>/", views.DetalheDaAulaView.as_view(), name="detalhe"),
    path("<int:pk>/registrar/", views.RegistrarMarcadaView.as_view(), name="registrar_marcada"),
    path("<int:pk>/editar/", views.EditarAulaView.as_view(), name="editar"),
    path("<int:pk>/nao-aconteceu/", views.NaoRealizadaView.as_view(), name="nao_realizada"),
    path("fotos/<int:pk>/", views.foto, name="foto"),
    path("<int:pk>/fotos/nova/", views.FotoNovaView.as_view(), name="foto_nova"),
    # Lista da BNCC do serviço (RF-16), para quem configura.
    path("bncc/", views.HabilidadesView.as_view(), name="habilidades"),
    path("bncc/nova/", views.HabilidadeNovaView.as_view(), name="habilidade_nova"),
    path("bncc/<int:pk>/editar/", views.HabilidadeEditarView.as_view(), name="habilidade_editar"),
]

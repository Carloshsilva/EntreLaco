from django.contrib import admin
from django.urls import include, path

from core import views as core_views

admin.site.site_header = "EntreLaço: painel da plataforma"
admin.site.site_title = "EntreLaço"
admin.site.index_title = "Serviços, pessoas e papéis"

urlpatterns = [
    path("plataforma/login/", core_views.redirecionar_login_do_admin),
    path("plataforma/", admin.site.urls),
    path("equipe/", include("equipe.urls")),
    path("escolas/", include("escolas.urls")),
    path("alunos/", include("alunos.urls")),
    path("autorizacoes/", include("autorizacoes.urls")),
    path("aulas/", include("aulas.urls")),
    path("reunioes/", include("reunioes.urls")),
    path("documentos/", include("documentos.urls")),
    path("", include("core.urls")),
]

handler403 = "core.views.erro_403"
handler404 = "core.views.erro_404"
handler500 = "core.views.erro_500"

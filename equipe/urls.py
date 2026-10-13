from django.urls import path

from . import views, views_configuracao

app_name = "equipe"

urlpatterns = [
    # Pessoas da equipe (o pk é o do Usuario).
    path("", views.PessoasView.as_view(), name="pessoas"),
    path("nova/", views.PessoaNovaView.as_view(), name="pessoa_nova"),
    path("<int:pk>/", views.PessoaDetalheView.as_view(), name="pessoa_detalhe"),
    path("<int:pk>/editar/", views.PessoaEditarView.as_view(), name="pessoa_editar"),
    path("<int:pk>/desativar/", views.PessoaDesativarView.as_view(), name="pessoa_desativar"),
    path("<int:pk>/reativar/", views.PessoaReativarView.as_view(), name="pessoa_reativar"),
    path("<int:pk>/link-senha/", views.PessoaLinkSenhaView.as_view(), name="pessoa_link_senha"),
    path("<int:pk>/professor/", views.professor, name="professor"),
    # Quem configura o serviço.
    path("papeis/", views_configuracao.PapeisView.as_view(), name="papeis"),
    path("papeis/novo/", views_configuracao.PapelNovoView.as_view(), name="papel_novo"),
    path("papeis/<int:pk>/editar/", views_configuracao.PapelEditarView.as_view(), name="papel_editar"),
    path("configuracao/", views_configuracao.ConfiguracaoView.as_view(), name="configuracao"),
    path("componentes/", views_configuracao.ComponentesView.as_view(), name="componentes"),
    path("componentes/novo/", views_configuracao.ComponenteNovoView.as_view(), name="componente_novo"),
    path("componentes/<int:pk>/editar/", views_configuracao.ComponenteEditarView.as_view(), name="componente_editar"),
]

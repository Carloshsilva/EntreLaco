from django.apps import AppConfig


class AutorizacoesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "autorizacoes"
    verbose_name = "Autorizações"

    def ready(self):
        from . import encaixes  # noqa: F401 - registra menu, seções do aluno, pendências e agenda

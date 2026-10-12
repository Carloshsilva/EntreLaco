from django.apps import AppConfig


class EscolasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "escolas"
    verbose_name = "Escolas"

    def ready(self):
        from . import encaixes  # noqa: F401 - registra menu, seções do aluno, pendências e agenda

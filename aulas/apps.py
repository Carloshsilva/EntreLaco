from django.apps import AppConfig


class AulasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "aulas"
    verbose_name = "Aulas"

    def ready(self):
        from . import encaixes  # noqa: F401 - registra menu, seções do aluno, pendências e agenda

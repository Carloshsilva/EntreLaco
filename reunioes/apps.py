from django.apps import AppConfig


class ReunioesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reunioes"
    verbose_name = "Reuniões"

    def ready(self):
        from . import encaixes  # noqa: F401 - registra menu, seções do aluno, pendências e agenda

from django.apps import AppConfig


class EquipeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "equipe"
    verbose_name = "Equipe"

    def ready(self):
        from . import encaixes  # noqa: F401 - registra menu, seções do aluno, pendências e agenda

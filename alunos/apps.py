from django.apps import AppConfig


class AlunosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "alunos"
    verbose_name = "Alunos"

    def ready(self):
        from . import encaixes  # noqa: F401 - registra menu, seções do aluno, pendências e agenda

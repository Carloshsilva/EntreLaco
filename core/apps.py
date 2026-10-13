from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Núcleo"

    def ready(self):
        from django.core import checks

        from . import encaixes  # noqa: F401 - registra menu e pontos de encaixe
        from .registro import conferir_secoes_do_aluno

        checks.register(conferir_secoes_do_aluno, checks.Tags.templates)

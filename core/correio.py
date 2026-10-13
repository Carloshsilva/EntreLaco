"""Envio de e-mail da plataforma."""
from django.conf import settings


def email_ligado():
    """Diz se o e-mail sai de verdade.

    Sem configuração no .env, o Django fica no modo console: a mensagem só vai para os
    registros do servidor (docker compose logs web) e não chega a ninguém. Nesse caso as
    telas não dizem que mandaram nada.
    """
    return not settings.EMAIL_BACKEND.endswith(".console.EmailBackend")

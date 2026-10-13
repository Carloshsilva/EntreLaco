"""O que este módulo acrescenta às telas comuns (veja core/registro.py).

- Seção "Documentos" no perfil do aluno (RF-12): fotos e scans, com quem digitalizou e quando.
  Os documentos não têm item próprio no menu: ficam no histórico de cada aluno.
"""
from django.urls import reverse

from core.registro import SecaoDoAluno, registrar_secao_do_aluno

GRUPO = "documentos"


def secao_documentos_do_aluno(request, aluno):
    """Os documentos do aluno, do envio mais recente para o mais antigo."""
    from .models import Documento

    servico = getattr(request, "servico", None)
    if servico is None or not request.acesso.pode_ver(GRUPO):
        return None
    documentos = list(
        Documento.objects.filter(servico=servico, aluno=aluno).select_related("criado_por")
        .only("id", "tipo", "titulo", "data_documento", "criado_em", "criado_por__nome", "criado_por__email")
        .order_by("-criado_em", "-pk")
    )
    pode_enviar = request.acesso.pode_editar(GRUPO)
    return {
        "documentos": documentos,
        "pode_enviar": pode_enviar,
        "url_enviar": reverse("documentos:novo", args=[aluno.pk]) if pode_enviar else "",
    }


registrar_secao_do_aluno(SecaoDoAluno(
    chave="documentos", titulo="Documentos", template="documentos/_secao_aluno.html",
    contexto=secao_documentos_do_aluno, grupo=GRUPO, ordem=60,
))

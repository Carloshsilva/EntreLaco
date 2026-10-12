"""Arquivos enviados: fotos de aula, documentos digitalizados e assinaturas.

- Ficam em MEDIA_ROOT, fora da pasta pública, com nome aleatório e separados
  por serviço; só saem por views que conferem login, serviço e permissão.
- Fotos perdem os metadados (EXIF, que pode trazer local e aparelho) ao serem salvas.
- Tamanho e tipo são conferidos pelo conteúdo, não pela extensão.
"""
import hashlib
import io
import mimetypes
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.http import FileResponse, Http404

TIPOS_DE_IMAGEM = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp")}
PDF = ("application/pdf", "pdf")


def _caminho(instancia, nome_original, pasta):
    """servico_<id>/<pasta>/<aaaa>/<mm>/<uuid>.<ext>: nome aleatório, separado por serviço."""
    from django.utils import timezone

    extensao = nome_original.rsplit(".", 1)[-1].lower() if "." in nome_original else "bin"
    extensao = "".join(c for c in extensao if c.isalnum())[:5] or "bin"
    agora = timezone.now()
    servico_id = getattr(instancia, "servico_id", None) or "plataforma"
    return f"servico_{servico_id}/{pasta}/{agora:%Y}/{agora:%m}/{uuid.uuid4().hex}.{extensao}"


# Funções nomeadas no nível do módulo, para as migrações conseguirem referenciá-las em `upload_to`.
def caminho_foto_de_aula(instancia, nome_original):
    return _caminho(instancia, nome_original, "aulas")


def caminho_documento(instancia, nome_original):
    return _caminho(instancia, nome_original, "documentos")


def caminho_autorizacao(instancia, nome_original):
    return _caminho(instancia, nome_original, "autorizacoes")


def _tamanho_maximo():
    return getattr(settings, "ENTRELACO_TAMANHO_MAXIMO_ARQUIVO", 10 * 1024 * 1024)


def validar_tamanho(arquivo):
    if arquivo and arquivo.size > _tamanho_maximo():
        limite = _tamanho_maximo() // (1024 * 1024)
        raise ValidationError(f"O arquivo passa de {limite} MB. Envie uma foto menor ou um PDF mais leve.")


def _abrir_imagem(arquivo):
    from PIL import Image, UnidentifiedImageError

    try:
        arquivo.seek(0)
        imagem = Image.open(arquivo)
        imagem.load()
    except (UnidentifiedImageError, OSError, ValueError):
        return None
    return imagem


def _e_pdf(arquivo):
    arquivo.seek(0)
    inicio = arquivo.read(5)
    arquivo.seek(0)
    return inicio == b"%PDF-"


def limpar_imagem(arquivo, nome_base="foto"):
    """Regrava a imagem sem metadados, girada conforme o EXIF e com no máximo 2400px."""
    from PIL import ImageOps

    imagem = _abrir_imagem(arquivo)
    if imagem is None:
        raise ValidationError("Este arquivo não é uma foto que a plataforma consegue abrir. Use JPG, PNG ou WEBP.")
    formato = imagem.format if imagem.format in TIPOS_DE_IMAGEM else "JPEG"
    imagem = ImageOps.exif_transpose(imagem)
    imagem.thumbnail((2400, 2400))
    if formato == "JPEG" and imagem.mode not in ("RGB", "L"):
        imagem = imagem.convert("RGB")
    saida = io.BytesIO()
    opcoes = {"quality": 85, "optimize": True} if formato == "JPEG" else {}
    imagem.save(saida, format=formato, **opcoes)  # salvar de novo descarta o EXIF
    tipo, extensao = TIPOS_DE_IMAGEM[formato]
    saida.seek(0)
    return InMemoryUploadedFile(saida, None, f"{nome_base}.{extensao}", tipo, saida.getbuffer().nbytes, None)


def validar_foto(arquivo):
    """Para campos de foto: confere tamanho e tipo e devolve a foto limpa."""
    validar_tamanho(arquivo)
    return limpar_imagem(arquivo)


def validar_documento(arquivo):
    """Para documentos: aceita foto (limpa) ou PDF."""
    validar_tamanho(arquivo)
    if _e_pdf(arquivo):
        arquivo.seek(0)
        return arquivo
    if _abrir_imagem(arquivo) is not None:
        return limpar_imagem(arquivo, nome_base="documento")
    raise ValidationError("Envie uma foto (JPG, PNG ou WEBP) ou um PDF.")


def resumo_sha256(arquivo):
    """Impressão digital do conteúdo, para provar que o arquivo não mudou depois (LGPD-03)."""
    digest = hashlib.sha256()
    arquivo.seek(0)
    for pedaco in iter(lambda: arquivo.read(64 * 1024), b""):
        digest.update(pedaco)
    arquivo.seek(0)
    return digest.hexdigest()


def servir_arquivo(campo_arquivo, nome_para_download, *, inline=True):
    """Entrega um arquivo privado. Quem chama já conferiu login, serviço e permissão."""
    if not campo_arquivo or not campo_arquivo.name:
        raise Http404("Arquivo não encontrado.")
    try:
        aberto = campo_arquivo.open("rb")
    except FileNotFoundError as erro:
        raise Http404("Arquivo não encontrado.") from erro
    tipo, _ = mimetypes.guess_type(campo_arquivo.name)
    # Só imagens abrem na própria aba; PDF e o resto descem como arquivo.
    inline = inline and bool(tipo) and tipo.startswith("image/")
    resposta = FileResponse(
        aberto, as_attachment=not inline, filename=nome_para_download, content_type=tipo or "application/octet-stream"
    )
    resposta["Cache-Control"] = "private, no-store"
    resposta["X-Content-Type-Options"] = "nosniff"
    resposta["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    return resposta

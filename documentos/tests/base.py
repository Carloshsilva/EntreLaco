"""Dados e arquivos inventados comuns aos testes do módulo documentos."""
import io
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings

from core.models import EventoAuditoria
from core.permissoes import Acesso
from core.testes import (
    criar_aluno,
    criar_apoio,
    criar_papel,
    criar_pessoa,
    criar_professor,
    criar_servico,
    criar_supervisao,
)
from documentos.models import Documento

Acao = EventoAuditoria.Acao

# Um PDF mínimo, inventado.
PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"
# Marca que vai nos metadados EXIF da foto de teste e não pode sobrar no arquivo guardado.
MARCA_EXIF = "Aparelho Inventado 3000"


def foto_com_exif(formato="JPEG"):
    """Foto pequena com fabricante e modelo do aparelho no EXIF, como sai de um celular."""
    from PIL import Image

    imagem = Image.new("RGB", (64, 48), (200, 120, 40))
    exif = Image.Exif()
    exif[0x010F] = MARCA_EXIF  # Make
    exif[0x0110] = MARCA_EXIF  # Model
    saida = io.BytesIO()
    imagem.save(saida, format=formato, exif=exif.tobytes())
    return saida.getvalue()


def enviado(nome, conteudo, tipo):
    return SimpleUploadedFile(nome, conteudo, content_type=tipo)


def requisicao(usuario, caminho="/"):
    """Requisição com serviço e acesso, como o ServicoMiddleware deixaria."""
    request = RequestFactory().get(caminho)
    request.user = usuario
    vinculo = usuario.vinculos.select_related("servico", "papel").get()
    request.servico = vinculo.servico
    request.vinculo = vinculo
    request.acesso = Acesso.do_papel(vinculo.papel)
    return request


class BaseDocumentos(TestCase):
    """Um serviço com apoio (envia documentos), professor e supervisão, quem só vê documentos e quem não
    vê; um segundo serviço com uma pessoa e um aluno de fora. Os arquivos vão para uma pasta temporária."""

    @classmethod
    def setUpClass(cls):
        cls._pasta = tempfile.mkdtemp(prefix="entrelaco-documentos-")
        cls._pasta_privada = override_settings(MEDIA_ROOT=cls._pasta)
        cls._pasta_privada.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._pasta_privada.disable()
        shutil.rmtree(cls._pasta, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.servico = criar_servico("Escola Móvel Inventada")
        cls.outro_servico = criar_servico("Classe Hospitalar Fictícia")
        cls.apoio = criar_apoio(cls.servico, nome="Abel Apoio Inventado", email="abel@exemplo.org")
        cls.professor = criar_professor(cls.servico, nome="Paula Professora Inventada", email="paula@exemplo.org")
        cls.supervisao = criar_supervisao(cls.servico, nome="Sara Supervisora Inventada", email="sara@exemplo.org")
        cls.so_ve = criar_pessoa(
            cls.servico, criar_papel(cls.servico, "Só vê documentos", ver=["identificacao", "documentos"]),
            nome="Vera Leitora Inventada", email="vera@exemplo.org",
        )
        cls.so_aulas = criar_pessoa(
            cls.servico, criar_papel(cls.servico, "Só aulas", editar=["aulas"], ver=["identificacao"]),
            nome="Otto Aulas Inventado", email="otto@exemplo.org",
        )
        cls.de_fora = criar_supervisao(cls.outro_servico, nome="Flora De Fora Inventada", email="flora@exemplo.org")
        cls.aluno = criar_aluno(cls.servico, nome="Lia Inventada Moreira")
        cls.aluno_dois = criar_aluno(cls.servico, nome="Caio Fictício Prado")
        cls.aluno_de_fora = criar_aluno(cls.outro_servico, nome="Nina De Fora Souza")

    def documento(self, aluno=None, conteudo=PDF, nome="ficha.pdf", **extra):
        aluno = aluno or self.aluno
        extra.setdefault("titulo", "Ficha de papel assinada")
        extra.setdefault("criado_por", self.apoio)
        documento = Documento(servico=aluno.servico, aluno=aluno, tamanho=len(conteudo), **extra)
        documento.arquivo.save(nome, ContentFile(conteudo), save=False)
        documento.save()
        return documento

    def entrar(self, pessoa):
        self.client.force_login(pessoa)

    def assertUmH1(self, resposta):
        self.assertContains(resposta, "<h1", count=1)

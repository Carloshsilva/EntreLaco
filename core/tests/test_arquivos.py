"""Arquivos enviados: o tipo vem do conteúdo e a entrega usa uma lista fechada de tipos (dados inventados)."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from core.arquivos import tipo_do_arquivo, validar_documento


class TipoDoArquivoTestes(SimpleTestCase):
    def test_pdf_enviado_com_outra_extensao_fica_guardado_como_pdf(self):
        for nome in ("ficha.svg", "ficha.html", "ficha"):
            arquivo = SimpleUploadedFile(nome, b"%PDF-1.4\n% documento inventado\n", content_type="image/svg+xml")
            self.assertEqual(validar_documento(arquivo).name, "documento.pdf")

    def test_so_tipos_conhecidos_saem_com_o_proprio_tipo(self):
        self.assertEqual(tipo_do_arquivo("a/b/c.jpg"), "image/jpeg")
        self.assertEqual(tipo_do_arquivo("a/b/c.PDF"), "application/pdf")
        for nome in ("c.svg", "c.html", "c.js", "c", ""):
            self.assertEqual(tipo_do_arquivo(nome), "application/octet-stream")

"""Documentos digitalizados: enviar, ver, editar, abrir o arquivo e a seção do perfil (RF-12, SEG-04, SEG-05)."""
import datetime
import hashlib

from django.db import connection
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from core.models import EventoAuditoria
from core.registro import secoes_do_aluno
from documentos.encaixes import secao_documentos_do_aluno
from documentos.models import Documento

from .base import MARCA_EXIF, PDF, Acao, BaseDocumentos, enviado, foto_com_exif, requisicao


class EnviarTestes(BaseDocumentos):
    def url(self, aluno=None):
        return reverse("documentos:novo", args=[(aluno or self.aluno).pk])

    def dados(self, arquivo=None, **extra):
        dados = {
            "tipo": "ficha_papel", "titulo": "Ficha de papel assinada", "data_documento": "2026-10-01",
            "observacoes": "Original na pasta inventada.",
            "arquivo": arquivo or enviado("ficha.pdf", PDF, "application/pdf"),
        }
        dados.update(extra)
        return dados

    def test_abre_para_quem_edita_documentos(self):
        for pessoa in (self.apoio, self.professor, self.supervisao):
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                resposta = self.client.get(self.url())
                self.assertEqual(resposta.status_code, 200)
                self.assertUmH1(resposta)
                self.assertContains(resposta, 'accept="image/*,application/pdf"')
                self.assertNotContains(resposta, "capture")
                self.assertContains(resposta, 'enctype="multipart/form-data"')
                self.assertContains(resposta, "Para o histórico de Lia M.")

    def test_403_para_quem_so_ve_ou_nao_ve(self):
        for pessoa in (self.so_ve, self.so_aulas):
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                self.assertEqual(self.client.get(self.url()).status_code, 403)
                self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 403)
        self.assertFalse(Documento.objects.exists())

    def test_aluno_de_outro_servico_da_404(self):
        self.entrar(self.apoio)
        self.assertEqual(self.client.get(self.url(self.aluno_de_fora)).status_code, 404)
        self.assertEqual(self.client.post(self.url(self.aluno_de_fora), self.dados()).status_code, 404)
        self.assertFalse(Documento.objects.exists())

    def test_pdf_e_aceito_com_tamanho_impressao_digital_e_trilha(self):
        self.entrar(self.apoio)
        resposta = self.client.post(self.url(), self.dados())
        documento = Documento.objects.get()
        self.assertRedirects(resposta, reverse("documentos:detalhe", args=[documento.pk]))
        self.assertEqual(documento.servico, self.servico)
        self.assertEqual(documento.aluno, self.aluno)
        self.assertEqual(documento.criado_por, self.apoio)
        self.assertEqual(documento.tamanho, len(PDF))
        self.assertEqual(documento.impressao_digital, hashlib.sha256(PDF).hexdigest())
        self.assertTrue(documento.arquivo.name.startswith(f"servico_{self.servico.pk}/documentos/"))
        with documento.arquivo.open("rb") as guardado:
            self.assertEqual(guardado.read(), PDF)
        evento = EventoAuditoria.objects.get(modelo="documentos.Documento", objeto_id=str(documento.pk))
        self.assertEqual(evento.acao, Acao.CRIOU)
        self.assertEqual(evento.usuario, self.apoio)
        self.assertEqual(evento.aluno_id, self.aluno.pk)

    def test_foto_e_aceita_sem_os_metadados_exif(self):
        original = foto_com_exif()
        self.assertIn(MARCA_EXIF.encode(), original)
        self.entrar(self.professor)
        self.client.post(self.url(), self.dados(arquivo=enviado("IMG_0001.jpg", original, "image/jpeg"),
                                                tipo="atividade", titulo="Desenho inventado"))
        documento = Documento.objects.get()
        with documento.arquivo.open("rb") as guardado:
            conteudo = guardado.read()
        self.assertNotIn(MARCA_EXIF.encode(), conteudo)
        guardado_aberto = Image.open(documento.arquivo.path)
        self.assertEqual(dict(guardado_aberto.getexif()), {})
        self.assertEqual(documento.tamanho, len(conteudo))
        self.assertEqual(documento.impressao_digital, hashlib.sha256(conteudo).hexdigest())
        self.assertTrue(documento.arquivo.name.endswith(".jpg"))

    def test_png_tambem_e_aceito(self):
        self.entrar(self.apoio)
        self.client.post(self.url(), self.dados(arquivo=enviado("scan.png", foto_com_exif("PNG"), "image/png")))
        self.assertTrue(Documento.objects.get().arquivo.name.endswith(".png"))

    def test_outro_tipo_de_arquivo_e_recusado(self):
        self.entrar(self.apoio)
        falso = enviado("ficha.pdf", b"isto nao e um pdf nem uma foto", "application/pdf")
        resposta = self.client.post(self.url(), self.dados(arquivo=falso))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Envie uma foto (JPG, PNG ou WEBP) ou um PDF.")
        self.assertContains(resposta, 'aria-invalid="true"')
        self.assertFalse(Documento.objects.exists())

    def test_sem_arquivo_explica_o_que_fazer(self):
        self.entrar(self.apoio)
        dados = self.dados()
        del dados["arquivo"]
        resposta = self.client.post(self.url(), dados)
        self.assertContains(resposta, "Escolha a foto ou o PDF do documento.")
        self.assertFalse(Documento.objects.exists())

    def test_titulo_em_branco_usa_o_tipo_e_a_data(self):
        self.entrar(self.apoio)
        self.client.post(self.url(), self.dados(titulo="", data_documento="2026-10-10"))
        self.assertEqual(Documento.objects.get().titulo, "Ficha de papel assinada de 10/10/2026")

    def test_data_depois_de_hoje_e_recusada(self):
        self.entrar(self.apoio)
        amanha = timezone.localdate() + datetime.timedelta(days=1)
        resposta = self.client.post(self.url(), self.dados(data_documento=amanha.isoformat()))
        self.assertContains(resposta, "A data do documento está depois de hoje.")
        self.assertFalse(Documento.objects.exists())


class DetalheTestes(BaseDocumentos):
    def url(self, documento):
        return reverse("documentos:detalhe", args=[documento.pk])

    def test_abre_para_quem_ve_documentos(self):
        documento = self.documento(data_documento=datetime.date(2026, 10, 1), impressao_digital="a" * 64)
        self.entrar(self.so_ve)
        resposta = self.client.get(self.url(documento))
        self.assertEqual(resposta.status_code, 200)
        self.assertUmH1(resposta)
        self.assertContains(resposta, "Ficha de papel assinada")
        self.assertContains(resposta, "Abel Apoio Inventado")
        self.assertContains(resposta, "01/10/2026")
        self.assertContains(resposta, "a" * 64)
        self.assertContains(resposta, "bytes")
        self.assertContains(resposta, "não podem ser excluídos")
        self.assertContains(resposta, f'href="{reverse("documentos:arquivo", args=[documento.pk])}" hx-boost="false"')
        self.assertContains(resposta, "Baixar o PDF")
        self.assertNotContains(resposta, "<img")
        self.assertNotContains(resposta, reverse("documentos:editar", args=[documento.pk]))

    def test_editar_so_para_quem_edita_documentos(self):
        documento = self.documento()
        self.entrar(self.apoio)
        self.assertContains(self.client.get(self.url(documento)), reverse("documentos:editar", args=[documento.pk]))

    def test_foto_mostra_a_previa_pela_view_protegida(self):
        documento = self.documento(conteudo=foto_com_exif(), nome="foto.jpg")
        self.entrar(self.so_ve)
        resposta = self.client.get(self.url(documento))
        self.assertContains(resposta, f'src="{reverse("documentos:arquivo", args=[documento.pk])}?previa=1"')
        self.assertContains(resposta, "Abrir a foto")
        self.assertNotContains(resposta, "/arquivos-protegidos/")

    def test_403_para_quem_nao_ve_documentos(self):
        documento = self.documento()
        self.entrar(self.so_aulas)
        self.assertEqual(self.client.get(self.url(documento)).status_code, 403)

    def test_documento_de_outro_servico_da_404(self):
        documento = self.documento(aluno=self.aluno_de_fora, criado_por=self.de_fora)
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(self.url(documento)).status_code, 404)

    def test_historico_mostra_quem_enviou(self):
        self.entrar(self.apoio)
        self.client.post(reverse("documentos:novo", args=[self.aluno.pk]), {
            "tipo": "termo", "titulo": "Termo inventado", "arquivo": enviado("t.pdf", PDF, "application/pdf"),
        })
        resposta = self.client.get(self.url(Documento.objects.get()))
        self.assertContains(resposta, "<strong>Abel Apoio Inventado</strong> criou documento", html=True)


class EditarTestes(BaseDocumentos):
    def setUp(self):
        self.doc = self.documento()

    def url(self, documento=None):
        return reverse("documentos:editar", args=[(documento or self.doc).pk])

    def dados(self, **extra):
        dados = {
            "tipo": "ficha_papel", "titulo": "Ficha de papel assinada pela família", "data_documento": "2026-10-02",
            "observacoes": "", "motivo_alteracao": "O título estava incompleto.",
        }
        dados.update(extra)
        return dados

    def test_abre_sem_o_campo_do_arquivo(self):
        self.entrar(self.apoio)
        resposta = self.client.get(self.url())
        self.assertEqual(resposta.status_code, 200)
        self.assertUmH1(resposta)
        self.assertNotContains(resposta, 'name="arquivo"')
        self.assertContains(resposta, "Por que você está alterando?")

    def test_403_para_quem_so_ve(self):
        self.entrar(self.so_ve)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 403)

    def test_documento_de_outro_servico_da_404(self):
        de_fora = self.documento(aluno=self.aluno_de_fora, criado_por=self.de_fora)
        self.entrar(self.apoio)
        self.assertEqual(self.client.get(self.url(de_fora)).status_code, 404)

    def test_salvar_grava_o_motivo_e_nao_mexe_no_arquivo(self):
        arquivo_antes = self.doc.arquivo.name
        self.entrar(self.apoio)
        resposta = self.client.post(self.url(), self.dados())
        self.assertRedirects(resposta, reverse("documentos:detalhe", args=[self.doc.pk]))
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.titulo, "Ficha de papel assinada pela família")
        self.assertEqual(self.doc.arquivo.name, arquivo_antes)
        evento = EventoAuditoria.objects.get(modelo="documentos.Documento", acao=Acao.ALTEROU)
        self.assertEqual(evento.motivo, "O título estava incompleto.")
        self.assertEqual(evento.mudancas["titulo"]["para"], "Ficha de papel assinada pela família")

    def test_sem_motivo_nao_salva(self):
        self.entrar(self.apoio)
        resposta = self.client.post(self.url(), self.dados(motivo_alteracao=""))
        self.assertContains(resposta, "Conte por que você está alterando")
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.titulo, "Ficha de papel assinada")


class ArquivoTestes(BaseDocumentos):
    def url(self, documento):
        return reverse("documentos:arquivo", args=[documento.pk])

    def test_pede_login(self):
        documento = self.documento()
        resposta = self.client.get(self.url(documento))
        self.assertEqual(resposta.status_code, 302)
        self.assertFalse(EventoAuditoria.objects.filter(acao=Acao.BAIXOU_ARQUIVO).exists())

    def test_abrir_o_pdf_entrega_o_arquivo_e_grava_na_trilha(self):
        documento = self.documento(titulo="Ficha de papel assinada")
        self.entrar(self.so_ve)
        resposta = self.client.get(self.url(documento))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(b"".join(resposta.streaming_content), PDF)
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        self.assertIn('attachment; filename="ficha-de-papel-assinada.pdf"', resposta["Content-Disposition"])
        self.assertIn("no-store", resposta["Cache-Control"])
        evento = EventoAuditoria.objects.get(acao=Acao.BAIXOU_ARQUIVO)
        self.assertEqual(evento.usuario, self.so_ve)
        self.assertEqual(evento.objeto_id, str(documento.pk))
        self.assertEqual(evento.aluno_id, self.aluno.pk)
        self.assertEqual(evento.descricao, "Abriu o arquivo")

    def test_previa_da_foto_abre_na_tela_e_tambem_fica_na_trilha(self):
        documento = self.documento(conteudo=foto_com_exif(), nome="foto.jpg")
        self.entrar(self.apoio)
        resposta = self.client.get(self.url(documento), {"previa": "1"})
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta["Content-Type"].startswith("image/"))
        self.assertTrue(resposta["Content-Disposition"].startswith("inline"))
        self.assertEqual(EventoAuditoria.objects.get(acao=Acao.BAIXOU_ARQUIVO).descricao,
                         "Viu a prévia na tela do documento")

    def test_previa_fica_na_trilha_uma_vez_por_sessao_e_abrir_sempre(self):
        documento = self.documento(conteudo=foto_com_exif(), nome="foto.jpg")
        self.entrar(self.apoio)
        for _ in range(3):
            self.client.get(self.url(documento), {"previa": "1"})
        self.client.get(self.url(documento))
        self.client.get(self.url(documento))
        descricoes = sorted(EventoAuditoria.objects.filter(acao=Acao.BAIXOU_ARQUIVO).values_list("descricao", flat=True))
        self.assertEqual(descricoes, ["Abriu o arquivo", "Abriu o arquivo", "Viu a prévia na tela do documento"])
        self.entrar(self.so_ve)
        self.client.get(self.url(documento), {"previa": "1"})
        self.assertEqual(EventoAuditoria.objects.filter(acao=Acao.BAIXOU_ARQUIVO, usuario=self.so_ve).count(), 1)

    def test_403_para_quem_nao_ve_documentos(self):
        documento = self.documento()
        self.entrar(self.so_aulas)
        self.assertEqual(self.client.get(self.url(documento)).status_code, 403)
        self.assertFalse(EventoAuditoria.objects.filter(acao=Acao.BAIXOU_ARQUIVO).exists())

    def test_arquivo_de_outro_servico_da_404(self):
        documento = self.documento(aluno=self.aluno_de_fora, criado_por=self.de_fora)
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(self.url(documento)).status_code, 404)
        self.assertFalse(EventoAuditoria.objects.filter(acao=Acao.BAIXOU_ARQUIVO).exists())

    def test_so_aceita_leitura(self):
        documento = self.documento()
        self.entrar(self.apoio)
        self.assertEqual(self.client.post(self.url(documento)).status_code, 405)


class SecaoDoPerfilTestes(BaseDocumentos):
    def secao(self, pessoa, aluno=None):
        aluno = aluno or self.aluno
        request = requisicao(pessoa, f"/alunos/{aluno.pk}/")
        dados = secao_documentos_do_aluno(request, aluno)
        html = render_to_string(
            "documentos/_secao_aluno.html", {"dados": dados, "aluno": aluno, "acesso": request.acesso}, request=request,
        )
        return dados, html

    def test_secao_registrada_para_quem_ve_documentos(self):
        self.assertIn("documentos", [s["chave"] for s in secoes_do_aluno(requisicao(self.so_ve), self.aluno)])
        self.assertNotIn("documentos", [s["chave"] for s in secoes_do_aluno(requisicao(self.so_aulas), self.aluno)])

    def test_lista_os_documentos_do_aluno_com_quem_digitalizou(self):
        documento = self.documento(data_documento=datetime.date(2026, 10, 1))
        self.documento(aluno=self.aluno_dois, titulo="Documento de outro aluno")
        dados, html = self.secao(self.so_ve)
        self.assertEqual(dados["documentos"], [documento])
        self.assertIn(reverse("documentos:detalhe", args=[documento.pk]), html)
        self.assertIn("Ficha de papel assinada", html)
        self.assertIn("01/10/2026", html)
        self.assertIn("Abel I.", html)
        self.assertIn('data-label="Digitalizado por"', html)
        self.assertNotIn("Documento de outro aluno", html)

    def test_botao_enviar_so_para_quem_edita(self):
        _, html = self.secao(self.apoio)
        self.assertIn(reverse("documentos:novo", args=[self.aluno.pk]), html)
        self.assertIn("Enviar documento", html)
        _, html = self.secao(self.so_ve)
        self.assertNotIn("Enviar documento", html)

    def test_consultas_da_secao_nao_crescem_com_o_numero_de_documentos(self):
        self.documento()
        with CaptureQueriesContext(connection) as poucas:
            self.secao(self.apoio)
        for numero in range(8):
            self.documento(titulo=f"Atividade inventada {numero}", criado_por=self.professor if numero % 2 else self.apoio)
        with CaptureQueriesContext(connection) as muitas:
            self.secao(self.apoio)
        self.assertEqual(len(poucas), len(muitas))

    def test_sem_documentos(self):
        _, html = self.secao(self.apoio)
        self.assertIn("Nenhum documento digitalizado ainda.", html)

    def test_perfil_do_aluno_mostra_a_secao(self):
        documento = self.documento()
        url = reverse("alunos:detalhe", args=[self.aluno.pk])
        self.entrar(self.apoio)
        resposta = self.client.get(url)
        self.assertContains(resposta, 'id="secao-documentos"')
        self.assertContains(resposta, reverse("documentos:detalhe", args=[documento.pk]))
        self.assertContains(resposta, reverse("documentos:novo", args=[self.aluno.pk]))
        self.entrar(self.so_aulas)
        self.assertNotContains(self.client.get(url), 'id="secao-documentos"')

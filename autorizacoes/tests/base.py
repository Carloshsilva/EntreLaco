"""Dados inventados comuns aos testes do módulo autorizacoes. Nada de dado real."""
import base64
import datetime
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno, Responsavel
from autorizacoes.models import Autorizacao, Termo, Tipo
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

Acao = EventoAuditoria.Acao
Situacao = Autorizacao.Situacao
Forma = Autorizacao.Forma

TEXTO_DO_TERMO_DE_USO = (
    "Texto provisório inventado para teste: autorizo o uso dos dados da criança pelo serviço. "
    "O texto definitivo será escrito pelo advogado."
)
TEXTO_DO_TERMO_DE_CONTATO = (
    "Texto provisório inventado para teste: autorizo o serviço a falar com a escola da criança."
)


def requisicao(usuario, caminho="/"):
    """Requisição com serviço e acesso, como o ServicoMiddleware deixaria."""
    request = RequestFactory().get(caminho)
    request.user = usuario
    vinculo = usuario.vinculos.select_related("servico", "papel").get()
    request.servico = vinculo.servico
    request.vinculo = vinculo
    request.acesso = Acesso.do_papel(vinculo.papel)
    return request


def png_de_assinatura(largura=300, altura=100):
    """Um rabisco inventado em PNG, como o quadro de assinatura gravaria."""
    from PIL import Image, ImageDraw

    imagem = Image.new("RGB", (largura, altura), "white")
    desenho = ImageDraw.Draw(imagem)
    desenho.line([(10, altura - 20), (largura // 3, 15), (largura // 2, altura - 15), (largura - 10, 20)], fill="black", width=3)
    saida = io.BytesIO()
    imagem.save(saida, format="PNG")
    return saida.getvalue()


def data_url(png):
    return "data:image/png;base64," + base64.b64encode(png).decode()


def foto_jpg(nome="papel.jpg"):
    from PIL import Image

    imagem = Image.new("RGB", (120, 160), (240, 240, 230))
    saida = io.BytesIO()
    imagem.save(saida, format="JPEG")
    return SimpleUploadedFile(nome, saida.getvalue(), content_type="image/jpeg")


def pdf(nome="papel.pdf"):
    return SimpleUploadedFile(nome, b"%PDF-1.4\n% inventado para teste\n%%EOF\n", content_type="application/pdf")


def conversa_txt(nome="Conversa do WhatsApp com Responsavel Inventada.txt"):
    texto = "13/10/2026 14:02 - Responsável Inventada: Sim, autorizo.\n"
    return SimpleUploadedFile(nome, texto.encode("utf-8"), content_type="text/plain")


class BaseAutorizacoes(TestCase):
    """Um serviço com professor, supervisão (configura), apoio administrativo (só vê as autorizações)
    e um papel sem autorizações; e um segundo serviço com pessoa, aluno e termos de fora."""

    @classmethod
    def setUpClass(cls):
        cls._pasta = tempfile.mkdtemp(prefix="entrelaco-testes-autorizacoes-")
        cls._arquivos = override_settings(MEDIA_ROOT=cls._pasta)
        cls._arquivos.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._arquivos.disable()
        shutil.rmtree(cls._pasta, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.servico = criar_servico("Escola Móvel Inventada")
        cls.outro_servico = criar_servico("Classe Hospitalar Fictícia")

        cls.professor = criar_professor(cls.servico, nome="Paula Professora Inventada", email="paula@exemplo.org")
        cls.professor_b = criar_professor(cls.servico, nome="Bruno Professor Inventado", email="bruno@exemplo.org")
        cls.supervisao = criar_supervisao(cls.servico, nome="Sueli Supervisora Inventada", email="sueli@exemplo.org")
        cls.apoio = criar_apoio(cls.servico, nome="Abel Apoio Inventado", email="abel@exemplo.org")
        cls.so_aulas = criar_pessoa(
            cls.servico, criar_papel(cls.servico, "Só aulas", editar=["aulas"], ver=["identificacao"]),
            nome="Saulo Só Aulas Inventado", email="so.aulas@exemplo.org",
        )
        cls.sem_familia = criar_pessoa(
            cls.servico,
            criar_papel(cls.servico, "Colhe sem ver a família", editar=["autorizacoes"], ver=["identificacao"]),
            nome="Celso Sem Família Inventado", email="sem.familia@exemplo.org",
        )
        cls.de_fora = criar_professor(cls.outro_servico, nome="Flora De Fora Inventada", email="flora@exemplo.org")

        cls.aluno = criar_aluno(
            cls.servico, nome="Lia Inventada Moreira", unidade="Oncologia Fictícia", leito="12B",
            diagnostico="Diagnóstico inventado para teste", criado_por=cls.professor,
        )
        cls.responsavel = Responsavel.objects.create(
            servico=cls.servico, aluno=cls.aluno, nome="Rita Responsável Inventada",
            parentesco=Responsavel.Parentesco.MAE, responsavel_legal=True,
        )
        cls.tia = Responsavel.objects.create(
            servico=cls.servico, aluno=cls.aluno, nome="Tereza Tia Inventada",
            parentesco=Responsavel.Parentesco.TIO, responsavel_legal=False,
        )
        cls.outro_aluno = criar_aluno(cls.servico, nome="Caio Inventado Souza", criado_por=cls.professor_b)
        cls.responsavel_do_outro = Responsavel.objects.create(
            servico=cls.servico, aluno=cls.outro_aluno, nome="Olívia Outra Inventada",
            parentesco=Responsavel.Parentesco.MAE,
        )

        cls.termo_uso = Termo.objects.create(
            servico=cls.servico, tipo=Tipo.USO_DADOS, versao_do_termo=1,
            titulo="Uso dos dados (texto provisório)", texto=TEXTO_DO_TERMO_DE_USO, criado_por=cls.supervisao,
        )
        cls.termo_contato = Termo.objects.create(
            servico=cls.servico, tipo=Tipo.CONTATO_ESCOLA, versao_do_termo=1,
            titulo="Contato com a escola (texto provisório)", texto=TEXTO_DO_TERMO_DE_CONTATO,
            criado_por=cls.supervisao,
        )

        cls.aluno_de_fora = criar_aluno(cls.outro_servico, nome="Tomás Inventado de Fora")
        cls.responsavel_de_fora = Responsavel.objects.create(
            servico=cls.outro_servico, aluno=cls.aluno_de_fora, nome="Ivo Responsável de Fora",
            parentesco=Responsavel.Parentesco.PAI,
        )
        cls.termo_de_fora = Termo.objects.create(
            servico=cls.outro_servico, tipo=Tipo.CONTATO_ESCOLA, versao_do_termo=1,
            titulo="Termo de outro serviço", texto="Texto inventado de outro serviço.",
        )

    # ------------------------------------------------------------ ajudas

    def coleta(self, aluno=None, tipo=Tipo.CONTATO_ESCOLA, situacao=Situacao.VALIDA, forma=Forma.PAPEL,
               colhida_por=None, servico=None, termo=None, arquivo=None, **extra):
        """Uma coleta inventada, gravada direto no banco."""
        aluno = aluno or self.aluno
        servico = servico or aluno.servico
        if termo is None and servico == self.servico:
            termo = self.termo_contato if tipo == Tipo.CONTATO_ESCOLA else self.termo_uso
        colhida_por = colhida_por or self.professor
        extra.setdefault("responsavel_nome", "Rita Responsável Inventada" if situacao != Situacao.PENDENTE else "")
        if situacao != Situacao.PENDENTE:
            extra.setdefault("colhida_em", timezone.now().replace(microsecond=0))
        autorizacao = Autorizacao(
            servico=servico, aluno=aluno, tipo=tipo, situacao=situacao, forma=forma, termo=termo,
            colhida_por=colhida_por, criado_por=colhida_por, **extra,
        )
        if arquivo is not None:
            autorizacao.arquivo = arquivo
        autorizacao.save()
        return autorizacao

    def url_colher(self, aluno=None, tipo=Tipo.CONTATO_ESCOLA):
        return reverse("autorizacoes:colher", args=[(aluno or self.aluno).pk, tipo])

    def eventos(self, obj, acao=None):
        eventos = EventoAuditoria.objects.filter(modelo=obj._meta.label, objeto_id=str(obj.pk))
        return eventos.filter(acao=acao) if acao else eventos

    def dias_atras(self, dias):
        return timezone.localdate() - datetime.timedelta(days=dias)


__all__ = [
    "Acao", "Aluno", "Autorizacao", "BaseAutorizacoes", "Forma", "Situacao", "Termo", "Tipo", "conversa_txt",
    "data_url", "foto_jpg", "pdf", "png_de_assinatura", "requisicao",
]

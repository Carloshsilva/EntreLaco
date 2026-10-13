"""Base dos testes de aulas. Só dados inventados (nomes fictícios, e-mails @exemplo.org)."""
import datetime
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from aulas.models import Aula, HabilidadeBNCC
from core.models import Vinculo
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
from equipe.models import ComponenteCurricular

HOJE = timezone.localdate


def foto_de_teste(nome="atividade.jpg", *, com_exif=False, formato="JPEG", tamanho=(64, 48)):
    """Uma foto pequena gerada na hora; com `com_exif`, leva fabricante, modelo e localização inventados."""
    imagem = Image.new("RGB", tamanho, (180, 120, 60))
    saida = io.BytesIO()
    opcoes = {}
    if com_exif:
        exif = Image.Exif()
        exif[0x010F] = "Fabricante Inventado"  # Make
        exif[0x0110] = "Tablet Fictício 3000"  # Model
        exif[0x0132] = "2026:10:13 10:00:00"  # DateTime
        exif[0x8825] = {1: "S", 2: (23.0, 33.0, 1.0), 3: "W", 4: (46.0, 38.0, 1.0)}  # GPS inventado
        opcoes["exif"] = exif.tobytes()
    imagem.save(saida, format=formato, **opcoes)
    tipo = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[formato]
    return SimpleUploadedFile(nome, saida.getvalue(), content_type=tipo)


class BaseDeAulas(TestCase):
    """Dois serviços, com professor, supervisão (configura e vê tudo), apoio administrativo e alunos."""

    @classmethod
    def setUpClass(cls):
        cls._pasta = tempfile.mkdtemp(prefix="entrelaco-aulas-testes-")
        cls._arquivos = override_settings(MEDIA_ROOT=cls._pasta)
        cls._arquivos.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._arquivos.disable()
        shutil.rmtree(cls._pasta, ignore_errors=True)

    def setUp(self):
        self.servico = criar_servico(nome="Escola Móvel Inventada")
        self.professor = criar_professor(self.servico, nome="Ana Pereira Inventada", email="ana.prof@exemplo.org")
        self.outro_professor = criar_professor(self.servico, nome="Bruno Costa Inventado", email="bruno.prof@exemplo.org")
        self.supervisao = criar_supervisao(self.servico, nome="Carla Souza Inventada", email="carla.sup@exemplo.org")
        self.apoio = criar_apoio(self.servico, nome="Davi Lima Inventado", email="davi.apoio@exemplo.org")
        self.leitor = criar_pessoa(
            self.servico, criar_papel(self.servico, "Só vê aulas", ver=["identificacao", "aulas"]),
            nome="Eva Rocha Inventada", email="eva.leitura@exemplo.org",
        )
        self.aluno = criar_aluno(self.servico, nome="Lia Martins Inventada", leito="12")
        self.aluno_em_pausa = criar_aluno(self.servico, nome="Caio Prado Fictício", situacao="pausa")
        self.aluno_encerrado = criar_aluno(self.servico, nome="Gabi Nunes Fictícia", situacao="encerrado")
        self.componente = ComponenteCurricular.objects.create(servico=self.servico, nome="Matemática")
        self.componente_inativo = ComponenteCurricular.objects.create(servico=self.servico, nome="Latim", ativo=False)

        self.outro_servico = criar_servico(nome="Classe Hospitalar Fictícia")
        self.professor_de_fora = criar_professor(self.outro_servico, nome="Fábio Alves Inventado")
        self.aluno_de_fora = criar_aluno(self.outro_servico, nome="Theo Ramos Fictício")
        self.componente_de_fora = ComponenteCurricular.objects.create(servico=self.outro_servico, nome="Ciências")

    # ---------------------------------------------------------------- ajudas

    def entrar(self, pessoa):
        self.client.force_login(pessoa)

    def criar_aula(self, *, servico=None, aluno=None, professor=None, situacao=Aula.Situacao.REGISTRADA, data=None,
                   minutos=30, hora=datetime.time(10, 0), **extra):
        servico = servico or self.servico
        return Aula.objects.create(
            servico=servico, aluno=aluno or self.aluno, professor=professor or self.professor, situacao=situacao,
            data=data or HOJE(), duracao_minutos=minutos, hora_inicio=hora, **extra,
        )

    def criar_habilidade(self, codigo="EF01LP01", servico=None, **extra):
        extra.setdefault("descricao", "Habilidade inventada para teste de leitura.")
        return HabilidadeBNCC.objects.create(servico=servico or self.servico, codigo=codigo, **extra)

    def dados_do_registro(self, **mudancas):
        dados = {
            "aluno": self.aluno.pk,
            "data": HOJE().isoformat(),
            "hora_inicio": "10:00",
            "duracao_minutos": "30",
            "componentes": [self.componente.pk],
            "conteudo": "Leitura de uma história inventada e contagem até 20.",
            "participacao": "Participou com interesse.",
        }
        dados.update(mudancas)
        return {chave: valor for chave, valor in dados.items() if valor is not None}

    def requisicao(self, pessoa, servico=None):
        """Requisição com serviço e acesso, como o middleware do núcleo monta."""
        servico = servico or self.servico
        request = RequestFactory().get("/")
        request.user = pessoa
        vinculo = Vinculo.objects.select_related("papel").get(usuario=pessoa, servico=servico)
        request.servico = servico
        request.vinculo = vinculo
        request.acesso = Acesso.do_papel(vinculo.papel)
        return request

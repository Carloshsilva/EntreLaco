from django.conf import settings
from django.db import models

from core.arquivos import caminho_foto_de_aula
from core.models import ModeloDoServico


class HabilidadeBNCC(ModeloDoServico):
    """Lista de eixos e habilidades da BNCC mantida pelo serviço (RF-16)."""

    codigo = models.CharField("código", max_length=20)
    eixo = models.CharField(max_length=120, blank=True)
    descricao = models.TextField("descrição")
    ativa = models.BooleanField(default=True)

    GRUPOS_DE_CAMPOS = {"aulas": ["codigo", "eixo", "descricao", "ativa"]}

    class Meta:
        verbose_name = "habilidade da BNCC"
        verbose_name_plural = "habilidades da BNCC"
        ordering = ["codigo"]
        constraints = [models.UniqueConstraint(fields=["servico", "codigo"], name="habilidade_unica_por_servico")]

    def __str__(self):
        return f"{self.codigo}: {self.descricao[:80]}"


class Aula(ModeloDoServico):
    """Aula marcada na agenda e depois registrada (RF-15, RF-44).

    Uma aula pode nascer marcada (agenda) ou já registrada (aula dada sem
    agendamento). Registrar aula de aluno sem ficha completa gera a pendência
    da ficha para o professor da aula (RF-19).
    """

    class Situacao(models.TextChoices):
        MARCADA = "marcada", "Marcada"
        REGISTRADA = "registrada", "Registrada"
        NAO_REALIZADA = "nao_realizada", "Não aconteceu"

    aluno = models.ForeignKey("alunos.Aluno", on_delete=models.PROTECT, related_name="aulas")
    professor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="aulas", verbose_name="professor(a)"
    )
    data = models.DateField()
    hora_inicio = models.TimeField("horário", null=True, blank=True)
    duracao_minutos = models.PositiveSmallIntegerField(
        "minutos de atendimento", default=30, help_text="Conta para o número de aulas pela regra do serviço (RF-55)."
    )
    situacao = models.CharField("situação", max_length=15, choices=Situacao.choices, default=Situacao.MARCADA)
    componentes = models.ManyToManyField(
        "equipe.ComponenteCurricular", blank=True, related_name="aulas", verbose_name="componentes trabalhados"
    )
    conteudo = models.TextField("o que foi trabalhado", blank=True)
    participacao = models.TextField(
        "como o aluno participou", blank=True, help_text="Interesse, dificuldades, o que ficou para a próxima aula."
    )
    habilidades = models.ManyToManyField(
        HabilidadeBNCC, blank=True, related_name="aulas", verbose_name="habilidades da BNCC"
    )
    motivo_nao_realizada = models.CharField(
        "por que a aula não aconteceu", max_length=255, blank=True,
        help_text="Por exemplo: exame, criança dormindo, alta antes do horário.",
    )
    registrada_em = models.DateTimeField("registrada em", null=True, blank=True, editable=False)
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", editable=False
    )

    GRUPOS_DE_CAMPOS = {
        "aulas": [
            "aluno", "professor", "data", "hora_inicio", "duracao_minutos", "situacao", "componentes", "conteudo",
            "participacao", "habilidades", "motivo_nao_realizada",
        ],
    }

    class Meta:
        verbose_name = "aula"
        verbose_name_plural = "aulas"
        ordering = ["-data", "-hora_inicio"]
        indexes = [
            models.Index(fields=["servico", "data"]),
            models.Index(fields=["servico", "professor", "data"]),
            models.Index(fields=["aluno", "-data"]),
        ]

    def __str__(self):
        return f"Aula de {self.aluno} em {self.data:%d/%m/%Y}"

    def aulas_equivalentes(self, minutos_por_aula=None):
        """Quantas aulas este atendimento conta (RF-55). Na Escola Móvel, 30 minutos = 1 aula.

        Atendimento menor que a regra conta zero; o resto da divisão não arredonda para cima.
        """
        if self.situacao != self.Situacao.REGISTRADA:
            return 0
        minutos_por_aula = minutos_por_aula or self.servico.minutos_por_aula or 30
        return self.duracao_minutos // minutos_por_aula


class FotoDaAula(ModeloDoServico):
    """Foto de atividade anexada ao registro de aula (RF-15)."""

    aula = models.ForeignKey(Aula, on_delete=models.CASCADE, related_name="fotos")
    arquivo = models.ImageField("foto", upload_to=caminho_foto_de_aula)
    legenda = models.CharField(max_length=200, blank=True)

    GRUPOS_DE_CAMPOS = {"aulas": ["arquivo", "legenda"]}

    class Meta:
        verbose_name = "foto da aula"
        verbose_name_plural = "fotos das aulas"
        ordering = ["criado_em"]

    def __str__(self):
        return self.legenda or f"Foto da {self.aula}"

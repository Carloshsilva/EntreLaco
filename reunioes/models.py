from django.conf import settings
from django.db import models

from core.models import ModeloDoServico
from core.permissoes import GRUPOS_DE_DADOS


class Reuniao(ModeloDoServico):
    """Reunião do calendário, com pauta e ata (RF-17, RF-44)."""

    class Tipo(models.TextChoices):
        SEMANAL = "semanal", "Reunião semanal da equipe"
        MULTIDISCIPLINAR = "multidisciplinar", "Multidisciplinar"
        CUIDADOS_PALIATIVOS = "cuidados_paliativos", "Cuidados paliativos"
        TMO = "tmo", "TMO"
        OUTRA = "outra", "Outra"

    class Situacao(models.TextChoices):
        MARCADA = "marcada", "Marcada"
        REALIZADA = "realizada", "Realizada"
        CANCELADA = "cancelada", "Cancelada"

    tipo = models.CharField(max_length=25, choices=Tipo.choices, default=Tipo.SEMANAL)
    titulo = models.CharField("título", max_length=150)
    data = models.DateField()
    hora_inicio = models.TimeField("horário", null=True, blank=True)
    duracao_minutos = models.PositiveSmallIntegerField("duração (minutos)", default=60)
    local = models.CharField(max_length=120, blank=True)
    participantes = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="reunioes", verbose_name="participantes da equipe"
    )
    pauta = models.TextField(blank=True)
    ata = models.TextField(blank=True)
    situacao = models.CharField("situação", max_length=10, choices=Situacao.choices, default=Situacao.MARCADA)

    GRUPOS_DE_CAMPOS = {
        "atas": ["tipo", "titulo", "data", "hora_inicio", "duracao_minutos", "local", "participantes", "pauta", "ata",
                 "situacao"],
    }

    class Meta:
        verbose_name = "reunião"
        verbose_name_plural = "reuniões"
        ordering = ["-data", "-hora_inicio"]
        indexes = [models.Index(fields=["servico", "data"])]

    def __str__(self):
        return f"{self.titulo} ({self.data:%d/%m/%Y})"


# Tipos de dado que uma citação pode carregar; quem não vê o tipo não vê a citação (RF-17).
GRUPOS_DE_CITACAO = [(codigo, nome) for codigo, nome, _ in GRUPOS_DE_DADOS
                     if codigo in {"atas", "aprendizagem", "sensivel", "familia", "escolar"}]


class CitacaoDeAluno(ModeloDoServico):
    """Um aluno citado na ata, com encaminhamento e responsável (RF-17).

    Aparece no perfil do aluno. Na primeira versão, a citação com responsável e
    prazo aparece como pendência dele; o quadro de tarefas vem depois.
    """

    reuniao = models.ForeignKey(Reuniao, on_delete=models.CASCADE, related_name="citacoes")
    aluno = models.ForeignKey("alunos.Aluno", on_delete=models.CASCADE, related_name="citacoes")
    texto = models.TextField("o que foi dito")
    grupo_de_dado = models.CharField(
        "tipo de dado", max_length=20, choices=GRUPOS_DE_CITACAO, default="atas",
        help_text="Se a citação fala de saúde, escolha Saúde e dados sensíveis: só quem vê esse tipo de dado verá a citação.",
    )
    encaminhamento = models.TextField(blank=True)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="responsável pelo encaminhamento",
    )
    prazo = models.DateField(null=True, blank=True)
    concluida = models.BooleanField("encaminhamento concluído", default=False)

    GRUPOS_DE_CAMPOS = {
        "atas": ["aluno", "texto", "grupo_de_dado", "encaminhamento", "responsavel", "prazo", "concluida"],
    }

    class Meta:
        verbose_name = "citação de aluno"
        verbose_name_plural = "citações de alunos"
        ordering = ["-reuniao__data", "-criado_em"]

    def __str__(self):
        return f"{self.aluno} na {self.reuniao}"

    def grupo_na_trilha(self):
        """Na trilha, a citação vale como ata e como o tipo dela: só vê o evento quem vê os dois,
        a mesma regra de `visivel_para`."""
        return ("atas", self.grupo_de_dado)

    def visivel_para(self, acesso):
        return acesso.pode_ver("atas") and acesso.pode_ver(self.grupo_de_dado)

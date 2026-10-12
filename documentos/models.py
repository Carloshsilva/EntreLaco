from django.db import models

from core.arquivos import caminho_documento
from core.models import ModeloDoServico


class Documento(ModeloDoServico):
    """Foto ou scan guardado no histórico do aluno, com quem digitalizou (RF-12).

    Quem digitalizou é `criado_por`. A regra de guarda do papel original
    depois da foto espera o advogado (LGPD-08).
    """

    class Tipo(models.TextChoices):
        FICHA_PAPEL = "ficha_papel", "Ficha de papel assinada"
        TERMO = "termo", "Termo de autorização"
        RELATORIO = "relatorio", "Relatório ou laudo"
        ESCOLAR = "escolar", "Documento escolar"
        ATIVIDADE = "atividade", "Atividade do aluno"
        OUTRO = "outro", "Outro"

    aluno = models.ForeignKey("alunos.Aluno", on_delete=models.CASCADE, related_name="documentos")
    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.FICHA_PAPEL)
    titulo = models.CharField("título", max_length=150)
    arquivo = models.FileField(upload_to=caminho_documento)
    data_documento = models.DateField("data do documento", null=True, blank=True)
    observacoes = models.TextField("observações", blank=True)
    tamanho = models.PositiveIntegerField("tamanho em bytes", default=0, editable=False)
    impressao_digital = models.CharField("impressão digital (SHA-256)", max_length=64, blank=True, editable=False)

    GRUPOS_DE_CAMPOS = {"documentos": ["tipo", "titulo", "arquivo", "data_documento", "observacoes"]}

    class Meta:
        verbose_name = "documento"
        verbose_name_plural = "documentos"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["aluno", "-criado_em"])]

    def __str__(self):
        return self.titulo

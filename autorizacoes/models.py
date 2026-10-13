from django.conf import settings
from django.db import models

from core.arquivos import caminho_autorizacao
from core.models import ModeloDoServico


class Tipo(models.TextChoices):
    USO_DADOS = "uso_dados", "Uso dos dados"
    CONTATO_ESCOLA = "contato_escola", "Contato com a escola"


class Termo(ModeloDoServico):
    """Texto de um termo de autorização, com versão (LGPD-03).

    O texto definitivo é do advogado (LGPD-02); nesta versão de teste o termo é
    um texto provisório, e cada autorização guarda a versão que a família viu.
    """

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    versao_do_termo = models.PositiveIntegerField("versão do termo", default=1)
    titulo = models.CharField("título", max_length=150)
    texto = models.TextField()
    vigente = models.BooleanField(default=True, help_text="Só um termo vigente por tipo.")

    GRUPOS_DE_CAMPOS = {"autorizacoes": ["tipo", "versao_do_termo", "titulo", "texto", "vigente"]}

    class Meta:
        verbose_name = "termo"
        verbose_name_plural = "termos"
        ordering = ["tipo", "-versao_do_termo"]
        constraints = [models.UniqueConstraint(fields=["servico", "tipo", "versao_do_termo"], name="termo_versao_unica")]

    def __str__(self):
        return f"{self.titulo} (versão {self.versao_do_termo})"


class Autorizacao(ModeloDoServico):
    """Uma coleta de autorização da família (RF-25 a RF-29, RF-64).

    Cada coleta é um registro: uma nova coleta não apaga a anterior, para a
    prova continuar guardada (LGPD-03). A situação atual de cada tipo é a da
    coleta mais recente daquele aluno.
    """

    class Situacao(models.TextChoices):
        PENDENTE = "pendente", "Pendente"
        PROVISORIA = "provisoria", "Provisória"
        VALIDA = "valida", "Válida"
        RECUSADA = "recusada", "Recusada"
        REVOGADA = "revogada", "Revogada"

    class Forma(models.TextChoices):
        TABLET = "tablet", "Assinatura no tablet"
        LINK = "link", "Link para o celular"
        PAPEL = "papel", "Papel assinado e fotografado"
        WHATSAPP = "whatsapp", "Sim por WhatsApp"

    aluno = models.ForeignKey("alunos.Aluno", on_delete=models.CASCADE, related_name="autorizacoes")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    situacao = models.CharField("situação", max_length=12, choices=Situacao.choices, default=Situacao.PENDENTE)
    forma = models.CharField("forma de coleta", max_length=10, choices=Forma.choices, blank=True)
    termo = models.ForeignKey(Termo, on_delete=models.PROTECT, null=True, blank=True, related_name="autorizacoes")
    responsavel = models.ForeignKey(
        "alunos.Responsavel", on_delete=models.SET_NULL, null=True, blank=True, related_name="autorizacoes",
        verbose_name="responsável que autorizou",
    )
    # Cópia do nome e do documento no momento da coleta: a prova não muda se o cadastro mudar depois.
    responsavel_nome = models.CharField("nome de quem autorizou", max_length=150, blank=True)
    responsavel_documento = models.CharField(
        "documento de quem autorizou", max_length=40, blank=True, help_text="RG ou CPF, como a pessoa informar."
    )
    colhida_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="quem colheu",
    )
    colhida_em = models.DateTimeField("colhida em", null=True, blank=True)
    assinatura = models.ImageField(
        "assinatura no tablet", upload_to=caminho_autorizacao, blank=True, editable=False
    )
    arquivo = models.FileField(
        "foto do papel ou conversa do WhatsApp", upload_to=caminho_autorizacao, blank=True,
        help_text="Papel assinado fotografado ou a conversa exportada do WhatsApp.",
    )
    impressao_digital = models.CharField(
        "impressão digital (SHA-256)", max_length=64, blank=True, editable=False,
        help_text="Mostra que o termo, quem assinou e a assinatura não mudaram depois (LGPD-03).",
    )
    aparelho = models.CharField("aparelho usado", max_length=255, blank=True, editable=False)
    revogada_em = models.DateTimeField("revogada em", null=True, blank=True, editable=False)
    revogacao_motivo = models.TextField("como a família pediu a revogação", blank=True)
    observacoes = models.TextField("observações", blank=True)

    GRUPOS_DE_CAMPOS = {
        "autorizacoes": [
            "tipo", "situacao", "forma", "termo", "responsavel", "responsavel_nome", "responsavel_documento",
            "colhida_por", "colhida_em", "assinatura", "arquivo", "impressao_digital", "aparelho", "revogada_em",
            "revogacao_motivo", "observacoes",
        ],
    }

    class Meta:
        verbose_name = "autorização"
        verbose_name_plural = "autorizações"
        ordering = ["-criado_em", "-id"]
        indexes = [models.Index(fields=["aluno", "tipo", "-criado_em"])]

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.aluno}: {self.get_situacao_display()}"

    @property
    def libera_contato(self):
        """Contato com a escola só com autorização válida ou provisória (RF-27, RF-28)."""
        return self.tipo == Tipo.CONTATO_ESCOLA and self.situacao in {self.Situacao.VALIDA, self.Situacao.PROVISORIA}


def autorizacao_atual(aluno, tipo):
    """A coleta mais recente daquele tipo, ou None."""
    return aluno.autorizacoes.filter(tipo=tipo).order_by("-criado_em", "-id").first()

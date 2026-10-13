from django.conf import settings
from django.db import models

from core.models import ModeloDoServico


class Escola(models.Model):
    """Base nacional de escolas de origem, comum a todos os serviços (RF-13, SEG-05).

    Só guarda dado público (o que o Censo Escolar do INEP publica). O contato que
    cada serviço confirma fica em ContatoEscola, separado por serviço (RF-14).
    Nesta versão de teste a base vem com escolas inventadas.
    """

    class Rede(models.TextChoices):
        MUNICIPAL = "municipal", "Municipal"
        ESTADUAL = "estadual", "Estadual"
        FEDERAL = "federal", "Federal"
        PRIVADA = "privada", "Privada"

    class Funcionamento(models.TextChoices):
        EM_ATIVIDADE = "em_atividade", "Em atividade"
        PARALISADA = "paralisada", "Paralisada"
        EXTINTA = "extinta", "Extinta"

    codigo_inep = models.CharField("código INEP", max_length=8, unique=True)
    nome = models.CharField(max_length=200)
    rede = models.CharField(max_length=20, choices=Rede.choices, blank=True)
    endereco = models.CharField("endereço", max_length=255, blank=True)
    bairro = models.CharField(max_length=120, blank=True)
    municipio = models.CharField("município", max_length=120)
    uf = models.CharField("UF", max_length=2)
    cep = models.CharField("CEP", max_length=9, blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    funcionamento = models.CharField(
        "situação de funcionamento", max_length=20, choices=Funcionamento.choices, default=Funcionamento.EM_ATIVIDADE
    )
    fonte = models.CharField(
        max_length=120, default="Base fictícia de teste",
        help_text="De onde veio o registro: INEP, cadastro de um serviço ou base de teste.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "escola"
        verbose_name_plural = "escolas"
        ordering = ["nome"]
        indexes = [models.Index(fields=["nome"]), models.Index(fields=["municipio", "uf"])]

    def __str__(self):
        return f"{self.nome} ({self.municipio}/{self.uf})"


class ContatoEscola(ModeloDoServico):
    """O contato da escola que um serviço confirmou (RF-14).

    Outros serviços não veem este contato; o que é comum é só a base pública.
    """

    class Situacao(models.TextChoices):
        ATUALIZADO = "atualizado", "Atualizado"
        PRECISA_ATUALIZAR = "precisa_atualizar", "Precisa atualizar"

    escola = models.ForeignKey(Escola, on_delete=models.PROTECT, related_name="contatos")
    email = models.EmailField("e-mail", blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    quem_atende = models.CharField(
        "quem atende", max_length=150, blank=True, help_text="Nome e cargo, por exemplo: Marta, coordenadora pedagógica."
    )
    observacoes = models.TextField("observações", blank=True)
    situacao = models.CharField(
        "situação do contato", max_length=20, choices=Situacao.choices, default=Situacao.PRECISA_ATUALIZAR
    )
    confirmado_em = models.DateField("confirmado em", null=True, blank=True, editable=False)
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", editable=False
    )

    GRUPOS_DE_CAMPOS = {"escola_contato": ["email", "telefone", "quem_atende", "observacoes", "situacao"]}

    class Meta:
        verbose_name = "contato da escola"
        verbose_name_plural = "contatos das escolas"
        ordering = ["escola__nome"]
        constraints = [models.UniqueConstraint(fields=["servico", "escola"], name="contato_unico_por_servico")]

    def __str__(self):
        return f"Contato de {self.escola.nome}"

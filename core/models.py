from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from .permissoes import CODIGOS_DE_ACAO, CODIGOS_DE_GRUPO, NENHUM

MOTIVOS_DE_SAIDA_PADRAO = ["Alta", "Fim do tratamento", "Volta à escola", "Transferência", "Óbito"]


def motivos_de_saida_padrao():
    return list(MOTIVOS_DE_SAIDA_PADRAO)


class Servico(models.Model):
    """Um serviço de educação hospitalar, cliente da plataforma (RF-01)."""

    nome = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    ativo = models.BooleanField(default=True)
    # Parâmetros que quem configura o serviço ajusta (RF-62).
    minutos_por_aula = models.PositiveSmallIntegerField(
        "minutos de atendimento por aula", default=30,
        help_text="Regra de equivalência: quantos minutos de atendimento contam 1 aula (RF-55).",
    )
    bncc_ativa = models.BooleanField(
        "lista da BNCC ligada", default=False,
        help_text="Mostra a lista de eixos e habilidades da BNCC no registro de aula (RF-16).",
    )
    prazo_revisao_ativo_dias = models.PositiveSmallIntegerField(
        "prazo da revisão de aluno ativo (dias)", default=21,
        help_text="Sem aula registrada ou marcada nesse prazo, o aluno entra em revisão (RF-21).",
    )
    motivos_saida = models.JSONField("motivos de saída", default=motivos_de_saida_padrao)
    modulos = models.JSONField(
        "módulos ligados", default=list, blank=True,
        help_text="Módulos ligados pelo administrador da plataforma (RF-02).",
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "serviço"
        verbose_name_plural = "serviços"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _criar(self, email, password, **extra):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        usuario = self.model(email=self.normalize_email(email).lower(), **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._criar(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._criar(email, password, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Uma pessoa com login próprio (RF-05). Superusuário = administrador da plataforma."""

    email = models.EmailField("e-mail", unique=True)
    nome = models.CharField("nome completo", max_length=150)
    whatsapp_trabalho = models.CharField(
        "WhatsApp de trabalho", max_length=20, blank=True,
        help_text="Guardado para quando o envio por WhatsApp entrar (RF-48). Nada é enviado nesta versão.",
    )
    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField("acessa o painel da plataforma", default=False)
    date_joined = models.DateTimeField("cadastrado em", default=timezone.now)
    # Verificação em duas etapas (SEG-07): obrigatória para o administrador e para quem configura.
    totp_segredo = models.CharField(max_length=64, blank=True, editable=False)
    totp_ativo = models.BooleanField("verificação em duas etapas ativa", default=False)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["nome"]

    class Meta:
        verbose_name = "pessoa"
        verbose_name_plural = "pessoas"
        ordering = ["nome"]

    def __str__(self):
        return self.nome or self.email

    def get_full_name(self):
        return self.nome

    def get_short_name(self):
        return (self.nome or self.email).split(" ")[0]

    @property
    def nome_curto(self):
        """Primeiro nome e inicial do último: "Ana P."."""
        partes = (self.nome or "").split()
        if len(partes) >= 2:
            return f"{partes[0]} {partes[-1][0]}."
        return self.nome or self.email


def acessos_padrao():
    return {grupo: NENHUM for grupo in CODIGOS_DE_GRUPO}


class Papel(models.Model):
    """Papel cadastrado pelo serviço, com o que vê e edita por tipo de dado (RF-06, RF-07)."""

    servico = models.ForeignKey(Servico, on_delete=models.CASCADE, related_name="papeis")
    nome = models.CharField(max_length=80)
    descricao = models.CharField("descrição", max_length=255, blank=True)
    acessos = models.JSONField(default=acessos_padrao, help_text="Tipo de dado → nenhum, ver ou editar.")
    acoes = models.JSONField(default=list, blank=True, help_text=f"Ações liberadas: {', '.join(CODIGOS_DE_ACAO)}.")
    pode_configurar = models.BooleanField(
        "pode configurar o serviço", default=False,
        help_text="Só o administrador da plataforma libera, e a liberação fica na trilha (RF-03).",
    )

    class Meta:
        verbose_name = "papel"
        verbose_name_plural = "papéis"
        ordering = ["servico", "nome"]
        constraints = [models.UniqueConstraint(fields=["servico", "nome"], name="papel_unico_por_servico")]

    def __str__(self):
        return f"{self.nome} ({self.servico})"


class Vinculo(models.Model):
    """Liga uma pessoa a um serviço, com um papel."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vinculos")
    servico = models.ForeignKey(Servico, on_delete=models.CASCADE, related_name="vinculos")
    papel = models.ForeignKey(Papel, on_delete=models.PROTECT, related_name="vinculos")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "vínculo"
        verbose_name_plural = "vínculos"
        constraints = [models.UniqueConstraint(fields=["usuario", "servico"], name="vinculo_unico")]

    def __str__(self):
        return f"{self.usuario} em {self.servico} como {self.papel.nome}"


class ModeloDoServico(models.Model):
    """Base de todo dado que pertence a um serviço (SEG-05).

    `versao` sobe a cada gravação e serve para detectar quando duas pessoas
    mudaram o mesmo dado ao mesmo tempo (RNF-04).
    """

    servico = models.ForeignKey(Servico, on_delete=models.PROTECT, related_name="+")
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("atualizado em", auto_now=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", editable=False
    )
    atualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", editable=False
    )
    versao = models.PositiveIntegerField(default=1, editable=False)

    # Tipo de dado → campos. Precisa listar todo campo editável do modelo.
    GRUPOS_DE_CAMPOS = {}

    class Meta:
        abstract = True


class EventoAuditoria(models.Model):
    """Trilha de auditoria (SEG-03, SEG-04). Só é criada, nunca editada nem apagada."""

    class Acao(models.TextChoices):
        CRIOU = "criou", "Criou"
        ALTEROU = "alterou", "Alterou"
        VALIDOU = "validou", "Validou"
        EXCLUIU = "excluiu", "Excluiu"
        MUDOU_SITUACAO = "mudou_situacao", "Mudou a situação"
        LIBEROU_PERMISSAO = "liberou_permissao", "Liberou permissão"
        MUDOU_PAPEL = "mudou_papel", "Mudou papel"
        ENTROU = "entrou", "Entrou"
        SAIU = "saiu", "Saiu"
        FALHOU_LOGIN = "falhou_login", "Errou a senha"
        BAIXOU_ARQUIVO = "baixou_arquivo", "Abriu arquivo"
        ASSINOU = "assinou", "Registrou assinatura"
        OUTRO = "outro", "Outro"

    servico = models.ForeignKey(Servico, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    usuario_nome = models.CharField(max_length=150, blank=True)
    acao = models.CharField(max_length=30, choices=Acao.choices)
    modelo = models.CharField(max_length=80, blank=True)
    objeto_id = models.CharField(max_length=40, blank=True)
    objeto_repr = models.CharField(max_length=200, blank=True)
    aluno_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    # {campo: {"rotulo": ..., "grupo": ..., "de": ..., "para": ...}}
    mudancas = models.JSONField(default=dict, blank=True)
    motivo = models.TextField(blank=True)
    descricao = models.CharField(max_length=255, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    criado_em = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "evento da trilha"
        verbose_name_plural = "trilha de auditoria"
        ordering = ["-criado_em", "-id"]
        indexes = [models.Index(fields=["servico", "-criado_em"]), models.Index(fields=["modelo", "objeto_id"])]

    def __str__(self):
        return f"{self.usuario_nome} {self.get_acao_display().lower()} {self.objeto_repr}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("A trilha de auditoria não pode ser alterada.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("A trilha de auditoria não pode ser apagada.")

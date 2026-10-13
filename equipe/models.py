from django.conf import settings
from django.db import models

from core.models import ModeloDoServico


class ComponenteCurricular(ModeloDoServico):
    """O que se ensina: lista mantida por cada serviço (RF-09)."""

    nome = models.CharField(max_length=80)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "componente curricular"
        verbose_name_plural = "componentes curriculares"
        ordering = ["nome"]
        constraints = [models.UniqueConstraint(fields=["servico", "nome"], name="componente_unico_por_servico")]

    def __str__(self):
        return self.nome


class PerfilProfessor(ModeloDoServico):
    """O que cada professor ensina, em um serviço (RF-09).

    O calendário do professor é a agenda filtrada por ele (aulas e reuniões).
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfis_de_professor", verbose_name="pessoa"
    )
    componentes = models.ManyToManyField(
        ComponenteCurricular, blank=True, related_name="professores", verbose_name="o que ensina"
    )
    educacao_infantil = models.BooleanField("educação infantil", default=False)
    anos_iniciais = models.BooleanField("anos iniciais (1º ao 5º ano)", default=False)
    anos_finais = models.BooleanField("anos finais (6º ao 9º ano)", default=False)
    ensino_medio = models.BooleanField("ensino médio", default=False)
    eja = models.BooleanField("EJA", default=False)
    observacoes = models.TextField("observações", blank=True)

    class Meta:
        verbose_name = "perfil de professor"
        verbose_name_plural = "perfis de professor"
        ordering = ["usuario__nome"]
        constraints = [models.UniqueConstraint(fields=["servico", "usuario"], name="professor_unico_por_servico")]

    def __str__(self):
        return f"Professor(a) {self.usuario}"

    @property
    def etapas(self):
        campos = ["educacao_infantil", "anos_iniciais", "anos_finais", "ensino_medio", "eja"]
        return [str(self._meta.get_field(c).verbose_name) for c in campos if getattr(self, c)]

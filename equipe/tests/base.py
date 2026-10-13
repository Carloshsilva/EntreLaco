"""Dados inventados comuns aos testes da equipe."""
from django.test import TestCase

from core.models import EventoAuditoria
from core.testes import criar_apoio, criar_papel, criar_pessoa, criar_professor, criar_servico, criar_supervisao


class EquipeTestCase(TestCase):
    """Um serviço com supervisão (configura), coordenação (só cuida da equipe), professor e apoio,
    e um segundo serviço com uma pessoa de fora."""

    @classmethod
    def setUpTestData(cls):
        cls.servico = criar_servico("Escola Móvel Inventada")
        cls.outro_servico = criar_servico("Classe Hospitalar Fictícia")
        cls.supervisao = criar_supervisao(cls.servico, nome="Sueli Supervisora Inventada", email="sueli@exemplo.org")
        cls.papel_supervisao = cls.supervisao.vinculos.get().papel
        cls.papel_coordenacao = criar_papel(cls.servico, "Coordenação de equipe", acoes=["gerir_equipe"])
        cls.coordenacao = criar_pessoa(
            cls.servico, cls.papel_coordenacao, nome="Caio Coordenador Inventado", email="caio@exemplo.org"
        )
        cls.professor = criar_professor(cls.servico, nome="Paula Professora Inventada", email="paula@exemplo.org")
        cls.papel_professor = cls.professor.vinculos.get().papel
        cls.apoio = criar_apoio(cls.servico, nome="Abel Apoio Inventado", email="abel@exemplo.org")
        cls.de_fora = criar_professor(cls.outro_servico, nome="Flora De Fora Inventada", email="flora@exemplo.org")

    def entrar(self, pessoa):
        self.client.force_login(pessoa)

    def eventos(self, **filtro):
        return EventoAuditoria.objects.filter(**filtro)

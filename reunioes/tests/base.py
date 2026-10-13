"""Dados inventados comuns aos testes do módulo reuniões."""
import datetime

from django.test import RequestFactory, TestCase
from django.utils import timezone

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
from reunioes.models import CitacaoDeAluno, Reuniao

Acao = EventoAuditoria.Acao


def requisicao(usuario, caminho="/"):
    """Requisição com serviço e acesso, como o ServicoMiddleware deixaria."""
    request = RequestFactory().get(caminho)
    request.user = usuario
    vinculo = usuario.vinculos.select_related("servico", "papel").get()
    request.servico = vinculo.servico
    request.vinculo = vinculo
    request.acesso = Acesso.do_papel(vinculo.papel)
    return request


class BaseReunioes(TestCase):
    """Um serviço com supervisão (edita tudo), professores (veem as atas), apoio (não vê as atas) e uma
    secretaria das reuniões (edita as atas, mas não vê saúde); um segundo serviço com uma pessoa de fora."""

    @classmethod
    def setUpTestData(cls):
        cls.hoje = timezone.localdate()
        cls.servico = criar_servico("Escola Móvel Inventada")
        cls.outro_servico = criar_servico("Classe Hospitalar Fictícia")
        cls.supervisao = criar_supervisao(cls.servico, nome="Sara Supervisora Inventada", email="sara@exemplo.org")
        cls.professor = criar_professor(cls.servico, nome="Paula Professora Inventada", email="paula@exemplo.org")
        cls.professor_dois = criar_professor(cls.servico, nome="Tiago Professor Fictício", email="tiago@exemplo.org")
        cls.apoio = criar_apoio(cls.servico, nome="Abel Apoio Inventado", email="abel@exemplo.org")
        cls.secretaria = criar_pessoa(
            cls.servico, criar_papel(cls.servico, "Secretaria das reuniões", editar=["atas"], ver=["identificacao"]),
            nome="Rita Secretaria Inventada", email="rita@exemplo.org",
        )
        cls.de_fora = criar_supervisao(cls.outro_servico, nome="Flora De Fora Inventada", email="flora@exemplo.org")

        cls.aluno = criar_aluno(cls.servico, nome="Lia Inventada Moreira")
        cls.aluno_dois = criar_aluno(cls.servico, nome="Caio Fictício Prado")
        cls.aluno_de_fora = criar_aluno(cls.outro_servico, nome="Nina De Fora Souza")

        cls.reuniao = Reuniao.objects.create(
            servico=cls.servico, tipo=Reuniao.Tipo.SEMANAL, titulo="Reunião semanal da equipe",
            data=cls.hoje + datetime.timedelta(days=2), hora_inicio=datetime.time(14, 0), duracao_minutos=60,
            local="Sala da equipe inventada", pauta="Alunos novos da semana\nRevisão das pendências",
            criado_por=cls.supervisao,
        )
        cls.reuniao.participantes.set([cls.supervisao, cls.professor])
        cls.reuniao_passada = Reuniao.objects.create(
            servico=cls.servico, tipo=Reuniao.Tipo.MULTIDISCIPLINAR, titulo="Reunião multidisciplinar de outubro",
            data=cls.hoje - datetime.timedelta(days=7), situacao=Reuniao.Situacao.REALIZADA,
            ata="Conversamos sobre os alunos da oncologia inventada.",
        )
        cls.reuniao_de_fora = Reuniao.objects.create(
            servico=cls.outro_servico, titulo="Reunião do outro serviço", data=cls.hoje + datetime.timedelta(days=1),
        )

    def citar(self, reuniao=None, aluno=None, grupo="atas", **extra):
        reuniao = reuniao or self.reuniao
        extra.setdefault("texto", "A equipe combinou levar atividades de leitura.")
        return CitacaoDeAluno.objects.create(
            servico=reuniao.servico, reuniao=reuniao, aluno=aluno or self.aluno, grupo_de_dado=grupo, **extra
        )

    def entrar(self, pessoa):
        self.client.force_login(pessoa)

    def assertUmH1(self, resposta):
        self.assertContains(resposta, "<h1", count=1)

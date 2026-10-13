"""Dados inventados comuns aos testes do módulo alunos. Nada de dado real."""
import datetime

from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from alunos.models import Aluno, MudancaDeSituacao, Responsavel
from core.models import EventoAuditoria
from core.permissoes import Acesso
from core.testes import (
    criar_aluno,
    criar_apoio,
    criar_escola,
    criar_papel,
    criar_pessoa,
    criar_professor,
    criar_servico,
    criar_supervisao,
)

Acao = EventoAuditoria.Acao
Situacao = Aluno.Situacao

DIAGNOSTICO = "Diagnóstico inventado para teste"


def hoje():
    return timezone.localdate()


def dias_atras(dias):
    return hoje() - datetime.timedelta(days=dias)


def requisicao(usuario, caminho="/"):
    """Requisição com serviço e acesso, como o ServicoMiddleware deixaria."""
    request = RequestFactory().get(caminho)
    request.user = usuario
    vinculo = usuario.vinculos.select_related("servico", "papel").get()
    request.servico = vinculo.servico
    request.vinculo = vinculo
    request.acesso = Acesso.do_papel(vinculo.papel)
    return request


def dados_do_formulario(form, **trocas):
    """O que o navegador enviaria com o formulário como veio na tela, trocando alguns campos."""
    dados = {}
    for campo in form:
        if campo.name == "motivo_alteracao":
            continue
        valor = campo.value()
        if campo.widget_type == "checkbox":
            if valor:
                dados[campo.name] = "on"
            continue
        if valor is None:
            valor = ""
        if isinstance(valor, datetime.date):
            valor = valor.isoformat()
        dados[campo.name] = [str(v) for v in valor] if isinstance(valor, (list, tuple)) else str(valor)
    for nome, valor in trocas.items():
        if valor is None:
            dados.pop(nome, None)
        else:
            dados[nome] = valor
    return dados


class BaseAlunos(TestCase):
    """Um serviço com professor, orientação (muda situação), supervisão (configura), apoio
    administrativo e papéis recortados; e um segundo serviço com uma pessoa e um aluno de fora."""

    @classmethod
    def setUpTestData(cls):
        cls.servico = criar_servico("Escola Móvel Inventada")
        cls.outro_servico = criar_servico("Classe Hospitalar Fictícia")

        cls.professor = criar_professor(cls.servico, nome="Paula Professora Inventada", email="paula@exemplo.org")
        cls.professor_b = criar_professor(cls.servico, nome="Bruno Professor Inventado", email="bruno@exemplo.org")
        cls.supervisao = criar_supervisao(cls.servico, nome="Sueli Supervisora Inventada", email="sueli@exemplo.org")
        cls.papel_orientacao = criar_papel(
            cls.servico, "Orientação pedagógica",
            editar=["identificacao", "aprendizagem", "escolar", "familia"], ver=["sensivel", "aulas", "autorizacoes"],
            acoes=["mudar_situacao"],
        )
        cls.orientacao = criar_pessoa(
            cls.servico, cls.papel_orientacao, nome="Olga Orientadora Inventada", email="olga@exemplo.org"
        )
        cls.apoio = criar_apoio(cls.servico, nome="Abel Apoio Inventado", email="abel@exemplo.org")
        cls.so_aulas = criar_pessoa(
            cls.servico, criar_papel(cls.servico, "Só aulas", editar=["aulas"]), nome="Saulo Só Aulas Inventado",
            email="so.aulas@exemplo.org",
        )
        cls.so_ver = criar_pessoa(
            cls.servico, criar_papel(cls.servico, "Só vê alunos", ver=["identificacao", "aulas"]),
            nome="Vera Só Vê Inventada", email="so.ver@exemplo.org",
        )
        cls.de_fora = criar_supervisao(cls.outro_servico, nome="Flora De Fora Inventada", email="flora@exemplo.org")

        cls.escola = criar_escola("Escola Municipal Inventada Alfa", codigo="93000001")
        cls.aluno = criar_aluno(
            cls.servico, nome="Lia Inventada Moreira", data_nascimento=dias_atras(9 * 365 + 10),
            unidade="Oncologia Fictícia", leito="12B", data_internacao=dias_atras(30),
            visao=Aluno.Condicao.COM_ALTERACAO, alfabetizacao=Aluno.Alfabetizacao.ALFABETIZADO,
            diagnostico=DIAGNOSTICO, tratamento="Tratamento inventado", ano_escolar=Aluno.AnoEscolar.ANO_4,
            escola=cls.escola, criado_por=cls.professor,
        )
        cls.responsavel = Responsavel.objects.create(
            servico=cls.servico, aluno=cls.aluno, nome="Rita Responsável Inventada",
            parentesco=Responsavel.Parentesco.MAE, telefone="(11) 98888-0000", email="rita@exemplo.org",
        )
        cls.aluno_de_fora = criar_aluno(cls.outro_servico, nome="Tomás Inventado de Fora")
        cls.responsavel_de_fora = Responsavel.objects.create(
            servico=cls.outro_servico, aluno=cls.aluno_de_fora, nome="Ivo Responsável de Fora",
            parentesco=Responsavel.Parentesco.PAI,
        )

    def entrar(self, pessoa):
        self.client.force_login(pessoa)

    def eventos(self, **filtro):
        return EventoAuditoria.objects.filter(**filtro)

    def aula(self, aluno, data, professor=None, situacao="registrada"):
        from aulas.models import Aula

        return Aula.objects.create(
            servico=aluno.servico, aluno=aluno, professor=professor or self.professor, data=data, situacao=situacao,
        )

    def mudanca(self, aluno, de, para, data=None, **extra):
        return MudancaDeSituacao.objects.create(
            servico=aluno.servico, aluno=aluno, de=de, para=para, data=data or hoje(),
            motivo=extra.pop("motivo", "Motivo inventado"), **extra,
        )

    def contar_consultas(self, funcao):
        with CaptureQueriesContext(connection) as contexto:
            funcao()
        return len(contexto.captured_queries)

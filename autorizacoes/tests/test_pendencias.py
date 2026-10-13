"""Pendências das autorizações (RF-19, RF-27, RF-64)."""
import datetime

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from aulas.models import Aula
from autorizacoes.pendencias import pendencias_de_autorizacoes
from core.registro import pendencias_para
from core.testes import criar_aluno

from .base import BaseAutorizacoes, Forma, Situacao, Tipo, requisicao


def pendencias(pessoa, usuario=None, todas=False):
    return pendencias_de_autorizacoes(requisicao(pessoa), usuario or pessoa, todas)


class PendenteEProvisoriaTestes(BaseAutorizacoes):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # As duas autorizações colhidas: a pendência de "sem coleta" não entra nestes testes.
        for aluno in (cls.aluno, cls.outro_aluno):
            for tipo in Tipo.values:
                cls.coleta_inicial(aluno, tipo)

    @classmethod
    def coleta_inicial(cls, aluno, tipo):
        from autorizacoes.models import Autorizacao

        Autorizacao.objects.create(
            servico=cls.servico, aluno=aluno, tipo=tipo, situacao=Situacao.VALIDA, forma=Forma.PAPEL,
            colhida_por=cls.professor, colhida_em=timezone.now() - datetime.timedelta(days=30),
        )

    def test_provisoria_vira_pendencia_de_quem_colheu(self):
        provisoria = self.coleta(situacao=Situacao.PROVISORIA, forma=Forma.WHATSAPP, colhida_por=self.professor_b)
        lista = pendencias(self.professor_b)
        self.assertEqual(len(lista), 1)
        p = lista[0]
        self.assertEqual(p.titulo, "Colher o sim definitivo de Lia M. (contato com a escola)")
        self.assertEqual(p.tipo, "Autorização")
        self.assertEqual(p.aluno, "Lia M.")
        self.assertEqual(p.prazo, timezone.localdate(provisoria.colhida_em) + datetime.timedelta(days=7))
        self.assertEqual(p.url, self.url_colher())
        self.assertEqual(p.chave, f"autorizacao-{self.aluno.pk}-contato_escola-{self.professor_b.pk}")
        self.assertEqual(pendencias(self.professor), [])  # não é de quem não colheu

    def test_pendente_vira_pendencia_de_quem_colheu(self):
        self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.PENDENTE, forma="", colhida_por=self.professor)
        lista = pendencias(self.professor)
        self.assertEqual([p.titulo for p in lista], ["Colher a autorização de Lia M. (uso dos dados)"])
        self.assertEqual(lista[0].detalhe, "A família ainda vai decidir.")

    def test_fecha_quando_passa_a_valida_ou_recusada(self):
        self.coleta(situacao=Situacao.PROVISORIA, forma=Forma.WHATSAPP)
        self.assertEqual(len(pendencias(self.professor)), 1)
        self.coleta(situacao=Situacao.VALIDA)
        self.assertEqual(pendencias(self.professor), [])
        self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.PENDENTE, forma="")
        self.assertEqual(len(pendencias(self.professor)), 1)
        self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.RECUSADA)
        self.assertEqual(pendencias(self.professor), [])

    def test_todas_traz_o_servico_inteiro_com_responsavel(self):
        self.coleta(situacao=Situacao.PROVISORIA, forma=Forma.WHATSAPP, colhida_por=self.professor_b)
        self.coleta(aluno=self.outro_aluno, tipo=Tipo.USO_DADOS, situacao=Situacao.PENDENTE, forma="")
        self.coleta(aluno=self.aluno_de_fora, situacao=Situacao.PENDENTE, forma="", termo=self.termo_de_fora,
                    colhida_por=self.de_fora)
        lista = pendencias(self.supervisao, todas=True)
        self.assertEqual(
            sorted((p.aluno, p.responsavel) for p in lista), [("Caio S.", "Paula I."), ("Lia M.", "Bruno I.")]
        )

    def test_aluno_encerrado_nao_gera_pendencia(self):
        self.coleta(situacao=Situacao.PROVISORIA, forma=Forma.WHATSAPP)
        Aluno.objects.filter(pk=self.aluno.pk).update(situacao=Aluno.Situacao.ENCERRADO)
        self.assertEqual(pendencias(self.professor), [])

    def test_so_para_quem_ve_autorizacoes_e_a_identificacao(self):
        self.coleta(situacao=Situacao.PROVISORIA, forma=Forma.WHATSAPP, colhida_por=self.so_aulas)
        self.assertEqual(pendencias(self.so_aulas), [])
        self.assertEqual(pendencias(self.so_aulas, todas=True), [])
        # Na visão de todas, a tarefa de quem não vê as autorizações fica sem responsável.
        lista = pendencias(self.supervisao, todas=True)
        self.assertEqual([p.responsavel for p in lista], ["Sem responsável"])

    def test_aparece_na_tela_inicial(self):
        self.coleta(situacao=Situacao.PROVISORIA, forma=Forma.WHATSAPP)
        self.client.force_login(self.professor)
        resposta = self.client.get(reverse("inicio"))
        self.assertContains(resposta, "Colher o sim definitivo de Lia M. (contato com a escola)")
        titulos = [p.titulo for p in pendencias_para(requisicao(self.professor))]
        self.assertEqual(titulos.count("Colher o sim definitivo de Lia M. (contato com a escola)"), 1)


class SemColetaTestes(BaseAutorizacoes):
    def test_aluno_sem_aula_fica_com_quem_cadastrou(self):
        lista = pendencias(self.professor)
        self.assertEqual([p.titulo for p in lista], ["Colher as autorizações de Lia M."])
        p = lista[0]
        self.assertEqual(p.detalhe, "Faltam as autorizações de uso dos dados e contato com a escola.")
        self.assertEqual(p.url, reverse("alunos:detalhe", args=[self.aluno.pk]) + "#secao-autorizacoes")
        self.assertEqual(p.prazo, timezone.localdate(self.aluno.criado_em) + datetime.timedelta(days=7))
        self.assertEqual(p.chave, f"autorizacao-{self.aluno.pk}-uso_dados-contato_escola-{self.professor.pk}")
        self.assertEqual([p.titulo for p in pendencias(self.professor_b)], ["Colher as autorizações de Caio S."])

    def test_com_aula_registrada_vai_para_o_professor_da_primeira_aula(self):
        hoje = timezone.localdate()
        Aula.objects.create(servico=self.servico, aluno=self.aluno, professor=self.professor_b,
                            data=hoje - datetime.timedelta(days=5), situacao=Aula.Situacao.REGISTRADA)
        Aula.objects.create(servico=self.servico, aluno=self.aluno, professor=self.professor,
                            data=hoje - datetime.timedelta(days=2), situacao=Aula.Situacao.REGISTRADA)
        Aula.objects.create(servico=self.servico, aluno=self.aluno, professor=self.professor,
                            data=hoje - datetime.timedelta(days=9), situacao=Aula.Situacao.MARCADA)
        self.assertEqual(pendencias(self.professor), [])
        lista = pendencias(self.professor_b)
        self.assertIn("Colher as autorizações de Lia M.", [p.titulo for p in lista])
        p = next(p for p in lista if p.aluno == "Lia M.")
        self.assertEqual(p.prazo, hoje - datetime.timedelta(days=5) + datetime.timedelta(days=7))
        self.assertIn("registrada sem as autorizações", p.origem)

    def test_faltando_um_tipo_cita_o_tipo(self):
        self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.RECUSADA)
        lista = pendencias(self.professor)
        self.assertEqual([p.titulo for p in lista], ["Colher a autorização de Lia M. (contato com a escola)"])

    def test_com_as_duas_coletas_some(self):
        self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.RECUSADA)
        self.coleta(tipo=Tipo.CONTATO_ESCOLA, situacao=Situacao.VALIDA)
        self.assertEqual(pendencias(self.professor), [])

    def test_so_aluno_ativo(self):
        Aluno.objects.filter(pk=self.aluno.pk).update(situacao=Aluno.Situacao.PAUSA)
        self.assertEqual(pendencias(self.professor), [])

    def test_todas_com_responsavel_e_sem_outro_servico(self):
        lista = pendencias(self.supervisao, todas=True)
        self.assertEqual(sorted((p.aluno, p.responsavel) for p in lista), [("Caio S.", "Bruno I."), ("Lia M.", "Paula I.")])
        self.assertNotIn("Tomás", " ".join(p.titulo for p in lista))

    def test_quem_so_ve_as_autorizacoes_nao_colhe_mas_ve_as_suas(self):
        criar_aluno(self.servico, nome="Dora Inventada Lima", criado_por=self.apoio)
        self.assertEqual([p.titulo for p in pendencias(self.apoio)], ["Colher as autorizações de Dora L."])

    def test_consultas_nao_crescem_com_os_alunos(self):
        def contar():
            with CaptureQueriesContext(connection) as consultas:
                pendencias(self.supervisao, todas=True)
            return len(consultas)

        def mais_alunos(quantos, inicio):
            for numero in range(inicio, inicio + quantos):
                aluno = criar_aluno(self.servico, nome=f"Aluno Inventado Número{numero}", criado_por=self.professor)
                self.coleta(aluno=aluno, situacao=Situacao.PENDENTE, forma="")

        # Com uma pendência de cada tipo já existente, todas as consultas fixas entram na conta.
        mais_alunos(1, 0)
        antes = contar()
        mais_alunos(15, 1)
        self.assertEqual(contar(), antes)

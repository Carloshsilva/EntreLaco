"""Lista de aulas: filtros, separação entre serviços, permissão e a conta pela regra do serviço (RF-55)."""
import datetime

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from aulas import regras
from aulas.models import Aula
from core.testes import criar_aluno, criar_pessoa

from .base import HOJE, BaseDeAulas


class ListaDeAulasTestes(BaseDeAulas):
    url = reverse("aulas:lista")

    def test_abre_para_quem_ve_aulas(self):
        self.criar_aula(minutos=60)
        for pessoa in (self.professor, self.supervisao, self.leitor):
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                resposta = self.client.get(self.url)
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, "<h1", count=1)

    def test_apoio_administrativo_nao_ve(self):
        self.entrar(self.apoio)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_sem_login_vai_para_entrar(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("entrar"), resposta["Location"])

    def test_pessoa_sem_servico(self):
        self.entrar(criar_pessoa())
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_botoes_so_para_quem_edita(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, reverse("aulas:registrar"))
        self.assertContains(resposta, reverse("aulas:marcar"))
        self.entrar(self.leitor)
        resposta = self.client.get(self.url)
        self.assertNotContains(resposta, reverse("aulas:registrar"))
        self.assertNotContains(resposta, reverse("aulas:marcar"))

    def test_total_de_atendimentos_e_aulas_pela_regra(self):
        self.criar_aula(minutos=60)
        self.criar_aula(minutos=45)
        self.criar_aula(minutos=30, situacao=Aula.Situacao.MARCADA)
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        # 60 minutos contam 2 aulas e 45 contam 1; a marcada ainda não conta.
        self.assertContains(resposta, "2 atendimentos, 3 aulas pela regra de 30 minutos")
        self.assertContains(resposta, "1 aula marcada")
        self.assertContains(resposta, "Conta ao registrar")

    def test_mudar_a_regra_do_servico_muda_a_conta(self):
        self.criar_aula(minutos=60)
        self.criar_aula(minutos=90)
        self.servico.minutos_por_aula = 45
        self.servico.save()
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "2 atendimentos, 3 aulas pela regra de 45 minutos")

    def test_padrao_e_esta_semana_e_as_aulas_de_quem_da_aula(self):
        minha = self.criar_aula()
        do_colega = self.criar_aula(professor=self.outro_professor, aluno=self.aluno_em_pausa)
        antiga = self.criar_aula(data=HOJE() - datetime.timedelta(days=30), aluno=self.aluno_encerrado)
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, reverse("aulas:detalhe", args=[minha.pk]))
        self.assertNotContains(resposta, reverse("aulas:detalhe", args=[do_colega.pk]))
        self.assertNotContains(resposta, reverse("aulas:detalhe", args=[antiga.pk]))
        resposta = self.client.get(self.url, {"professor": "todos"})
        self.assertContains(resposta, reverse("aulas:detalhe", args=[do_colega.pk]))
        inicio = (HOJE() - datetime.timedelta(days=40)).isoformat()
        resposta = self.client.get(self.url, {"de": inicio, "ate": HOJE().isoformat()})
        self.assertContains(resposta, reverse("aulas:detalhe", args=[antiga.pk]))

    def test_quem_nao_da_aula_ve_toda_a_equipe(self):
        aula = self.criar_aula()
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, reverse("aulas:detalhe", args=[aula.pk]))
        self.assertEqual(resposta.context["escolha_professor"], "todos")

    def test_nao_mostra_aulas_de_outro_servico(self):
        de_fora = self.criar_aula(servico=self.outro_servico, aluno=self.aluno_de_fora, professor=self.professor_de_fora)
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url, {"professor": "todos", "aluno": self.aluno_de_fora.pk})
        self.assertNotContains(resposta, reverse("aulas:detalhe", args=[de_fora.pk]))
        self.assertNotContains(resposta, self.aluno_de_fora.nome)
        self.assertNotContains(resposta, self.professor_de_fora.nome)

    def test_filtros_de_aluno_e_situacao(self):
        registrada = self.criar_aula()
        marcada_ontem = self.criar_aula(situacao=Aula.Situacao.MARCADA, data=HOJE() - datetime.timedelta(days=1))
        do_outro_aluno = self.criar_aula(aluno=self.aluno_em_pausa)
        self.entrar(self.professor)
        de = (HOJE() - datetime.timedelta(days=7)).isoformat()
        resposta = self.client.get(self.url, {"aluno": self.aluno.pk, "de": de})
        self.assertContains(resposta, reverse("aulas:detalhe", args=[registrada.pk]))
        self.assertNotContains(resposta, reverse("aulas:detalhe", args=[do_outro_aluno.pk]))
        resposta = self.client.get(self.url, {"situacao": "falta_registrar", "de": de})
        self.assertContains(resposta, reverse("aulas:detalhe", args=[marcada_ontem.pk]))
        self.assertContains(resposta, "Falta registrar")
        self.assertNotContains(resposta, reverse("aulas:detalhe", args=[registrada.pk]))

    def test_tabela_com_cabecalho_e_rotulos_para_o_celular(self):
        self.criar_aula()
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, '<th scope="col">Aluno</th>', html=False)
        self.assertContains(resposta, 'data-label="Situação"')
        # Nome do aluno abreviado na lista.
        self.assertContains(resposta, "Lia I.")
        self.assertNotContains(resposta, ">Lia Martins Inventada</a>")

    def test_htmx_devolve_so_os_resultados(self):
        self.criar_aula()
        self.entrar(self.professor)
        resposta = self.client.get(self.url, headers={"HX-Request": "true", "HX-Target": "resultados"})
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "<html")
        self.assertContains(resposta, "1 atendimento, 1 aula pela regra de 30 minutos")
        # Navegação com hx-boost recebe a página inteira.
        resposta = self.client.get(self.url, headers={"HX-Request": "true", "HX-Boosted": "true"})
        self.assertContains(resposta, "<html")

    def test_consultas_nao_crescem_com_o_numero_de_aulas(self):
        self.entrar(self.professor)
        for _ in range(3):
            self.criar_aula()
        with CaptureQueriesContext(connection) as poucas:
            self.client.get(self.url)
        for numero in range(25):
            aluno = criar_aluno(self.servico, nome=f"Aluno Fictício Número {numero}")
            self.criar_aula(aluno=aluno, minutos=60)
        with CaptureQueriesContext(connection) as muitas:
            resposta = self.client.get(self.url)
        self.assertContains(resposta, "28 atendimentos")
        self.assertEqual(len(poucas), len(muitas))


class RegraDeEquivalenciaTestes(BaseDeAulas):
    """RF-55: na Escola Móvel, 30 minutos de atendimento contam 1 aula."""

    def test_sessenta_minutos_contam_duas_e_quarenta_e_cinco_contam_uma(self):
        self.assertEqual(regras.aulas_equivalentes(60, 30), 2)
        self.assertEqual(regras.aulas_equivalentes(45, 30), 1)
        self.assertEqual(regras.aulas_equivalentes(20, 30), 0)
        self.assertEqual(self.criar_aula(minutos=60).aulas_equivalentes(), 2)
        self.assertEqual(self.criar_aula(minutos=45).aulas_equivalentes(), 1)

    def test_aula_que_nao_foi_registrada_nao_conta(self):
        self.assertEqual(self.criar_aula(minutos=60, situacao=Aula.Situacao.MARCADA).aulas_equivalentes(), 0)
        self.assertEqual(self.criar_aula(minutos=60, situacao=Aula.Situacao.NAO_REALIZADA).aulas_equivalentes(), 0)

    def test_a_regra_vem_do_servico(self):
        self.servico.minutos_por_aula = 50
        self.servico.save()
        aula = Aula.objects.get(pk=self.criar_aula(minutos=100).pk)
        self.assertEqual(aula.aulas_equivalentes(), 2)
        self.assertEqual(regras.resumo_de_atendimentos(1, 1, 50), "1 atendimento, 1 aula pela regra de 50 minutos")

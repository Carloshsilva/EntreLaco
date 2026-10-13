"""Agenda, pendência de aula sem registro e seção do perfil do aluno (RF-09, RF-43, RF-44, RF-55)."""
import datetime
from unittest import mock

from django.template.loader import render_to_string
from django.urls import reverse

from aulas.encaixes import eventos_de_aulas, pendencias_de_aulas, secao_aulas_do_aluno
from aulas.models import Aula
from core.registro import eventos_da_agenda, secoes_do_aluno

from .base import HOJE, BaseDeAulas

UM_DIA = datetime.timedelta(days=1)


class AgendaTestes(BaseDeAulas):
    def setUp(self):
        super().setUp()
        self.marcada = self.criar_aula(situacao=Aula.Situacao.MARCADA, data=HOJE() + UM_DIA)
        self.registrada = self.criar_aula(minutos=60)
        self.registrada.componentes.add(self.componente)
        self.nao_realizada = self.criar_aula(situacao=Aula.Situacao.NAO_REALIZADA, motivo_nao_realizada="Exame")
        self.do_colega = self.criar_aula(professor=self.outro_professor, aluno=self.aluno_em_pausa)
        self.de_fora = self.criar_aula(servico=self.outro_servico, aluno=self.aluno_de_fora, professor=self.professor_de_fora)
        self.inicio, self.fim = HOJE() - UM_DIA * 3, HOJE() + UM_DIA * 3

    def test_calendario_do_professor(self):
        eventos = eventos_de_aulas(self.requisicao(self.professor), self.inicio, self.fim, self.professor)
        self.assertEqual(len(eventos), 3)
        por_situacao = {e.situacao: e for e in eventos}
        self.assertEqual(set(por_situacao), {"Marcada", "Registrada", "Não aconteceu"})
        marcada = por_situacao["Marcada"]
        self.assertEqual(marcada.titulo, "Aula com Lia I.")
        self.assertEqual(marcada.url, reverse("aulas:registrar_marcada", args=[self.marcada.pk]))
        self.assertEqual(marcada.tipo, "aula")
        self.assertFalse(marcada.cancelado)
        self.assertEqual(por_situacao["Registrada"].detalhe, "Matemática")
        self.assertEqual(por_situacao["Registrada"].url, reverse("aulas:detalhe", args=[self.registrada.pk]))
        self.assertTrue(por_situacao["Não aconteceu"].cancelado)

    def test_servico_todo_sem_outro_servico(self):
        eventos = eventos_de_aulas(self.requisicao(self.supervisao), self.inicio, self.fim, None)
        self.assertEqual(len(eventos), 4)
        self.assertNotIn(f"/aulas/{self.de_fora.pk}/", " ".join(e.url for e in eventos))

    def test_quem_so_ve_vai_para_o_detalhe(self):
        eventos = eventos_de_aulas(self.requisicao(self.leitor), self.inicio, self.fim, self.professor)
        marcada = next(e for e in eventos if e.situacao == "Marcada")
        self.assertEqual(marcada.url, reverse("aulas:detalhe", args=[self.marcada.pk]))

    def test_apoio_administrativo_nao_ve_aulas_na_agenda(self):
        self.assertEqual(eventos_de_aulas(self.requisicao(self.apoio), self.inicio, self.fim, None), [])
        self.assertEqual(eventos_da_agenda(self.requisicao(self.apoio), self.inicio, self.fim, None), [])

    def test_consultas_fixas_na_agenda(self):
        request = self.requisicao(self.supervisao)
        with self.assertNumQueries(2):
            eventos_de_aulas(request, self.inicio, self.fim, None)


class PendenciaDeAulaSemRegistroTestes(BaseDeAulas):
    def test_nasce_no_dia_seguinte_para_o_professor_da_aula(self):
        aula = self.criar_aula(situacao=Aula.Situacao.MARCADA, data=HOJE(), hora=datetime.time(8, 0))
        request = self.requisicao(self.professor)
        self.assertEqual(pendencias_de_aulas(request, self.professor, False), [])
        with mock.patch("aulas.regras.hoje", return_value=HOJE() + UM_DIA):
            pendencias = pendencias_de_aulas(request, self.professor, False)
        self.assertEqual(len(pendencias), 1)
        pendencia = pendencias[0]
        self.assertEqual(pendencia.titulo, f"Registrar a aula de Lia I. de {HOJE():%d/%m}")
        self.assertEqual(pendencia.tipo, "Aula sem registro")
        self.assertEqual(pendencia.prazo, HOJE() + UM_DIA)
        self.assertEqual(pendencia.url, reverse("aulas:registrar_marcada", args=[aula.pk]))
        self.assertEqual(pendencia.chave, f"aula-{aula.pk}")
        self.assertEqual(pendencia.responsavel, "")

    def test_so_do_professor_da_aula_e_todas_com_responsavel(self):
        aula = self.criar_aula(situacao=Aula.Situacao.MARCADA, data=HOJE() - UM_DIA)
        self.criar_aula(
            servico=self.outro_servico, aluno=self.aluno_de_fora, professor=self.professor_de_fora,
            situacao=Aula.Situacao.MARCADA, data=HOJE() - UM_DIA,
        )
        self.assertEqual(pendencias_de_aulas(self.requisicao(self.outro_professor), self.outro_professor, False), [])
        todas = pendencias_de_aulas(self.requisicao(self.supervisao), self.supervisao, True)
        self.assertEqual([p.chave for p in todas], [f"aula-{aula.pk}"])
        self.assertEqual(todas[0].responsavel, "Ana I.")

    def test_registrada_ou_nao_realizada_nao_e_pendencia(self):
        self.criar_aula(data=HOJE() - UM_DIA)
        self.criar_aula(situacao=Aula.Situacao.NAO_REALIZADA, data=HOJE() - UM_DIA)
        self.assertEqual(pendencias_de_aulas(self.requisicao(self.professor), self.professor, False), [])

    def test_apoio_administrativo_nao_recebe(self):
        self.criar_aula(situacao=Aula.Situacao.MARCADA, data=HOJE() - UM_DIA, professor=self.apoio)
        self.assertEqual(pendencias_de_aulas(self.requisicao(self.apoio), self.apoio, False), [])

    def test_aparece_na_tela_inicial(self):
        self.criar_aula(situacao=Aula.Situacao.MARCADA, data=HOJE() - UM_DIA)
        self.entrar(self.professor)
        resposta = self.client.get(reverse("inicio"))
        self.assertContains(resposta, f"Registrar a aula de Lia I. de {(HOJE() - UM_DIA):%d/%m}")


class SecaoDoAlunoTestes(BaseDeAulas):
    def setUp(self):
        super().setUp()
        self.criar_aula(minutos=60, conteudo="Leitura de um livro inventado.")
        self.criar_aula(minutos=45, data=HOJE() - UM_DIA)
        self.criar_aula(situacao=Aula.Situacao.MARCADA, data=HOJE() + UM_DIA)

    def test_totais_proximas_e_ultimas(self):
        dados = secao_aulas_do_aluno(self.requisicao(self.professor), self.aluno)
        self.assertEqual(dados["registradas"], 2)
        self.assertEqual(dados["equivalentes"], 3)
        self.assertEqual(dados["resumo"], "2 atendimentos, 3 aulas pela regra de 30 minutos")
        self.assertEqual(len(dados["proximas"]), 1)
        self.assertEqual(len(dados["ultimas"]), 2)
        self.assertTrue(dados["pode_registrar"])
        self.assertEqual(dados["url_registrar"], f"{reverse('aulas:registrar')}?aluno={self.aluno.pk}")

    def test_template_da_secao(self):
        request = self.requisicao(self.professor)
        dados = secao_aulas_do_aluno(request, self.aluno)
        html = render_to_string("aulas/_secao_aluno.html", {
            "dados": dados, "aluno": self.aluno, "acesso": request.acesso, "request": request,
        })
        self.assertIn("2 atendimentos, 3 aulas pela regra de 30 minutos", html)
        self.assertIn(f"?aluno={self.aluno.pk}", html)
        self.assertIn("Leitura de um livro inventado.", html)
        self.assertIn('data-label="Componentes"', html)
        self.assertNotIn("<h2", html)
        self.assertNotIn("<h1", html)

    def test_quem_so_ve_nao_recebe_os_botoes(self):
        dados = secao_aulas_do_aluno(self.requisicao(self.leitor), self.aluno)
        self.assertFalse(dados["pode_registrar"])

    def test_aluno_de_outro_servico_nao_tem_secao(self):
        self.assertIsNone(secao_aulas_do_aluno(self.requisicao(self.professor), self.aluno_de_fora))

    def test_apoio_administrativo_nao_ve_a_secao(self):
        chaves = [s["chave"] for s in secoes_do_aluno(self.requisicao(self.apoio), self.aluno)]
        self.assertNotIn("aulas", chaves)
        chaves = [s["chave"] for s in secoes_do_aluno(self.requisicao(self.professor), self.aluno)]
        self.assertIn("aulas", chaves)

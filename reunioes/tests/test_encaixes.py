"""Encaixes das reuniões: agenda (RF-44), pendências e seção do perfil do aluno (RF-17)."""
import datetime

from django.db import connection
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.registro import eventos_da_agenda, pendencias_para, secoes_do_aluno
from reunioes.encaixes import eventos_de_reuniao, pendencias_de_encaminhamento, secao_citacoes_do_aluno
from reunioes.models import Reuniao

from .base import BaseReunioes, requisicao


class AgendaTestes(BaseReunioes):
    def periodo(self):
        return self.hoje - datetime.timedelta(days=10), self.hoje + datetime.timedelta(days=10)

    def test_reuniao_aparece_na_agenda_de_quem_participa(self):
        inicio, fim = self.periodo()
        eventos = eventos_de_reuniao(requisicao(self.professor), inicio, fim, self.professor)
        self.assertEqual([e.titulo for e in eventos], ["Reunião semanal da equipe"])
        evento = eventos[0]
        self.assertEqual(evento.tipo, "reuniao")
        self.assertEqual(evento.hora, datetime.time(14, 0))
        self.assertEqual(evento.duracao_minutos, 60)
        self.assertEqual(evento.situacao, "Marcada")
        self.assertFalse(evento.cancelado)
        self.assertEqual(evento.pessoas, ["Paula I.", "Sara I."])
        self.assertEqual(evento.url, reverse("reunioes:detalhe", args=[self.reuniao.pk]))
        self.assertEqual(evento.detalhe, "Local: Sala da equipe inventada")

    def test_quem_nao_participa_nao_ve_na_propria_agenda(self):
        inicio, fim = self.periodo()
        self.assertEqual(eventos_de_reuniao(requisicao(self.professor_dois), inicio, fim, self.professor_dois), [])

    def test_agenda_de_todos_traz_as_reunioes_do_servico(self):
        inicio, fim = self.periodo()
        titulos = {e.titulo for e in eventos_de_reuniao(requisicao(self.supervisao), inicio, fim, None)}
        self.assertEqual(titulos, {"Reunião semanal da equipe", "Reunião multidisciplinar de outubro"})

    def test_quem_nao_ve_as_atas_nao_ve_reunioes_na_agenda(self):
        inicio, fim = self.periodo()
        self.assertEqual(eventos_de_reuniao(requisicao(self.apoio), inicio, fim, None), [])

    def test_cancelada_vem_marcada(self):
        Reuniao.objects.filter(pk=self.reuniao.pk).update(situacao=Reuniao.Situacao.CANCELADA)
        inicio, fim = self.periodo()
        evento = eventos_de_reuniao(requisicao(self.professor), inicio, fim, self.professor)[0]
        self.assertTrue(evento.cancelado)
        self.assertEqual(evento.situacao, "Cancelada")

    def test_tela_da_agenda_mostra_a_reuniao(self):
        self.entrar(self.professor)
        resposta = self.client.get(reverse("agenda"), {"semana": self.reuniao.data.isoformat()})
        self.assertContains(resposta, "Reunião semanal da equipe")
        self.assertContains(resposta, "el-event-reuniao")

    def test_fonte_registrada_no_nucleo(self):
        inicio, fim = self.periodo()
        eventos = eventos_da_agenda(requisicao(self.professor), inicio, fim, usuario=self.professor)
        self.assertIn("Reunião semanal da equipe", [e.titulo for e in eventos])


class PendenciasTestes(BaseReunioes):
    def test_encaminhamento_vira_pendencia_do_responsavel(self):
        citacao = self.citar(
            encaminhamento="Levar gibis inventados na quinta-feira para a aluna ler durante a semana toda no leito.",
            responsavel=self.professor, prazo=self.hoje + datetime.timedelta(days=3),
        )
        pendencias = pendencias_de_encaminhamento(requisicao(self.professor), self.professor, False)
        self.assertEqual(len(pendencias), 1)
        pendencia = pendencias[0]
        self.assertTrue(pendencia.titulo.startswith("Encaminhamento de Lia M.: Levar gibis inventados"))
        self.assertTrue(pendencia.titulo.endswith("…"))
        self.assertEqual(pendencia.tipo, "Encaminhamento de reunião")
        self.assertEqual(pendencia.prazo, citacao.prazo)
        self.assertEqual(pendencia.aluno, "Lia M.")
        self.assertEqual(pendencia.origem, f"Reunião semanal da equipe de {self.reuniao.data:%d/%m}")
        self.assertEqual(pendencia.url, reverse("reunioes:detalhe", args=[self.reuniao.pk]) + f"#citacao-{citacao.pk}")
        self.assertEqual(pendencia.chave, f"citacao-{citacao.pk}")
        self.assertEqual(pendencia.responsavel, "")

    def test_origem_sem_repetir_a_palavra_reuniao(self):
        self.citar(reuniao=self.reuniao_passada, encaminhamento="Levar gibis.", responsavel=self.professor)
        self.reuniao_passada.titulo = "Multidisciplinar de outubro"
        self.reuniao_passada.save()
        pendencia = pendencias_de_encaminhamento(requisicao(self.professor), self.professor, False)[0]
        self.assertEqual(pendencia.origem, f"Reunião Multidisciplinar de outubro de {self.reuniao_passada.data:%d/%m}")

    def test_so_do_responsavel_e_so_o_que_nao_foi_concluido(self):
        self.citar(encaminhamento="Levar gibis.", responsavel=self.professor, concluida=True)
        self.citar(encaminhamento="Sem dono por enquanto.")
        self.citar(encaminhamento="Ligar para a escola.", responsavel=self.professor_dois)
        self.assertEqual(pendencias_de_encaminhamento(requisicao(self.professor), self.professor, False), [])

    def test_todas_traz_as_do_servico_com_o_responsavel(self):
        self.citar(encaminhamento="Levar gibis.", responsavel=self.professor)
        self.citar(aluno=self.aluno_dois, encaminhamento="Ligar para a escola.", responsavel=self.professor_dois)
        self.citar(reuniao=self.reuniao_de_fora, aluno=self.aluno_de_fora, encaminhamento="De fora.",
                   responsavel=self.de_fora)
        pendencias = pendencias_de_encaminhamento(requisicao(self.supervisao), self.supervisao, True)
        self.assertEqual(sorted(p.responsavel for p in pendencias), ["Paula I.", "Tiago F."])

    def test_citacao_de_saude_nao_vira_pendencia_para_quem_nao_ve_saude(self):
        # O formulário não deixa, mas o dado pode ter vindo de antes de o papel mudar.
        self.citar(grupo="sensivel", encaminhamento="Conversar com a família.", responsavel=self.secretaria)
        self.assertEqual(pendencias_de_encaminhamento(requisicao(self.secretaria), self.secretaria, False), [])
        self.assertEqual(pendencias_de_encaminhamento(requisicao(self.secretaria), self.secretaria, True), [])
        self.assertEqual(len(pendencias_de_encaminhamento(requisicao(self.supervisao), self.supervisao, True)), 1)

    def test_quem_nao_ve_as_atas_nao_recebe(self):
        self.citar(encaminhamento="Levar gibis.", responsavel=self.apoio)
        self.assertEqual(pendencias_de_encaminhamento(requisicao(self.apoio), self.apoio, False), [])

    def test_pendencia_aparece_na_tela_inicial(self):
        self.citar(encaminhamento="Levar gibis.", responsavel=self.professor)
        self.entrar(self.professor)
        resposta = self.client.get(reverse("inicio"))
        self.assertContains(resposta, "Encaminhamento de Lia M.: Levar gibis.")
        self.assertContains(resposta, "Encaminhamento de reunião")
        chaves = [p.chave for p in pendencias_para(requisicao(self.professor))]
        self.assertEqual(len(chaves), len(set(chaves)))


class SecaoDoPerfilTestes(BaseReunioes):
    def secao(self, pessoa, aluno=None):
        request = requisicao(pessoa, f"/alunos/{(aluno or self.aluno).pk}/")
        dados = secao_citacoes_do_aluno(request, aluno or self.aluno)
        html = render_to_string(
            "reunioes/_secao_aluno.html",
            {"dados": dados, "aluno": aluno or self.aluno, "acesso": request.acesso, "user": pessoa},
            request=request,
        )
        return dados, html

    def test_secao_registrada_para_quem_ve_as_atas(self):
        chaves = [s["chave"] for s in secoes_do_aluno(requisicao(self.professor), self.aluno)]
        self.assertIn("citacoes", chaves)
        chaves = [s["chave"] for s in secoes_do_aluno(requisicao(self.apoio), self.aluno)]
        self.assertNotIn("citacoes", chaves)

    def test_mostra_reuniao_encaminhamento_responsavel_e_situacao(self):
        self.citar(
            reuniao=self.reuniao_passada, encaminhamento="Levar gibis.", responsavel=self.professor,
            prazo=self.hoje - datetime.timedelta(days=1),
        )
        dados, html = self.secao(self.professor)
        self.assertEqual(len(dados["citacoes"]), 1)
        self.assertIn("Reunião multidisciplinar de outubro", html)
        self.assertIn(self.reuniao_passada.data.strftime("%d/%m/%Y"), html)
        self.assertIn("Levar gibis.", html)
        self.assertIn("Paula I. (você)", html)
        self.assertIn("Prazo vencido", html)
        self.assertIn(reverse("reunioes:citacao_concluir", args=[dados["citacoes"][0].pk]), html)
        self.assertIn('name="proximo"', html)

    def test_citacao_de_saude_some_do_perfil_para_quem_nao_ve_saude(self):
        self.citar(grupo="sensivel", texto="Fala de saúde inventada no perfil.")
        self.citar(texto="Fala sobre leitura no perfil.")
        dados, html = self.secao(self.secretaria)
        self.assertNotIn("Fala de saúde inventada", html)
        self.assertIn("Fala sobre leitura no perfil.", html)
        dados, html = self.secao(self.supervisao)
        self.assertIn("Fala de saúde inventada no perfil.", html)

    def test_so_as_citacoes_deste_aluno(self):
        self.citar(aluno=self.aluno_dois, texto="Fala sobre outro aluno.")
        dados, html = self.secao(self.professor)
        self.assertEqual(dados["citacoes"], [])
        self.assertIn("Nenhuma citação em reunião até agora.", html)

    def test_botao_citar_so_para_quem_edita_as_atas(self):
        _, html = self.secao(self.secretaria)
        self.assertIn("Citar em uma reunião", html)
        self.assertIn(f"{reverse('reunioes:lista')}?aluno={self.aluno.pk}", html)
        _, html = self.secao(self.professor)
        self.assertNotIn("Citar em uma reunião", html)

    def test_consultas_da_secao_nao_crescem_com_o_numero_de_citacoes(self):
        self.citar(encaminhamento="Levar gibis.", responsavel=self.professor)
        with CaptureQueriesContext(connection) as poucas:
            self.secao(self.professor)
        for numero in range(10):
            self.citar(reuniao=self.reuniao_passada, texto=f"Fala {numero}.", encaminhamento="Ligar.",
                       responsavel=self.professor_dois)
        with CaptureQueriesContext(connection) as muitas:
            self.secao(self.professor)
        self.assertEqual(len(poucas), len(muitas))

    def test_titulo_da_secao_fica_com_o_perfil(self):
        self.citar()
        _, html = self.secao(self.professor)
        self.assertNotIn("<h2", html)
        self.assertIn("<h3", html)

    def test_perfil_do_aluno_mostra_a_secao_so_com_o_que_a_pessoa_ve(self):
        self.citar(reuniao=self.reuniao_passada, texto="Fala sobre leitura no perfil.")
        self.citar(reuniao=self.reuniao_passada, grupo="sensivel", texto="Fala de saúde inventada no perfil.")
        url = reverse("alunos:detalhe", args=[self.aluno.pk])
        self.entrar(self.supervisao)
        resposta = self.client.get(url)
        self.assertContains(resposta, 'id="secao-citacoes"')
        self.assertContains(resposta, "Citações em reuniões")
        self.assertContains(resposta, "Fala de saúde inventada no perfil.")
        self.entrar(self.secretaria)
        resposta = self.client.get(url)
        self.assertContains(resposta, "Fala sobre leitura no perfil.")
        self.assertNotContains(resposta, "Fala de saúde inventada")
        self.entrar(self.apoio)
        self.assertNotContains(self.client.get(url), 'id="secao-citacoes"')

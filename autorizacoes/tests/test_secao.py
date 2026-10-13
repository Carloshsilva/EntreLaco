"""Seção "Autorizações da família" no perfil do aluno (RF-25, RF-28, RF-64)."""
from django.template.loader import render_to_string
from django.urls import reverse

from autorizacoes.secoes import contexto_das_autorizacoes
from core.registro import secoes_do_aluno

from .base import BaseAutorizacoes, Forma, Situacao, Tipo, requisicao


class SecaoTestes(BaseAutorizacoes):
    def desenhar(self, pessoa):
        request = requisicao(pessoa)
        dados = contexto_das_autorizacoes(request, self.aluno)
        html = render_to_string(
            "autorizacoes/_secao_aluno.html",
            {"dados": dados, "aluno": self.aluno, "acesso": request.acesso, "request": request},
        )
        return dados, html

    def test_registrada_no_perfil_so_para_quem_ve(self):
        secoes = [s["chave"] for s in secoes_do_aluno(requisicao(self.professor), self.aluno)]
        self.assertIn("autorizacoes", secoes)
        secoes = [s["chave"] for s in secoes_do_aluno(requisicao(self.apoio), self.aluno)]
        self.assertIn("autorizacoes", secoes)
        secoes = [s["chave"] for s in secoes_do_aluno(requisicao(self.so_aulas), self.aluno)]
        self.assertNotIn("autorizacoes", secoes)

    def test_aluno_de_outro_servico_nao_tem_secao(self):
        self.assertIsNone(contexto_das_autorizacoes(requisicao(self.professor), self.aluno_de_fora))

    def test_sem_coleta_mostra_ainda_nao_colhida_e_colher(self):
        dados, html = self.desenhar(self.professor)
        self.assertEqual(html.count("Ainda não colhida"), 2)
        self.assertIn(self.url_colher(tipo=Tipo.USO_DADOS), html)
        self.assertIn(self.url_colher(tipo=Tipo.CONTATO_ESCOLA), html)
        self.assertIn("nada sai para a escola", html)
        self.assertIn("Contato com a escola não liberado", html)
        self.assertFalse(dados["libera_contato"])

    def test_selo_e_acoes_de_cada_situacao(self):
        provisoria = self.coleta(situacao=Situacao.PROVISORIA, forma=Forma.WHATSAPP)
        valida = self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.VALIDA)
        dados, html = self.desenhar(self.professor)
        self.assertIn('<span class="el-badge el-badge-fita">Provisória</span>', html)
        self.assertIn('<span class="el-badge el-badge-success">Válida</span>', html)
        self.assertIn("Colher o sim definitivo", html)
        self.assertIn(reverse("autorizacoes:revogar", args=[provisoria.pk]), html)
        self.assertIn(reverse("autorizacoes:revogar", args=[valida.pk]), html)
        self.assertNotIn(self.url_colher(tipo=Tipo.USO_DADOS), html)  # válida não se colhe de novo
        self.assertIn(reverse("autorizacoes:detalhe", args=[valida.pk]), html)
        self.assertIn("Contato com a escola liberado pelo sim provisório", html)
        self.assertIn("Sim por WhatsApp", html)
        self.assertIn("Paula I.", html)  # nome_curto: primeiro nome e inicial do último
        self.assertTrue(dados["libera_contato"])

    def test_recusada_e_revogada_em_vermelho_com_palavra_e_colher(self):
        self.coleta(situacao=Situacao.RECUSADA)
        self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.REVOGADA)
        _, html = self.desenhar(self.professor)
        self.assertIn('<span class="el-badge el-badge-danger">Recusada</span>', html)
        self.assertIn('<span class="el-badge el-badge-danger">Revogada</span>', html)
        self.assertIn(self.url_colher(tipo=Tipo.USO_DADOS), html)
        self.assertIn(self.url_colher(tipo=Tipo.CONTATO_ESCOLA), html)

    def test_pendente_tem_selo_fita_e_colher(self):
        self.coleta(situacao=Situacao.PENDENTE, forma="")
        _, html = self.desenhar(self.professor)
        self.assertIn('<span class="el-badge el-badge-fita">Pendente</span>', html)
        self.assertIn("a família vai decidir depois", html)

    def test_quem_so_ve_nao_recebe_botoes_de_editar(self):
        valida = self.coleta()
        _, html = self.desenhar(self.apoio)
        self.assertNotIn(reverse("autorizacoes:revogar", args=[valida.pk]), html)
        self.assertNotIn(self.url_colher(tipo=Tipo.USO_DADOS), html)
        self.assertIn(reverse("autorizacoes:detalhe", args=[valida.pk]), html)

    def test_coletas_anteriores_ficam_como_prova(self):
        antiga = self.coleta(situacao=Situacao.RECUSADA)
        self.coleta(situacao=Situacao.VALIDA)
        _, html = self.desenhar(self.professor)
        self.assertIn("1 coleta anterior, guardada como prova", html)
        self.assertIn(reverse("autorizacoes:detalhe", args=[antiga.pk]), html)

    def test_uma_consulta_para_as_coletas(self):
        for _ in range(3):
            self.coleta(situacao=Situacao.RECUSADA)
            self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.RECUSADA)
        request = requisicao(self.professor)
        with self.assertNumQueries(1):
            contexto_das_autorizacoes(request, self.aluno)

    def test_no_perfil_do_aluno(self):
        self.coleta()
        self.client.force_login(self.professor)
        resposta = self.client.get(reverse("alunos:detalhe", args=[self.aluno.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'id="secao-autorizacoes"')
        self.assertContains(resposta, "Autorizações da família")
        self.assertContains(resposta, "Registrar revogação")

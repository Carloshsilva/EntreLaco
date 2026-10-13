"""Revogação a pedido da família (RF-29, LGPD-04)."""
from django.urls import reverse

from autorizacoes.models import autorizacao_atual
from autorizacoes.regras import libera_contato_com_a_escola

from .base import Acao, BaseAutorizacoes, Forma, Situacao, Tipo

DADOS = {"revogacao_motivo": "A mãe pediu por telefone hoje, às 10h.", "confirmar": "on"}


class RevogarTestes(BaseAutorizacoes):
    def url(self, autorizacao):
        return reverse("autorizacoes:revogar", args=[autorizacao.pk])

    def test_abre_para_quem_edita(self):
        autorizacao = self.coleta()
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url(autorizacao))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "<h1", count=1)
        self.assertContains(resposta, "nada mais é enviado à escola")
        self.assertContains(resposta, "Como a família pediu a revogação")

    def test_403_para_quem_so_ve(self):
        autorizacao = self.coleta()
        for pessoa in (self.apoio, self.so_aulas):
            self.client.force_login(pessoa)
            self.assertEqual(self.client.get(self.url(autorizacao)).status_code, 403)
            self.assertEqual(self.client.post(self.url(autorizacao), DADOS).status_code, 403)
        autorizacao.refresh_from_db()
        self.assertEqual(autorizacao.situacao, Situacao.VALIDA)

    def test_404_para_outro_servico(self):
        de_fora = self.coleta(aluno=self.aluno_de_fora, termo=self.termo_de_fora, colhida_por=self.de_fora)
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(self.url(de_fora)).status_code, 404)
        self.assertEqual(self.client.post(self.url(de_fora), DADOS).status_code, 404)

    def test_revogar_muda_a_situacao_atual_e_bloqueia_o_contato(self):
        autorizacao = self.coleta()
        self.assertTrue(libera_contato_com_a_escola(self.aluno))
        self.client.force_login(self.professor)
        resposta = self.client.post(self.url(autorizacao), DADOS)
        self.assertRedirects(
            resposta, reverse("alunos:detalhe", args=[self.aluno.pk]) + "#secao-autorizacoes",
            fetch_redirect_response=False,
        )
        autorizacao.refresh_from_db()
        self.assertEqual(autorizacao.situacao, Situacao.REVOGADA)
        self.assertIsNotNone(autorizacao.revogada_em)
        self.assertEqual(autorizacao.revogacao_motivo, "A mãe pediu por telefone hoje, às 10h.")
        self.assertEqual(autorizacao_atual(self.aluno, Tipo.CONTATO_ESCOLA).situacao, Situacao.REVOGADA)
        self.assertFalse(libera_contato_com_a_escola(self.aluno))
        evento = self.eventos(autorizacao, Acao.ALTEROU).get()
        self.assertEqual(evento.usuario, self.professor)
        self.assertEqual(evento.motivo, "A mãe pediu por telefone hoje, às 10h.")
        self.assertEqual(evento.mudancas["situacao"]["para"], "Revogada")
        self.assertContains(
            self.client.get(resposta["Location"]),
            "Revogação registrada. A partir de agora nada mais é enviado à escola sobre este aluno.",
        )

    def test_sim_provisorio_tambem_se_revoga(self):
        autorizacao = self.coleta(situacao=Situacao.PROVISORIA, forma=Forma.WHATSAPP)
        self.client.force_login(self.professor)
        self.client.post(self.url(autorizacao), DADOS)
        autorizacao.refresh_from_db()
        self.assertEqual(autorizacao.situacao, Situacao.REVOGADA)
        self.assertFalse(libera_contato_com_a_escola(self.aluno))

    def test_motivo_e_confirmacao_sao_obrigatorios(self):
        autorizacao = self.coleta()
        self.client.force_login(self.professor)
        resposta = self.client.post(self.url(autorizacao), {"revogacao_motivo": "", "confirmar": ""})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Conte como a família pediu a revogação")
        self.assertContains(resposta, "Marque a confirmação para registrar a revogação.")
        autorizacao.refresh_from_db()
        self.assertEqual(autorizacao.situacao, Situacao.VALIDA)
        self.assertFalse(self.eventos(autorizacao, Acao.ALTEROU).exists())

    def test_so_a_atual_valida_ou_provisoria_se_revoga(self):
        pendente = self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.PENDENTE, forma="")
        antiga = self.coleta()
        self.coleta(situacao=Situacao.RECUSADA)  # a atual de contato agora é a recusa
        self.client.force_login(self.professor)
        for autorizacao in (pendente, antiga):
            resposta = self.client.post(self.url(autorizacao), DADOS)
            self.assertRedirects(
                resposta, reverse("autorizacoes:detalhe", args=[autorizacao.pk]), fetch_redirect_response=False
            )
        pendente.refresh_from_db()
        antiga.refresh_from_db()
        self.assertEqual(pendente.situacao, Situacao.PENDENTE)
        self.assertEqual(antiga.situacao, Situacao.VALIDA)

    def test_revogar_uso_dos_dados_nao_mexe_no_contato(self):
        uso = self.coleta(tipo=Tipo.USO_DADOS)
        self.coleta(tipo=Tipo.CONTATO_ESCOLA)
        self.client.force_login(self.professor)
        self.client.post(self.url(uso), DADOS)
        uso.refresh_from_db()
        self.assertEqual(uso.situacao, Situacao.REVOGADA)
        self.assertTrue(libera_contato_com_a_escola(self.aluno))

"""Trilha de auditoria: quem só vê a trilha não lê o nome de aluno que o papel dela não vê (RF-07)."""
from django.test import TestCase
from django.urls import reverse

from core import auditoria
from core.testes import criar_aluno, criar_papel, criar_pessoa, criar_servico


class NomeDoAlunoNaTrilhaTestes(TestCase):
    def setUp(self):
        self.servico = criar_servico()
        auditor = criar_papel(self.servico, "Auditoria inventada", acoes=["ver_trilha"])
        self.auditoria = criar_pessoa(self.servico, auditor, nome="Ada Auditora Inventada")
        secretaria = criar_papel(self.servico, "Secretaria inventada", ver=["identificacao"], acoes=["ver_trilha"])
        self.secretaria = criar_pessoa(self.servico, secretaria, nome="Sara Secretaria Inventada")
        aluno = criar_aluno(self.servico, nome="Lia Inventada Sigilosa")
        auditoria.registrar(None, auditoria.Acao.CRIOU, aluno, servico=self.servico)

    def test_quem_nao_ve_a_identificacao_nao_le_o_nome(self):
        self.client.force_login(self.auditoria)
        resposta = self.client.get(reverse("trilha"))
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "Lia Inventada Sigilosa")

    def test_quem_ve_a_identificacao_le_o_nome(self):
        self.client.force_login(self.secretaria)
        self.assertContains(self.client.get(reverse("trilha")), "Lia Inventada Sigilosa")

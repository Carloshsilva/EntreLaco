"""Ordem de atendimento (RF-46): critério simples e visível, sem consulta por aluno."""
from django.urls import reverse

from alunos.models import Aluno
from core.testes import criar_aluno, criar_papel, criar_pessoa

from .base import BaseAlunos, Situacao, dias_atras


class FilaTestes(BaseAlunos):
    url = reverse("alunos:fila")

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # A aluna da base sai da fila: aqui só entram os alunos abaixo.
        Aluno.objects.filter(pk=cls.aluno.pk).update(situacao=Situacao.PAUSA)
        unidade = "Pediatria Fictícia"
        cls.nunca = criar_aluno(cls.servico, nome="Ana Nunca Teve", unidade=unidade, data_internacao=dias_atras(3))
        cls.dez_sem_risco = criar_aluno(cls.servico, nome="Beto Dez Dias", unidade=unidade,
                                        data_internacao=dias_atras(5))
        cls.dez_com_risco = criar_aluno(cls.servico, nome="Cris Com Risco", unidade="Oncologia Fictícia",
                                        risco_evasao=True)
        cls.dez_internado_ha_mais = criar_aluno(cls.servico, nome="Dani Internada Antes", unidade=unidade,
                                                data_internacao=dias_atras(30), leito="4A")
        cls.recente = criar_aluno(cls.servico, nome="Eva Aula Recente", unidade=unidade, risco_evasao=True,
                                  data_internacao=dias_atras(90))
        cls.encerrado = criar_aluno(cls.servico, nome="Fábio Encerrado", situacao=Situacao.ENCERRADO)

    def setUp(self):
        for aluno in (self.dez_sem_risco, self.dez_com_risco, self.dez_internado_ha_mais):
            self.aula(aluno, dias_atras(25))
            self.aula(aluno, dias_atras(10))
        self.aula(self.recente, dias_atras(2))
        # Aula marcada ou que não aconteceu não conta como aula registrada.
        self.aula(self.nunca, dias_atras(1), situacao="marcada")
        self.aula(self.nunca, dias_atras(4), situacao="nao_realizada")

    def nomes(self, resposta):
        return [linha["aluno"].nome for linha in resposta.context["linhas"]]

    def test_abre_para_quem_ve_alunos_e_aulas(self):
        for pessoa in (self.professor, self.so_ver, self.supervisao):
            self.entrar(pessoa)
            resposta = self.client.get(self.url)
            self.assertEqual(resposta.status_code, 200)
            self.assertContains(resposta, '<h1 class="el-display">Ordem de atendimento</h1>', html=True)

    def test_403_sem_ver_aulas_ou_alunos(self):
        for pessoa in (self.apoio, self.so_aulas):
            self.entrar(pessoa)
            self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_ordem_dias_sem_aula_depois_risco_depois_internacao(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertEqual(self.nomes(resposta), [
            "Ana Nunca Teve", "Cris Com Risco", "Dani Internada Antes", "Beto Dez Dias", "Eva Aula Recente",
        ])

    def test_cada_linha_diz_por_que_esta_ali(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Nunca teve aula registrada · internado há 3 dias")
        self.assertContains(resposta, "10 dias sem aula · risco de evasão")
        self.assertContains(resposta, "10 dias sem aula · internado há 30 dias")
        self.assertContains(resposta, "2 dias sem aula · risco de evasão · internado há 90 dias")
        self.assertContains(resposta, '<span class="el-alunos-fila-posicao">1º</span>', html=True)
        self.assertContains(resposta, "Pediatria Fictícia · leito 4A")
        self.assertContains(resposta, "quem nunca teve aula vem antes de todos")
        self.assertContains(resposta, "Mudar a ordem à mão fica para uma próxima versão.")

    def test_so_alunos_ativos_do_servico(self):
        self.entrar(self.professor)
        nomes = self.nomes(self.client.get(self.url))
        self.assertNotIn("Fábio Encerrado", nomes)
        self.assertNotIn("Lia Inventada Moreira", nomes)
        self.assertNotIn("Tomás Inventado de Fora", nomes)

    def test_filtro_de_unidade(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url, {"unidade": "Oncologia Fictícia"})
        self.assertEqual(self.nomes(resposta), ["Cris Com Risco"])
        resposta = self.client.get(self.url, {"unidade": "Oncologia Fictícia"}, HTTP_HX_REQUEST="true",
                                   HTTP_HX_TARGET="resultados")
        self.assertNotContains(resposta, "<html")
        self.assertContains(resposta, "Cris R.")

    def test_sem_ver_vida_escolar_o_risco_nao_entra(self):
        papel = criar_papel(self.servico, "Vê alunos e aulas", ver=["identificacao", "aulas"])
        pessoa = criar_pessoa(self.servico, papel, email="ve.aulas@exemplo.org")
        self.entrar(pessoa)
        resposta = self.client.get(self.url)
        self.assertNotContains(resposta, "risco de evasão")
        self.assertEqual(self.nomes(resposta), [
            "Ana Nunca Teve", "Dani Internada Antes", "Beto Dez Dias", "Cris Com Risco", "Eva Aula Recente",
        ])

    def test_botao_registrar_aula_so_para_quem_edita_aulas(self):
        url = f'{reverse("aulas:registrar")}?aluno={self.nunca.pk}'
        self.entrar(self.professor)
        self.assertContains(self.client.get(self.url), f'href="{url}"')
        self.entrar(self.so_ver)
        self.assertNotContains(self.client.get(self.url), reverse("aulas:registrar"))

    def test_consultas_nao_crescem_com_o_numero_de_alunos(self):
        self.entrar(self.professor)
        self.client.get(self.url)
        poucas = self.contar_consultas(lambda: self.client.get(self.url))
        for numero in range(10):
            aluno = criar_aluno(self.servico, nome=f"Aluno Inventado {numero:02d}", unidade="Pediatria Fictícia")
            self.aula(aluno, dias_atras(numero + 1))
        muitas = self.contar_consultas(lambda: self.client.get(self.url))
        self.assertEqual(poucas, muitas)

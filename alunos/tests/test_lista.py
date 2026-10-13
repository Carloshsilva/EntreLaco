"""Lista de alunos: quem abre, filtros, busca enquanto digita, selos e separação entre serviços."""
from django.urls import reverse

from core.testes import criar_aluno

from .base import DIAGNOSTICO, BaseAlunos, Situacao


class ListaTestes(BaseAlunos):
    url = reverse("alunos:lista")

    def test_pede_login(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("entrar"), resposta["Location"])

    def test_abre_para_quem_ve_a_identificacao(self):
        for pessoa in (self.professor, self.apoio, self.so_ver, self.supervisao):
            self.entrar(pessoa)
            resposta = self.client.get(self.url)
            self.assertEqual(resposta.status_code, 200)
            self.assertContains(resposta, '<h1 class="el-display">Alunos</h1>', html=True)

    def test_403_para_quem_nao_ve_a_identificacao(self):
        self.entrar(self.so_aulas)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_mostra_o_nome_curto_e_so_alunos_do_servico(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, f'<a href="{reverse("alunos:detalhe", args=[self.aluno.pk])}">Lia M.</a>', html=True)
        self.assertNotContains(resposta, "Lia Inventada Moreira")
        self.assertNotContains(resposta, "Tomás")
        self.assertContains(resposta, "9 anos")
        self.assertContains(resposta, "Oncologia Fictícia · leito 12B")

    def test_padrao_mostra_ativos_e_filtra_por_situacao(self):
        criar_aluno(self.servico, nome="Caio Encerrado Inventado", situacao=Situacao.ENCERRADO)
        criar_aluno(self.servico, nome="Duda Pausa Inventada", situacao=Situacao.PAUSA)
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Lia M.")
        self.assertNotContains(resposta, "Caio I.")
        self.assertNotContains(resposta, "Duda I.")

        resposta = self.client.get(self.url, {"situacao": "encerrados"})
        self.assertContains(resposta, "Caio I.")
        self.assertNotContains(resposta, "Lia M.")
        self.assertContains(resposta, '<span class="el-badge">', count=1)

        resposta = self.client.get(self.url, {"situacao": "pausa"})
        self.assertContains(resposta, "Duda I.")
        self.assertContains(resposta, "Em pausa</span>")

        resposta = self.client.get(self.url, {"situacao": "todos"})
        for nome in ("Lia M.", "Caio I.", "Duda I."):
            self.assertContains(resposta, nome)

    def test_busca_pelo_nome_e_pelo_nome_social(self):
        criar_aluno(self.servico, nome="Gabriel Inventado Souza", nome_social="Gabi Inventada")
        self.entrar(self.professor)
        resposta = self.client.get(self.url, {"q": "moreira"})
        self.assertContains(resposta, "Lia M.")
        self.assertNotContains(resposta, "Gabi I.")
        resposta = self.client.get(self.url, {"q": "gabi"})
        self.assertContains(resposta, "Gabi I.")
        self.assertNotContains(resposta, "Lia M.")
        resposta = self.client.get(self.url, {"q": "ninguém assim"})
        self.assertContains(resposta, "Nenhum aluno encontrado")

    def test_htmx_devolve_so_os_resultados(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url, {"q": "lia"}, HTTP_HX_REQUEST="true", HTTP_HX_TARGET="resultados")
        self.assertContains(resposta, "Lia M.")
        self.assertNotContains(resposta, "<html")
        self.assertNotContains(resposta, "<h1")
        # Navegação com hx-boost recebe a página inteira.
        resposta = self.client.get(self.url, HTTP_HX_REQUEST="true", HTTP_HX_BOOSTED="true", HTTP_HX_TARGET="conteudo")
        self.assertContains(resposta, "<html")

    def test_filtra_por_unidade(self):
        criar_aluno(self.servico, nome="Nina Inventada Prado", unidade="Pediatria Fictícia")
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, '<option value="Pediatria Fictícia">Pediatria Fictícia</option>', html=True)
        resposta = self.client.get(self.url, {"unidade": "Pediatria Fictícia"})
        self.assertContains(resposta, "Nina P.")
        self.assertNotContains(resposta, "Lia M.")
        # Unidade que não existe no serviço é ignorada.
        resposta = self.client.get(self.url, {"unidade": "Unidade de outro lugar"})
        self.assertContains(resposta, "Lia M.")

    def test_selos_de_situacao_ficha_e_risco(self):
        criar_aluno(self.servico, nome="Otto Inventado Lima", risco_evasao=True)
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Ativo</span>", count=2)
        # Lia tem a ficha completa; Otto só tem o nome.
        self.assertContains(resposta, "Ficha incompleta</span>", count=1)
        self.assertContains(resposta, '<td data-label="Ficha">Completa</td>', html=True)
        self.assertContains(resposta, "Risco de evasão</span>", count=1)

    def test_risco_de_evasao_so_para_quem_ve_a_vida_escolar(self):
        criar_aluno(self.servico, nome="Otto Inventado Lima", risco_evasao=True)
        self.entrar(self.so_ver)
        resposta = self.client.get(self.url)
        self.assertNotContains(resposta, "Risco de evasão")
        self.entrar(self.apoio)
        self.assertContains(self.client.get(self.url), '<th scope="col">Risco de evasão</th>', html=True)

    def test_apoio_nao_ve_saude_nem_condicoes(self):
        self.entrar(self.apoio)
        resposta = self.client.get(self.url)
        self.assertNotContains(resposta, DIAGNOSTICO)
        self.assertNotContains(resposta, "Com alteração")
        self.assertNotContains(resposta, "Visão")

    def test_botao_cadastrar_so_para_quem_edita_a_identificacao(self):
        novo = reverse("alunos:novo")
        self.entrar(self.professor)
        self.assertContains(self.client.get(self.url), f'href="{novo}"')
        self.entrar(self.apoio)
        self.assertNotContains(self.client.get(self.url), f'href="{novo}"')

    def test_link_da_ordem_de_atendimento_so_para_quem_ve_aulas(self):
        fila = reverse("alunos:fila")
        self.entrar(self.professor)
        self.assertContains(self.client.get(self.url), f'href="{fila}"')
        self.entrar(self.apoio)
        self.assertNotContains(self.client.get(self.url), f'href="{fila}"')

    def test_pagina_de_30_em_30(self):
        for numero in range(35):
            criar_aluno(self.servico, nome=f"Aluno Inventado {numero:02d}")
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertEqual(len(resposta.context["linhas"]), 30)
        self.assertContains(resposta, "Página 1 de 2")
        resposta = self.client.get(self.url, {"pagina": 2})
        self.assertEqual(len(resposta.context["linhas"]), 6)

    def test_consultas_nao_crescem_com_o_numero_de_alunos(self):
        self.entrar(self.professor)
        self.client.get(self.url)  # aquece a sessão
        poucos = self.contar_consultas(lambda: self.client.get(self.url))
        for numero in range(20):
            criar_aluno(self.servico, nome=f"Aluno Inventado {numero:02d}", unidade="Pediatria Fictícia")
        muitos = self.contar_consultas(lambda: self.client.get(self.url))
        self.assertEqual(poucos, muitos)

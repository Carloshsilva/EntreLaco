"""Perfil do aluno: resumo, condições em destaque (RF-10), seções, ações rápidas e permissões (RF-07)."""
import re

from django.test import Client
from django.urls import reverse

from alunos.models import Aluno
from core.testes import criar_aluno

from .base import DIAGNOSTICO, Acao, BaseAlunos, dados_do_formulario


class PerfilTestes(BaseAlunos):
    def setUp(self):
        self.url = reverse("alunos:detalhe", args=[self.aluno.pk])

    def test_abre_para_quem_ve_a_identificacao(self):
        for pessoa in (self.professor, self.apoio, self.so_ver, self.orientacao):
            self.entrar(pessoa)
            resposta = self.client.get(self.url)
            self.assertEqual(resposta.status_code, 200)
            self.assertContains(resposta, '<h1 id="titulo-aluno" class="el-student-name">Lia Inventada Moreira</h1>',
                                html=True)
            self.assertEqual(len(re.findall(r"<h1[ >]", resposta.content.decode())), 1)

    def test_403_para_quem_nao_ve_a_identificacao(self):
        self.entrar(self.so_aulas)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_404_para_aluno_de_outro_servico(self):
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(reverse("alunos:detalhe", args=[self.aluno_de_fora.pk])).status_code, 404)

    def test_resumo(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "<dt>Idade</dt><dd>9 anos</dd>", html=True)
        self.assertContains(resposta, "<dt>Unidade</dt><dd>Oncologia Fictícia</dd>", html=True)
        self.assertContains(resposta, "<dt>Leito</dt><dd>12B</dd>", html=True)
        self.assertContains(resposta, "Ativo</span>")
        self.assertNotContains(resposta, "Ficha incompleta")

    def test_condicoes_em_destaque_para_quem_ve_aprendizagem(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, '<dl class="el-student-flags">')
        for rotulo in ("Visão", "Audição", "Fala", "Motricidade", "Alfabetização", "Reprovação"):
            self.assertContains(resposta, f"<dt>{rotulo}</dt>", html=True)
        # Só a visão pede atenção: com alteração. A palavra vem junto da cor.
        self.assertContains(resposta, "el-flag el-flag-attention", count=1)
        self.assertContains(resposta, '<span class="el-sr-only">Atenção: </span>Com alteração', html=False)

    def test_nao_alfabetizado_e_ja_reprovou_pedem_atencao(self):
        aluno = criar_aluno(self.servico, nome="Davi Inventado Luz", alfabetizacao=Aluno.Alfabetizacao.NAO_ALFABETIZADO,
                            reprovacao=Aluno.Reprovacao.JA_REPROVOU)
        self.entrar(self.professor)
        resposta = self.client.get(reverse("alunos:detalhe", args=[aluno.pk]))
        self.assertContains(resposta, "el-flag el-flag-attention", count=2)

    def test_apoio_nao_ve_diagnostico_nem_condicoes(self):
        # Uma edição de saúde fica na trilha, mas o apoio não vê o que mudou.
        cliente = Client()
        cliente.force_login(self.professor)
        url_editar = reverse("alunos:editar", args=[self.aluno.pk])
        tela = cliente.get(url_editar)
        cliente.post(url_editar, dados_do_formulario(
            tela.context["form"], diagnostico="Outro diagnóstico inventado", motivo_alteracao="Laudo novo.",
            estado_original=tela.context["estado_original"],
        ))
        self.assertTrue(self.eventos(acao=Acao.ALTEROU, modelo="alunos.Aluno").exists())

        self.entrar(self.apoio)
        resposta = self.client.get(self.url)
        self.assertNotContains(resposta, DIAGNOSTICO)
        self.assertNotContains(resposta, "Outro diagnóstico inventado")
        self.assertNotContains(resposta, "Diagnóstico")
        self.assertNotContains(resposta, "Tratamento inventado")
        self.assertNotContains(resposta, "el-student-flags")
        self.assertNotContains(resposta, "Visão")
        self.assertNotContains(resposta, "Saúde e dados sensíveis")
        self.assertNotContains(resposta, "Condições e aprendizagem")
        # Mas vê a vida escolar e os responsáveis.
        self.assertContains(resposta, "Vida escolar")
        self.assertContains(resposta, "Rita Responsável Inventada")

        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Outro diagnóstico inventado")

    def test_secoes_com_abas_na_ordem_combinada(self):
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url)
        conteudo = resposta.content.decode()
        posicoes = [conteudo.index(f'id="secao-{chave}"') for chave in ("ficha", "responsaveis", "situacao", "historico")]
        self.assertEqual(posicoes, sorted(posicoes))
        for chave, titulo in (("ficha", "Ficha"), ("responsaveis", "Responsáveis"), ("situacao", "Situação"),
                              ("historico", "Histórico de alterações")):
            self.assertContains(resposta, f'<a href="#secao-{chave}" data-aba-do-perfil>{titulo}</a>', html=True)
            self.assertContains(
                resposta, f'<h2 id="titulo-{chave}" class="el-heading">{titulo}</h2>', html=True,
            )
            self.assertContains(resposta, f'aria-labelledby="titulo-{chave}"')

    def test_responsaveis_so_para_quem_ve_a_familia(self):
        self.entrar(self.so_ver)
        resposta = self.client.get(self.url)
        self.assertNotContains(resposta, 'id="secao-responsaveis"')
        self.assertNotContains(resposta, "Rita Responsável Inventada")

    def test_acoes_rapidas_do_professor(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, f'href="{reverse("aulas:registrar")}?aluno={self.aluno.pk}"')
        self.assertContains(resposta, f'href="{reverse("aulas:marcar")}?aluno={self.aluno.pk}"')
        self.assertContains(resposta, f'href="{reverse("alunos:editar", args=[self.aluno.pk])}"')
        self.assertContains(resposta, "el-btn el-btn-primary", count=1)

    def test_acoes_rapidas_somem_para_quem_nao_pode(self):
        self.entrar(self.so_ver)
        resposta = self.client.get(self.url)
        self.assertNotContains(resposta, reverse("aulas:registrar"))
        self.assertNotContains(resposta, reverse("alunos:editar", args=[self.aluno.pk]))
        self.assertNotContains(resposta, "Mudar situação")
        self.assertNotContains(resposta, "el-btn-primary")

    def test_aluno_encerrado_nao_oferece_registrar_aula(self):
        Aluno.objects.filter(pk=self.aluno.pk).update(situacao=Aluno.Situacao.ENCERRADO)
        self.entrar(self.professor)
        self.assertNotContains(self.client.get(self.url), reverse("aulas:registrar"))

    def test_mudar_situacao_so_para_quem_tem_a_acao(self):
        url = reverse("alunos:situacao", args=[self.aluno.pk])
        self.entrar(self.professor)
        self.assertNotContains(self.client.get(self.url), f'href="{url}"')
        self.entrar(self.orientacao)
        self.assertContains(self.client.get(self.url), f'href="{url}"')

    def test_ficha_incompleta_lista_o_que_falta_so_do_que_a_pessoa_ve(self):
        aluno = criar_aluno(self.servico, nome="Nico Inventado Sol", data_nascimento="2016-01-01", unidade="Pediatria")
        url = reverse("alunos:detalhe", args=[aluno.pk])
        self.entrar(self.professor)
        resposta = self.client.get(url)
        self.assertContains(resposta, "Ficha incompleta</span>")
        self.assertContains(resposta, "Falta: ano escolar, escola de origem e um responsável.")
        self.entrar(self.so_ver)
        resposta = self.client.get(url)
        self.assertContains(resposta, "Faltam dados que o seu papel não mostra.")
        self.assertNotContains(resposta, "escola de origem")

    def test_ficha_mostra_cada_tipo_de_dado_que_a_pessoa_ve(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        for titulo in ("Identificação do aluno", "Condições e aprendizagem", "Saúde e dados sensíveis", "Vida escolar"):
            self.assertContains(resposta, f'<h3 class="el-label-text">{titulo}</h3>', html=True)
        self.assertContains(resposta, DIAGNOSTICO)
        self.assertContains(resposta, "Escola Municipal Inventada Alfa")
        self.entrar(self.so_ver)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, '<h3 class="el-label-text">Identificação do aluno</h3>', html=True)
        self.assertNotContains(resposta, "Vida escolar")
        self.assertNotContains(resposta, "Escola Municipal Inventada Alfa")

    def test_historico_de_alteracoes(self):
        self.entrar(self.professor)
        url_editar = reverse("alunos:editar", args=[self.aluno.pk])
        tela = self.client.get(url_editar)
        self.client.post(url_editar, dados_do_formulario(
            tela.context["form"], leito="9C", motivo_alteracao="Troca de quarto.",
            estado_original=tela.context["estado_original"],
        ))
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Motivo: Troca de quarto.")
        self.assertContains(resposta, "<ins><span class=\"el-sr-only\">depois </span>9C</ins>", html=True)

    def test_consultas_do_perfil(self):
        self.entrar(self.supervisao)
        self.client.get(self.url)
        poucas = self.contar_consultas(lambda: self.client.get(self.url))
        for numero in range(5):
            self.mudanca(self.aluno, "ativo", "ativo", motivo=f"Revisão inventada {numero}")
        muitas = self.contar_consultas(lambda: self.client.get(self.url))
        self.assertEqual(poucas, muitas)

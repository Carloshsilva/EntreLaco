"""Editar a ficha: permissão por tipo de dado, motivo obrigatório, trilha e conflito de edição (RNF-04)."""
from unittest import mock

from django.db.models import F
from django.test import Client
from django.urls import reverse

from alunos import formularios
from alunos.models import Aluno

from .base import DIAGNOSTICO, Acao, BaseAlunos, dados_do_formulario


class EditarFichaTestes(BaseAlunos):
    def setUp(self):
        self.url = reverse("alunos:editar", args=[self.aluno.pk])

    def test_abre_para_quem_edita_algum_tipo_de_dado_da_ficha(self):
        for pessoa in (self.professor, self.orientacao, self.apoio):
            self.entrar(pessoa)
            resposta = self.client.get(self.url)
            self.assertEqual(resposta.status_code, 200)
            self.assertContains(resposta, "Por que você está alterando?")

    def test_403_para_quem_so_ve(self):
        for pessoa in (self.so_ver, self.so_aulas):
            self.entrar(pessoa)
            self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_404_para_aluno_de_outro_servico(self):
        self.entrar(self.professor)
        url = reverse("alunos:editar", args=[self.aluno_de_fora.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"nome": "Outro", "motivo_alteracao": "teste"}).status_code, 404)

    def test_apoio_edita_so_a_vida_escolar(self):
        self.entrar(self.apoio)
        resposta = self.client.get(self.url)
        campos = set(resposta.context["form"].fields) - {"motivo_alteracao"}
        self.assertEqual(campos, set(Aluno.GRUPOS_DE_CAMPOS["escolar"]))
        self.assertNotContains(resposta, DIAGNOSTICO)
        self.assertNotContains(resposta, 'name="diagnostico"')
        self.assertNotContains(resposta, 'name="visao"')
        self.assertNotContains(resposta, "Condições e aprendizagem")
        self.assertNotContains(resposta, "Saúde e dados sensíveis")

    def test_salvar_pede_motivo_e_grava_a_trilha(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        dados = dados_do_formulario(resposta.context["form"], leito="7A",
                                    estado_original=resposta.context["estado_original"])
        resposta = self.client.post(self.url, dados)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Conte por que você está alterando")
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.leito, "12B")

        dados["motivo_alteracao"] = "A criança mudou de quarto."
        resposta = self.client.post(self.url, dados)
        self.assertRedirects(resposta, reverse("alunos:detalhe", args=[self.aluno.pk]) + "#secao-ficha",
                             fetch_redirect_response=False)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.leito, "7A")
        self.assertEqual(self.aluno.versao, 2)
        evento = self.eventos(acao=Acao.ALTEROU, modelo="alunos.Aluno").get()
        self.assertEqual(evento.motivo, "A criança mudou de quarto.")
        self.assertEqual(evento.aluno_id, self.aluno.pk)
        self.assertEqual(list(evento.mudancas), ["leito"])
        self.assertEqual(evento.mudancas["leito"]["de"], "12B")

    def test_apoio_salva_a_vida_escolar_sem_mexer_no_resto(self):
        self.entrar(self.apoio)
        resposta = self.client.get(self.url)
        dados = dados_do_formulario(resposta.context["form"], turma="4º B", risco_evasao="on",
                                    motivo_alteracao="A escola informou a turma.",
                                    estado_original=resposta.context["estado_original"])
        self.assertEqual(self.client.post(self.url, dados).status_code, 302)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.turma, "4º B")
        self.assertTrue(self.aluno.risco_evasao)
        self.assertEqual(self.aluno.diagnostico, DIAGNOSTICO)
        self.assertEqual(self.aluno.visao, Aluno.Condicao.COM_ALTERACAO)


class ConflitoDeEdicaoTestes(BaseAlunos):
    """Duas pessoas abrem a ficha ao mesmo tempo, em dois aparelhos (RNF-04)."""

    def setUp(self):
        self.url = reverse("alunos:editar", args=[self.aluno.pk])
        self.primeira, self.segunda = Client(), Client()
        self.primeira.force_login(self.professor)
        self.segunda.force_login(self.orientacao)
        self.tela_1 = self.primeira.get(self.url)
        self.tela_2 = self.segunda.get(self.url)

    def enviar(self, cliente, tela, **trocas):
        dados = dados_do_formulario(tela.context["form"], estado_original=tela.context["estado_original"], **trocas)
        return cliente.post(self.url, dados)

    def test_mesmo_campo_mostra_as_duas_versoes_e_nada_e_salvo(self):
        resposta = self.enviar(self.primeira, self.tela_1, leito="20A", motivo_alteracao="Mudou de leito.")
        self.assertEqual(resposta.status_code, 302)

        resposta = self.enviar(self.segunda, self.tela_2, leito="31C", motivo_alteracao="Leito novo informado.")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Outra pessoa salvou este cadastro enquanto você editava")
        self.assertContains(resposta, "Paula I. salvou")
        self.assertContains(resposta, "<dd>20A</dd>", html=True)
        self.assertContains(resposta, "<dd>31C</dd>", html=True)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.leito, "20A")
        self.assertEqual(self.eventos(acao=Acao.ALTEROU, modelo="alunos.Aluno").count(), 1)

        # Quem salvou por último escolhe: ao salvar de novo, com o aviso visto, vale a escolha.
        dados = dados_do_formulario(resposta.context["form"], estado_original=resposta.context["estado_original"],
                                    leito="31C", motivo_alteracao="Conferi com a enfermagem.")
        self.assertEqual(self.segunda.post(self.url, dados).status_code, 302)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.leito, "31C")

    def test_campos_diferentes_se_juntam_sem_conflito(self):
        self.enviar(self.primeira, self.tela_1, leito="20A", motivo_alteracao="Mudou de leito.")
        resposta = self.enviar(self.segunda, self.tela_2, unidade="Pediatria Fictícia",
                               motivo_alteracao="Mudou de unidade.")
        self.assertEqual(resposta.status_code, 302)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.leito, "20A")
        self.assertEqual(self.aluno.unidade, "Pediatria Fictícia")
        self.assertEqual(self.aluno.versao, 3)


class GravacaoNoMeioDoCaminhoTestes(BaseAlunos):
    """Outra pessoa grava campos que esta pessoa nem vê entre abrir e salvar: nada disso é desfeito."""

    def test_salvar_a_vida_escolar_nao_desfaz_o_que_foi_gravado_no_meio(self):
        url = reverse("alunos:editar", args=[self.aluno.pk])
        self.entrar(self.apoio)
        tela = self.client.get(url)
        dados = dados_do_formulario(
            tela.context["form"], turma="4º B", motivo_alteracao="A escola mandou a turma nova.",
            estado_original=tela.context["estado_original"],
        )
        original = formularios.FormularioAlunoBase.clean
        pk = self.aluno.pk

        def clean_com_outra_gravacao(form):
            # Outra pessoa grava depois de a tela do apoio ler o aluno e antes da trava do salvar.
            Aluno.objects.filter(pk=pk).update(
                diagnostico="Diagnóstico corrigido por outra pessoa", situacao=Aluno.Situacao.PAUSA,
                versao=F("versao") + 1,
            )
            return original(form)

        with mock.patch.object(formularios.FormularioAlunoBase, "clean", clean_com_outra_gravacao):
            resposta = self.client.post(url, dados)
        self.assertEqual(resposta.status_code, 302)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.turma, "4º B")
        self.assertEqual(self.aluno.diagnostico, "Diagnóstico corrigido por outra pessoa")
        self.assertEqual(self.aluno.situacao, Aluno.Situacao.PAUSA)

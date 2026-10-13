"""Responsáveis: adicionar e editar, com permissão de família, separação entre serviços e trilha."""
from django.urls import reverse

from alunos.models import Responsavel

from .base import Acao, BaseAlunos, dados_do_formulario

DADOS = {
    "nome": "Jorge Responsável Inventado", "parentesco": "pai", "responsavel_legal": "on",
    "telefone": "11 97777 1234", "email": "jorge@exemplo.org",
}


class AdicionarResponsavelTestes(BaseAlunos):
    def setUp(self):
        self.url = reverse("alunos:responsavel_novo", args=[self.aluno.pk])

    def test_abre_para_quem_edita_a_familia(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, '<h1 class="el-display">Adicionar responsável</h1>', html=True)
        self.assertContains(resposta, "Escolha o parentesco")

    def test_403_para_quem_so_ve_a_familia(self):
        self.entrar(self.apoio)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, DADOS).status_code, 403)
        self.assertFalse(Responsavel.objects.filter(nome=DADOS["nome"]).exists())

    def test_404_para_aluno_de_outro_servico(self):
        self.entrar(self.professor)
        url = reverse("alunos:responsavel_novo", args=[self.aluno_de_fora.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, DADOS).status_code, 404)
        self.assertFalse(Responsavel.objects.filter(nome=DADOS["nome"]).exists())

    def test_salvar_grava_aluno_servico_e_trilha(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, DADOS)
        self.assertRedirects(resposta, reverse("alunos:detalhe", args=[self.aluno.pk]) + "#secao-responsaveis",
                             fetch_redirect_response=False)
        responsavel = Responsavel.objects.get(nome=DADOS["nome"])
        self.assertEqual(responsavel.aluno, self.aluno)
        self.assertEqual(responsavel.servico, self.servico)
        self.assertEqual(responsavel.telefone, "(11) 97777-1234")
        evento = self.eventos(acao=Acao.CRIOU, modelo="alunos.Responsavel").get()
        self.assertEqual(evento.aluno_id, self.aluno.pk)
        self.assertEqual(evento.mudancas["nome"]["grupo"], "familia")

    def test_erros_dizem_como_resolver(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, {"nome": "", "parentesco": "", "telefone": "123"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Falta o nome do responsável")
        self.assertContains(resposta, "Escolha o parentesco. Se não estiver na lista")
        self.assertContains(resposta, "Digite o telefone com DDD")


class EditarResponsavelTestes(BaseAlunos):
    def setUp(self):
        self.url = reverse("alunos:responsavel_editar", args=[self.responsavel.pk])

    def test_abre_para_quem_edita_a_familia(self):
        self.entrar(self.orientacao)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Rita Responsável Inventada")
        self.assertContains(resposta, "Por que você está alterando?")

    def test_403_para_quem_nao_edita(self):
        for pessoa in (self.apoio, self.so_ver):
            self.entrar(pessoa)
            self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_404_para_responsavel_de_outro_servico(self):
        self.entrar(self.professor)
        url = reverse("alunos:responsavel_editar", args=[self.responsavel_de_fora.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_salvar_pede_motivo_e_grava_a_trilha(self):
        self.entrar(self.professor)
        tela = self.client.get(self.url)
        dados = dados_do_formulario(tela.context["form"], telefone="(11) 95555-0000",
                                    estado_original=tela.context["estado_original"])
        self.assertEqual(self.client.post(self.url, dados).status_code, 200)
        self.responsavel.refresh_from_db()
        self.assertEqual(self.responsavel.telefone, "(11) 98888-0000")

        dados["motivo_alteracao"] = "A mãe trocou de número."
        self.assertEqual(self.client.post(self.url, dados).status_code, 302)
        self.responsavel.refresh_from_db()
        self.assertEqual(self.responsavel.telefone, "(11) 95555-0000")
        evento = self.eventos(acao=Acao.ALTEROU, modelo="alunos.Responsavel").get()
        self.assertEqual(evento.motivo, "A mãe trocou de número.")
        self.assertEqual(evento.aluno_id, self.aluno.pk)

    def test_perfil_mostra_os_botoes_so_para_quem_edita(self):
        perfil = reverse("alunos:detalhe", args=[self.aluno.pk])
        self.entrar(self.professor)
        resposta = self.client.get(perfil)
        self.assertContains(resposta, f'href="{self.url}"')
        self.assertContains(resposta, reverse("alunos:responsavel_novo", args=[self.aluno.pk]))
        self.assertContains(resposta, 'href="tel:11988880000"')
        self.entrar(self.apoio)
        resposta = self.client.get(perfil)
        self.assertContains(resposta, "Rita Responsável Inventada")
        self.assertNotContains(resposta, f'href="{self.url}"')
        self.assertNotContains(resposta, reverse("alunos:responsavel_novo", args=[self.aluno.pk]))

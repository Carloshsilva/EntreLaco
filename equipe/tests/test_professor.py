"""Perfil de professor (RF-09)."""
from unittest import mock

from django.db import IntegrityError
from django.urls import reverse

from core.models import EventoAuditoria
from equipe.models import ComponenteCurricular, PerfilProfessor

from .base import EquipeTestCase

Acao = EventoAuditoria.Acao


class PerfilDeProfessorTestes(EquipeTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.matematica = ComponenteCurricular.objects.create(servico=cls.servico, nome="Matemática")
        cls.arte = ComponenteCurricular.objects.create(servico=cls.servico, nome="Arte")
        cls.desativado = ComponenteCurricular.objects.create(servico=cls.servico, nome="Latim", ativo=False)
        cls.componente_de_fora = ComponenteCurricular.objects.create(servico=cls.outro_servico, nome="Música Fictícia")

    def test_quem_cuida_da_equipe_cadastra_o_perfil(self):
        self.entrar(self.coordenacao)
        url = reverse("equipe:professor", args=[self.professor.pk])
        tela = self.client.get(url)
        self.assertEqual(tela.status_code, 200)
        self.assertContains(tela, "Cadastrar perfil de professor")
        self.assertContains(tela, "Matemática")
        self.assertNotContains(tela, "Latim")
        self.assertNotContains(tela, "Música Fictícia")
        self.assertNotContains(tela, "Por que você está alterando?")
        resposta = self.client.post(url, {
            "componentes": [self.matematica.pk, self.arte.pk], "anos_iniciais": "on", "observacoes": "Atende à tarde",
        })
        self.assertRedirects(resposta, reverse("equipe:pessoa_detalhe", args=[self.professor.pk]))
        perfil = PerfilProfessor.objects.get(servico=self.servico, usuario=self.professor)
        self.assertEqual(set(perfil.componentes.all()), {self.matematica, self.arte})
        self.assertEqual(perfil.etapas, ["anos iniciais (1º ao 5º ano)"])
        self.assertTrue(self.eventos(acao=Acao.CRIOU, modelo="equipe.PerfilProfessor").exists())
        detalhe = self.client.get(reverse("equipe:pessoa_detalhe", args=[self.professor.pk]))
        self.assertContains(detalhe, "Arte, Matemática")
        self.assertContains(detalhe, "Atende à tarde")
        self.assertContains(detalhe, f"{reverse('agenda')}?pessoa={self.professor.pk}")

    def test_editar_pede_motivo_e_grava_trilha(self):
        perfil = PerfilProfessor.objects.create(servico=self.servico, usuario=self.professor)
        perfil.componentes.add(self.desativado)
        self.entrar(self.coordenacao)
        url = reverse("equipe:professor", args=[self.professor.pk])
        tela = self.client.get(url)
        self.assertContains(tela, "Editar perfil de professor")
        self.assertContains(tela, "Latim")  # quem já tinha o componente desativado continua com ele
        resposta = self.client.post(url, {"componentes": [self.desativado.pk, self.arte.pk], "eja": "on"})
        self.assertContains(resposta, "Por que você está alterando?")
        resposta = self.client.post(url, {
            "componentes": [self.desativado.pk, self.arte.pk], "eja": "on", "motivo_alteracao": "Começou na EJA",
        })
        self.assertRedirects(resposta, reverse("equipe:pessoa_detalhe", args=[self.professor.pk]))
        perfil.refresh_from_db()
        self.assertTrue(perfil.eja)
        self.assertEqual(perfil.versao, 2)
        evento = self.eventos(acao=Acao.ALTEROU, modelo="equipe.PerfilProfessor").get()
        self.assertEqual(evento.motivo, "Começou na EJA")
        self.assertIn("componentes", evento.mudancas)

    def test_componente_de_outro_servico_e_recusado(self):
        self.entrar(self.coordenacao)
        resposta = self.client.post(reverse("equipe:professor", args=[self.professor.pk]), {"componentes": [self.componente_de_fora.pk]})
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(PerfilProfessor.objects.exists())

    def test_a_propria_pessoa_edita_o_proprio_perfil(self):
        self.entrar(self.professor)
        url = reverse("equipe:professor", args=[self.professor.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        resposta = self.client.post(url, {"componentes": [self.matematica.pk]})
        self.assertRedirects(resposta, reverse("minha_conta"))
        self.assertTrue(PerfilProfessor.objects.filter(usuario=self.professor, servico=self.servico).exists())

    def test_professor_nao_edita_o_perfil_de_outra_pessoa(self):
        self.entrar(self.professor)
        self.assertEqual(self.client.get(reverse("equipe:professor", args=[self.apoio.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("equipe:professor", args=[self.apoio.pk]), {}).status_code, 403)

    def test_pessoa_de_outro_servico_da_404(self):
        self.entrar(self.supervisao)
        url = reverse("equipe:professor", args=[self.de_fora.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"componentes": [self.matematica.pk]}).status_code, 404)
        self.assertFalse(PerfilProfessor.objects.exists())

    def test_perfil_criado_por_outra_pessoa_ao_mesmo_tempo(self):
        self.entrar(self.coordenacao)
        url = reverse("equipe:professor", args=[self.professor.pk])
        # A outra pessoa grava o perfil entre a conferência e a gravação desta: o banco recusa o segundo.
        with mock.patch("core.views_base.CriarComAuditoriaMixin.form_valid", side_effect=IntegrityError):
            resposta = self.client.post(url, {"componentes": [self.matematica.pk]}, follow=True)
        self.assertRedirects(resposta, url)
        self.assertContains(resposta, "Outra pessoa acabou de criar este perfil")
        self.assertFalse(PerfilProfessor.objects.exists())

    def test_sem_login_vai_para_entrar(self):
        resposta = self.client.get(reverse("equipe:professor", args=[self.professor.pk]))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("entrar"), resposta["Location"])

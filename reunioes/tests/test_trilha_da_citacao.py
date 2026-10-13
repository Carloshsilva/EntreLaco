"""A citação na trilha segue a regra da tela: só vê quem vê as atas e o tipo de dado dela (RF-07, RF-17)."""
from django.urls import reverse

from core.models import EventoAuditoria
from reunioes.models import CitacaoDeAluno

from .base import BaseReunioes

TEXTO = "A família contou um conflito inventado para teste"


class TrilhaDaCitacaoTestes(BaseReunioes):
    def setUp(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(reverse("reunioes:citacao_nova", args=[self.reuniao.pk]), {
            "aluno": self.aluno.pk, "texto": TEXTO, "grupo_de_dado": "familia",
            "encaminhamento": "", "responsavel": "", "prazo": "",
        })
        self.assertEqual(resposta.status_code, 302)
        self.citacao = CitacaoDeAluno.objects.get()
        # A correção do texto vira um evento com o antes e o depois.
        url_editar = reverse("reunioes:citacao_editar", args=[self.citacao.pk])
        tela = self.client.get(url_editar)
        resposta = self.client.post(url_editar, {
            "aluno": self.aluno.pk, "texto": TEXTO + " (corrigido)", "grupo_de_dado": "familia",
            "encaminhamento": "", "responsavel": "", "prazo": "",
            "motivo_alteracao": "Corrigi o texto.", "estado_original": tela.context["estado_original"],
        })
        self.assertEqual(resposta.status_code, 302)

    def test_evento_exige_atas_e_o_tipo_da_citacao(self):
        grupos = set(EventoAuditoria.objects.filter(modelo="reunioes.CitacaoDeAluno").values_list("grupo", flat=True))
        self.assertEqual(grupos, {"atas+familia"})

    def test_quem_ve_familia_mas_nao_ve_atas_nao_le_a_citacao_no_historico(self):
        papel_apoio = self.apoio.vinculos.get().papel
        self.assertEqual(papel_apoio.acessos["atas"], "nenhum")
        self.assertIn(papel_apoio.acessos["familia"], ("ver", "editar"))
        self.entrar(self.apoio)
        perfil = self.client.get(reverse("alunos:detalhe", args=[self.aluno.pk]))
        self.assertEqual(perfil.status_code, 200)
        self.assertNotContains(perfil, TEXTO)

    def test_quem_ve_atas_e_familia_le_a_citacao_no_historico(self):
        perfil = self.client.get(reverse("alunos:detalhe", args=[self.aluno.pk]))
        self.assertContains(perfil, TEXTO)

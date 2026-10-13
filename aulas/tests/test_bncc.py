"""Lista da BNCC do serviço (RF-16): só quem configura mantém."""
from django.urls import reverse

from aulas.models import HabilidadeBNCC
from core.models import EventoAuditoria

from .base import BaseDeAulas


class ListaDaBnccTestes(BaseDeAulas):
    url = reverse("aulas:habilidades")

    def test_abre_para_quem_configura(self):
        self.criar_habilidade("EF01LP01", eixo="Leitura")
        self.criar_habilidade("EF99XX99", servico=self.outro_servico, descricao="Habilidade de outro serviço.")
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "<h1", count=1)
        self.assertContains(resposta, "EF01LP01")
        self.assertNotContains(resposta, "EF99XX99")
        self.assertContains(resposta, 'data-label="Situação"')

    def test_diz_se_esta_ligada_ou_desligada(self):
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Desligada no serviço.")
        self.assertContains(resposta, reverse("equipe:configuracao"))
        self.servico.bncc_ativa = True
        self.servico.save()
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Ligada no serviço.")

    def test_quem_nao_configura_recebe_403(self):
        for pessoa in (self.professor, self.apoio, self.leitor):
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.get(reverse("aulas:habilidade_nova")).status_code, 403)


class HabilidadeFormularioTestes(BaseDeAulas):
    def test_cadastrar_grava_a_trilha(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(reverse("aulas:habilidade_nova"), {
            "codigo": " ef01lp01 ", "eixo": "Leitura", "descricao": "Reconhecer letras inventadas.", "ativa": "on",
        })
        self.assertRedirects(resposta, reverse("aulas:habilidades"))
        habilidade = HabilidadeBNCC.objects.get()
        self.assertEqual(habilidade.codigo, "EF01LP01")
        self.assertEqual(habilidade.servico, self.servico)
        self.assertTrue(EventoAuditoria.objects.filter(
            modelo="aulas.HabilidadeBNCC", objeto_id=str(habilidade.pk), acao=EventoAuditoria.Acao.CRIOU,
        ).exists())

    def test_codigo_repetido_no_servico(self):
        self.criar_habilidade("EF01LP01")
        self.criar_habilidade("EF01LP02", servico=self.outro_servico)
        self.entrar(self.supervisao)
        resposta = self.client.post(reverse("aulas:habilidade_nova"), {"codigo": "EF01LP01", "descricao": "Outra."})
        self.assertContains(resposta, "O código EF01LP01 já está na lista do serviço")
        # O mesmo código em outro serviço não atrapalha.
        resposta = self.client.post(reverse("aulas:habilidade_nova"), {"codigo": "EF01LP02", "descricao": "Outra."})
        self.assertEqual(resposta.status_code, 302)

    def test_editar_pede_motivo_e_grava_a_trilha(self):
        habilidade = self.criar_habilidade("EF01LP01")
        url = reverse("aulas:habilidade_editar", args=[habilidade.pk])
        self.entrar(self.supervisao)
        resposta = self.client.get(url)
        self.assertContains(resposta, "Histórico da habilidade")
        resposta = self.client.post(url, {
            "codigo": "EF01LP01", "descricao": habilidade.descricao, "motivo_alteracao": "Saiu da lista do serviço.",
            "estado_original": resposta.context["estado_original"],
        })
        self.assertRedirects(resposta, reverse("aulas:habilidades"))
        habilidade.refresh_from_db()
        self.assertFalse(habilidade.ativa)
        evento = EventoAuditoria.objects.filter(modelo="aulas.HabilidadeBNCC", acao=EventoAuditoria.Acao.ALTEROU).get()
        self.assertEqual(evento.motivo, "Saiu da lista do serviço.")

    def test_habilidade_de_outro_servico_da_404(self):
        de_fora = self.criar_habilidade("EF01LP01", servico=self.outro_servico)
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(reverse("aulas:habilidade_editar", args=[de_fora.pk])).status_code, 404)

"""Comprovante e arquivos: só com login, serviço e permissão; cada abertura vai para a trilha (LGPD-03, SEG-04, SEG-05)."""
from django.urls import reverse

from .base import (
    Acao,
    BaseAutorizacoes,
    Forma,
    Situacao,
    Tipo,
    data_url,
    foto_jpg,
    png_de_assinatura,
)


class DetalheTestes(BaseAutorizacoes):
    def url(self, autorizacao):
        return reverse("autorizacoes:detalhe", args=[autorizacao.pk])

    def colher_no_papel(self):
        self.client.force_login(self.professor)
        self.client.post(self.url_colher(), {
            "forma": "papel", "quem": str(self.responsavel.pk), "documento": "RG inventado 123",
            "decisao": "autorizou", "arquivo": foto_jpg(),
        })
        return self.aluno.autorizacoes.get()

    def test_abre_para_quem_ve_com_a_prova(self):
        autorizacao = self.colher_no_papel()
        for pessoa in (self.professor, self.apoio):
            self.client.force_login(pessoa)
            resposta = self.client.get(self.url(autorizacao))
            self.assertEqual(resposta.status_code, 200)
            self.assertContains(resposta, "<h1", count=1)
            self.assertContains(resposta, "Autorização de contato com a escola")
            self.assertContains(resposta, "Rita Responsável Inventada")
            self.assertContains(resposta, "RG inventado 123")
            self.assertContains(resposta, autorizacao.impressao_digital)
            self.assertContains(resposta, "Confere: o arquivo não mudou")
            self.assertContains(resposta, "Contato com a escola (texto provisório)")
            self.assertContains(resposta, "autorizo o serviço a falar com a escola")
            self.assertContains(resposta, f'href="{reverse("autorizacoes:arquivo", args=[autorizacao.pk])}" hx-boost="false"')
            self.assertContains(resposta, "registrou assinatura")  # histórico
            self.assertNotContains(resposta, "Diagnóstico inventado")

    def test_botoes_so_para_quem_edita(self):
        autorizacao = self.coleta()
        url_revogar = reverse("autorizacoes:revogar", args=[autorizacao.pk])
        self.client.force_login(self.professor)
        self.assertContains(self.client.get(self.url(autorizacao)), url_revogar)
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url(autorizacao))
        self.assertNotContains(resposta, url_revogar)
        self.assertNotContains(resposta, self.url_colher())

    def test_403_para_quem_nao_ve_autorizacoes(self):
        autorizacao = self.coleta()
        self.client.force_login(self.so_aulas)
        self.assertEqual(self.client.get(self.url(autorizacao)).status_code, 403)

    def test_404_para_outro_servico(self):
        de_fora = self.coleta(aluno=self.aluno_de_fora, termo=self.termo_de_fora, colhida_por=self.de_fora)
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(self.url(de_fora)).status_code, 404)

    def test_coleta_substituida_avisa_e_aponta_a_atual(self):
        antiga = self.coleta(situacao=Situacao.RECUSADA)
        atual = self.coleta(situacao=Situacao.VALIDA)
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url(antiga))
        self.assertContains(resposta, "substituída por uma mais recente")
        self.assertContains(resposta, self.url(atual))
        self.assertNotContains(resposta, reverse("autorizacoes:revogar", args=[antiga.pk]))

    def test_pendente_no_tablet_oferece_continuar(self):
        autorizacao = self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.PENDENTE, forma=Forma.TABLET)
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url(autorizacao))
        self.assertContains(resposta, reverse("autorizacoes:assinar", args=[autorizacao.pk]))
        self.assertContains(resposta, "Ainda não há: a impressão digital é gerada quando a família responde.")


class ArquivosTestes(BaseAutorizacoes):
    def test_arquivo_sai_so_pela_view_e_vai_para_a_trilha(self):
        autorizacao = self.coleta(arquivo=foto_jpg())
        url = reverse("autorizacoes:arquivo", args=[autorizacao.pk])
        for pessoa in (self.professor, self.apoio):
            self.client.force_login(pessoa)
            resposta = self.client.get(url)
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta["Content-Type"], "image/jpeg")
            self.assertIn("no-store", resposta["Cache-Control"])
            self.assertNotIn("Lia", resposta.get("Content-Disposition", ""))
            b"".join(resposta.streaming_content)
        eventos = self.eventos(autorizacao, Acao.BAIXOU_ARQUIVO)
        self.assertEqual(eventos.count(), 2)
        self.assertEqual({e.usuario for e in eventos}, {self.professor, self.apoio})

    def test_arquivo_pede_login_e_permissao(self):
        autorizacao = self.coleta(arquivo=foto_jpg())
        url = reverse("autorizacoes:arquivo", args=[autorizacao.pk])
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("entrar"), resposta["Location"])
        self.client.force_login(self.so_aulas)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertFalse(self.eventos(autorizacao, Acao.BAIXOU_ARQUIVO).exists())

    def test_arquivo_de_outro_servico_da_404(self):
        de_fora = self.coleta(
            aluno=self.aluno_de_fora, termo=self.termo_de_fora, colhida_por=self.de_fora, arquivo=foto_jpg()
        )
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(reverse("autorizacoes:arquivo", args=[de_fora.pk])).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("autorizacoes:imagem_assinatura", args=[de_fora.pk])).status_code, 404
        )

    def test_sem_arquivo_da_404(self):
        autorizacao = self.coleta(situacao=Situacao.PENDENTE, forma="")
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(reverse("autorizacoes:arquivo", args=[autorizacao.pk])).status_code, 404)

    def test_imagem_da_assinatura(self):
        autorizacao = self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.PENDENTE, forma=Forma.TABLET)
        self.client.force_login(self.professor)
        self.client.post(self.url_colher(tipo=Tipo.USO_DADOS), {"forma": "tablet"})
        nova = self.aluno.autorizacoes.filter(tipo=Tipo.USO_DADOS).exclude(pk=autorizacao.pk).get()
        self.client.post(reverse("autorizacoes:assinar", args=[nova.pk]), {
            "quem": str(self.responsavel.pk), "decisao": "autorizo", "assinatura_dados": data_url(png_de_assinatura()),
        })
        self.client.force_login(self.apoio)
        resposta = self.client.get(reverse("autorizacoes:detalhe", args=[nova.pk]))
        url = reverse("autorizacoes:imagem_assinatura", args=[nova.pk])
        self.assertContains(resposta, f'src="{url}"')
        self.assertContains(resposta, "Confere: o termo, quem assinou, a resposta, a data e a assinatura")
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "image/png")
        b"".join(resposta.streaming_content)
        self.assertTrue(self.eventos(nova, Acao.BAIXOU_ARQUIVO).filter(usuario=self.apoio).exists())
        self.client.force_login(self.so_aulas)
        self.assertEqual(self.client.get(url).status_code, 403)

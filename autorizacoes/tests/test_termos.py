"""Termos de autorização: só quem configura, versões guardadas para sempre, termo usado não se edita (RF-25, LGPD-03)."""
from django.urls import reverse

from .base import Acao, BaseAutorizacoes, Situacao, Termo, Tipo


class ListaDeTermosTestes(BaseAutorizacoes):
    url = reverse("autorizacoes:termos")

    def test_pede_login(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("entrar"), resposta["Location"])

    def test_abre_para_quem_configura(self):
        self.client.force_login(self.supervisao)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "<h1", count=1)
        self.assertContains(resposta, "Uso dos dados (texto provisório)")
        self.assertContains(resposta, "Contato com a escola (texto provisório)")
        self.assertContains(resposta, "Versão 1 vigente", count=2)
        self.assertContains(resposta, "advogado")
        self.assertNotContains(resposta, "Termo de outro serviço")

    def test_403_para_quem_nao_configura(self):
        for pessoa in (self.professor, self.apoio, self.so_aulas):
            self.client.force_login(pessoa)
            self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_tipo_sem_termo_leva_ao_cadastro(self):
        self.termo_uso.delete()
        self.client.force_login(self.supervisao)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "O serviço ainda não tem termo de uso dos dados")
        self.assertContains(resposta, f'{reverse("autorizacoes:termo_novo")}?tipo={Tipo.USO_DADOS}')

    def test_versoes_anteriores_ficam_na_lista(self):
        self.termo_contato.vigente = False
        self.termo_contato.save()
        Termo.objects.create(
            servico=self.servico, tipo=Tipo.CONTATO_ESCOLA, versao_do_termo=2, titulo="Contato versão dois",
            texto="Texto inventado da versão 2.",
        )
        self.client.force_login(self.supervisao)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Versão 2 vigente")
        self.assertContains(resposta, "Versões anteriores")
        self.assertContains(resposta, 'data-label="Versão"')


class NovoTermoTestes(BaseAutorizacoes):
    url = reverse("autorizacoes:termo_novo")

    def test_abre_para_quem_configura(self):
        self.client.force_login(self.supervisao)
        resposta = self.client.get(self.url, {"tipo": Tipo.CONTATO_ESCOLA})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Nova versão do termo")
        self.assertContains(resposta, "a versão 1 deixa de valer")

    def test_403_para_quem_nao_configura(self):
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        resposta = self.client.post(self.url, {"tipo": Tipo.USO_DADOS, "titulo": "Outro", "texto": "Outro texto."})
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(Termo.objects.filter(servico=self.servico).count(), 2)

    def test_base_preenche_titulo_e_texto_so_do_proprio_servico(self):
        self.client.force_login(self.supervisao)
        resposta = self.client.get(self.url, {"base": self.termo_uso.pk})
        self.assertContains(resposta, "Uso dos dados (texto provisório)")
        resposta = self.client.get(self.url, {"base": self.termo_de_fora.pk})
        self.assertNotContains(resposta, "Termo de outro serviço")
        self.assertNotContains(resposta, "Texto inventado de outro serviço.")

    def test_nova_versao_vira_vigente_e_a_anterior_fica_guardada(self):
        autorizacao = self.coleta(tipo=Tipo.CONTATO_ESCOLA)
        self.client.force_login(self.supervisao)
        resposta = self.client.post(self.url, {
            "tipo": Tipo.CONTATO_ESCOLA, "titulo": "Contato com a escola, versão nova",
            "texto": "Texto provisório inventado, versão 2.",
        })
        novo = Termo.objects.get(servico=self.servico, tipo=Tipo.CONTATO_ESCOLA, versao_do_termo=2)
        self.assertRedirects(
            resposta, reverse("autorizacoes:termo_detalhe", args=[novo.pk]), fetch_redirect_response=False
        )
        self.assertTrue(novo.vigente)
        self.termo_contato.refresh_from_db()
        self.assertFalse(self.termo_contato.vigente)
        self.assertEqual(self.termo_contato.texto, TEXTO_GUARDADO)
        autorizacao.refresh_from_db()
        self.assertEqual(autorizacao.termo, self.termo_contato)  # a autorização aponta para a versão que a família viu
        # O outro tipo e o outro serviço não mudam.
        self.termo_uso.refresh_from_db()
        self.termo_de_fora.refresh_from_db()
        self.assertTrue(self.termo_uso.vigente)
        self.assertTrue(self.termo_de_fora.vigente)
        # Trilha: criou a nova e alterou a anterior, com o motivo.
        self.assertTrue(self.eventos(novo, Acao.CRIOU).exists())
        evento = self.eventos(self.termo_contato, Acao.ALTEROU).get()
        self.assertEqual(evento.usuario, self.supervisao)
        self.assertIn("versão 2", evento.motivo)
        self.assertEqual(evento.mudancas["vigente"]["para"], "Não")
        self.assertContains(self.client.get(resposta["Location"]), "A versão 2 é a vigente a partir de agora")

    def test_primeiro_termo_do_tipo_comeca_na_versao_1(self):
        self.client.force_login(self.supervisao)
        Termo.objects.filter(servico=self.servico, tipo=Tipo.USO_DADOS).delete()
        self.client.post(self.url, {"tipo": Tipo.USO_DADOS, "titulo": "Uso dos dados", "texto": "Texto inventado."})
        termo = Termo.objects.get(servico=self.servico, tipo=Tipo.USO_DADOS)
        self.assertEqual(termo.versao_do_termo, 1)
        self.assertTrue(termo.vigente)

    def test_campos_obrigatorios_explicam_o_que_falta(self):
        self.client.force_login(self.supervisao)
        resposta = self.client.post(self.url, {"tipo": Tipo.USO_DADOS, "titulo": "", "texto": ""})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Falta o título do termo")
        self.assertContains(resposta, "Falta o texto do termo")
        self.assertContains(resposta, 'aria-describedby="id_titulo_dica id_titulo_erro"')


TEXTO_GUARDADO = "Texto provisório inventado para teste: autorizo o serviço a falar com a escola da criança."


class DetalheDoTermoTestes(BaseAutorizacoes):
    def test_abre_para_quem_configura_com_texto_e_historico(self):
        self.client.force_login(self.supervisao)
        resposta = self.client.get(reverse("autorizacoes:termo_detalhe", args=[self.termo_uso.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "<h1", count=1)
        self.assertContains(resposta, "autorizo o uso dos dados")
        self.assertContains(resposta, "Vigente")
        self.assertContains(resposta, reverse("autorizacoes:termo_editar", args=[self.termo_uso.pk]))

    def test_403_e_404(self):
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(reverse("autorizacoes:termo_detalhe", args=[self.termo_uso.pk])).status_code, 403)
        self.client.force_login(self.supervisao)
        self.assertEqual(
            self.client.get(reverse("autorizacoes:termo_detalhe", args=[self.termo_de_fora.pk])).status_code, 404
        )

    def test_termo_usado_nao_mostra_editar(self):
        self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.PENDENTE, forma="")
        self.client.force_login(self.supervisao)
        resposta = self.client.get(reverse("autorizacoes:termo_detalhe", args=[self.termo_uso.pk]))
        self.assertNotContains(resposta, reverse("autorizacoes:termo_editar", args=[self.termo_uso.pk]))
        self.assertContains(resposta, "não pode mais mudar")


class EditarTermoTestes(BaseAutorizacoes):
    def url(self, termo=None):
        return reverse("autorizacoes:termo_editar", args=[(termo or self.termo_uso).pk])

    def test_termo_sem_uso_se_corrige_com_motivo_na_trilha(self):
        self.client.force_login(self.supervisao)
        resposta = self.client.get(self.url())
        self.assertEqual(resposta.status_code, 200)
        estado = resposta.context["estado_original"]
        resposta = self.client.post(self.url(), {
            "titulo": "Uso dos dados (texto provisório corrigido)", "texto": TEXTO_GUARDADO_USO,
            "motivo_alteracao": "Corrigi um erro de digitação no título.", "estado_original": estado,
        })
        self.assertRedirects(resposta, reverse("autorizacoes:termo_detalhe", args=[self.termo_uso.pk]))
        self.termo_uso.refresh_from_db()
        self.assertEqual(self.termo_uso.titulo, "Uso dos dados (texto provisório corrigido)")
        evento = self.eventos(self.termo_uso, Acao.ALTEROU).get()
        self.assertEqual(evento.motivo, "Corrigi um erro de digitação no título.")

    def test_edicao_pede_motivo(self):
        self.client.force_login(self.supervisao)
        resposta = self.client.post(self.url(), {"titulo": "Outro título", "texto": TEXTO_GUARDADO_USO})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Conte por que você está alterando")
        self.termo_uso.refresh_from_db()
        self.assertEqual(self.termo_uso.titulo, "Uso dos dados (texto provisório)")

    def test_termo_usado_nao_se_edita_so_nova_versao(self):
        self.coleta(tipo=Tipo.USO_DADOS)
        self.client.force_login(self.supervisao)
        destino = f"{reverse('autorizacoes:termo_novo')}?base={self.termo_uso.pk}"
        self.assertRedirects(self.client.get(self.url()), destino)
        resposta = self.client.post(self.url(), {
            "titulo": "Mudança proibida", "texto": "Outro texto.", "motivo_alteracao": "Tentativa inventada.",
        })
        self.assertRedirects(resposta, destino)
        self.termo_uso.refresh_from_db()
        self.assertEqual(self.termo_uso.titulo, "Uso dos dados (texto provisório)")
        self.assertFalse(self.eventos(self.termo_uso, Acao.ALTEROU).exists())

    def test_403_e_404(self):
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.client.force_login(self.supervisao)
        self.assertEqual(self.client.get(self.url(self.termo_de_fora)).status_code, 404)


TEXTO_GUARDADO_USO = (
    "Texto provisório inventado para teste: autorizo o uso dos dados da criança pelo serviço. "
    "O texto definitivo será escrito pelo advogado."
)

"""Colher a autorização: formas, uma por vez, prova e trilha (RF-25, RF-26, RF-27, RF-64, LGPD-03)."""
import hashlib

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from autorizacoes.regras import libera_contato_com_a_escola

from .base import (
    Acao,
    Autorizacao,
    BaseAutorizacoes,
    Forma,
    Situacao,
    Termo,
    Tipo,
    conversa_txt,
    foto_jpg,
    pdf,
)


class TelaDeColherTestes(BaseAutorizacoes):
    def test_pede_login(self):
        resposta = self.client.get(self.url_colher())
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("entrar"), resposta["Location"])

    def test_abre_para_quem_edita_com_as_formas(self):
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url_colher())
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "<h1", count=1)
        self.assertContains(resposta, "Lia M.")
        self.assertNotContains(resposta, "Lia Inventada Moreira")  # nome completo só no perfil
        for texto in ("Assinatura no tablet", "Papel assinado e fotografado", "Sim por WhatsApp",
                      "Link para o celular", "Registrar como pendente"):
            self.assertContains(resposta, texto)
        self.assertContains(resposta, '<button type="button" class="el-btn el-btn-secondary" disabled>Chega na próxima versão</button>', html=True)
        self.assertNotContains(resposta, "?forma=link")

    def test_403_para_quem_nao_edita_autorizacoes(self):
        for pessoa in (self.apoio, self.so_aulas):
            self.client.force_login(pessoa)
            self.assertEqual(self.client.get(self.url_colher()).status_code, 403)
            resposta = self.client.post(self.url_colher(), {"forma": "pendente"})
            self.assertEqual(resposta.status_code, 403)
        self.assertFalse(Autorizacao.objects.exists())

    def test_404_para_aluno_de_outro_servico_e_tipo_desconhecido(self):
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(self.url_colher(self.aluno_de_fora)).status_code, 404)
        self.assertEqual(self.client.get(reverse("autorizacoes:colher", args=[self.aluno.pk, "outro"])).status_code, 404)

    def test_sem_termo_avisa_e_leva_quem_configura_aos_termos(self):
        self.termo_contato.delete()
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url_colher())
        self.assertContains(resposta, "O serviço ainda não tem um termo de contato com a escola")
        self.assertContains(resposta, "Peça a quem configura o serviço")
        self.assertNotContains(resposta, reverse("autorizacoes:termo_novo"))
        self.assertNotContains(resposta, "?forma=papel")
        self.client.force_login(self.supervisao)
        resposta = self.client.get(self.url_colher())
        self.assertContains(resposta, f'{reverse("autorizacoes:termo_novo")}?tipo={Tipo.CONTATO_ESCOLA}')
        # E nada se colhe sem termo, nem forçando o envio.
        self.client.post(self.url_colher(), {"forma": "pendente"})
        self.assertFalse(Autorizacao.objects.exists())

    def test_cada_forma_abre_uma_por_vez(self):
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url_colher(), {"forma": "papel"})
        self.assertContains(resposta, "Foto do papel assinado")
        self.assertContains(resposta, "Escolher outra forma")
        self.assertNotContains(resposta, "Conversa exportada do WhatsApp")
        resposta = self.client.get(self.url_colher(), {"forma": "tablet"})
        self.assertContains(resposta, "Entregue o tablet ao responsável. Ao terminar, a plataforma pede o seu login de novo.")
        self.assertContains(resposta, 'hx-boost="false"')
        self.assertFalse(Autorizacao.objects.exists())  # só abrir não cria nada

    def test_responsaveis_legais_primeiro_e_so_os_do_aluno(self):
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url_colher(), {"forma": "papel"})
        html = resposta.content.decode()
        self.assertIn("Rita Responsável Inventada (Mãe) · responsável legal", html)
        self.assertIn("Tereza Tia Inventada (Tia ou tio)", html)
        self.assertLess(html.index("Rita Responsável"), html.index("Tereza Tia"))
        self.assertNotIn("Olívia Outra Inventada", html)
        self.assertNotIn("Ivo Responsável de Fora", html)

    def test_quem_nao_ve_a_familia_digita_o_nome(self):
        self.client.force_login(self.sem_familia)
        resposta = self.client.get(self.url_colher(), {"forma": "papel"})
        self.assertNotContains(resposta, "Rita Responsável Inventada")
        self.assertContains(resposta, 'name="nome"')
        self.assertNotContains(resposta, 'name="quem"')


class PapelTestes(BaseAutorizacoes):
    def enviar(self, pessoa=None, tipo=Tipo.CONTATO_ESCOLA, **dados):
        self.client.force_login(pessoa or self.professor)
        envio = {"forma": "papel", "quem": str(self.responsavel.pk), "documento": "RG 00.000.000-0 inventado",
                 "decisao": "autorizou", "arquivo": foto_jpg(), "observacoes": ""}
        envio.update(dados)
        envio = {chave: valor for chave, valor in envio.items() if valor is not None}
        return self.client.post(self.url_colher(tipo=tipo), envio)

    def test_papel_autorizado_fica_valido_com_prova_e_trilha(self):
        resposta = self.enviar()
        self.assertRedirects(
            resposta, reverse("alunos:detalhe", args=[self.aluno.pk]) + "#secao-autorizacoes",
            fetch_redirect_response=False,
        )
        autorizacao = Autorizacao.objects.get()
        self.assertEqual(autorizacao.servico, self.servico)
        self.assertEqual(autorizacao.situacao, Situacao.VALIDA)
        self.assertEqual(autorizacao.forma, Forma.PAPEL)
        self.assertEqual(autorizacao.termo, self.termo_contato)
        self.assertEqual(autorizacao.responsavel, self.responsavel)
        self.assertEqual(autorizacao.responsavel_nome, "Rita Responsável Inventada")
        self.assertEqual(autorizacao.responsavel_documento, "RG 00.000.000-0 inventado")
        self.assertEqual(autorizacao.colhida_por, self.professor)
        self.assertIsNotNone(autorizacao.colhida_em)
        with autorizacao.arquivo.open("rb") as aberto:
            self.assertEqual(autorizacao.impressao_digital, hashlib.sha256(aberto.read()).hexdigest())
        self.assertTrue(autorizacao.arquivo.name.startswith(f"servico_{self.servico.pk}/autorizacoes/"))
        evento = self.eventos(autorizacao, Acao.ASSINOU).get()
        self.assertEqual(evento.usuario, self.professor)
        self.assertEqual(evento.aluno_id, self.aluno.pk)
        self.assertIn("autorizou", evento.descricao)
        self.assertEqual(evento.mudancas["situacao"]["para"], "Válida")
        self.assertTrue(libera_contato_com_a_escola(self.aluno))

    def test_papel_em_pdf_e_aceito(self):
        self.enviar(arquivo=pdf())
        autorizacao = Autorizacao.objects.get()
        self.assertTrue(autorizacao.arquivo.name.endswith(".pdf"))

    def test_papel_nao_autorizado_fica_recusado(self):
        resposta = self.enviar(decisao="nao_autorizou")
        self.assertEqual(resposta.status_code, 302)
        autorizacao = Autorizacao.objects.get()
        self.assertEqual(autorizacao.situacao, Situacao.RECUSADA)
        self.assertFalse(libera_contato_com_a_escola(self.aluno))

    def test_foto_do_papel_e_obrigatoria(self):
        resposta = self.enviar(arquivo=None)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Falta a foto do papel assinado. Fotografe o papel e envie a foto.")
        self.assertContains(resposta, 'href="#id_arquivo"')
        self.assertFalse(Autorizacao.objects.exists())

    def test_arquivo_que_nao_e_foto_nem_pdf_e_recusado(self):
        falso = SimpleUploadedFile("papel.jpg", b"isto nao e uma foto", content_type="image/jpeg")
        resposta = self.enviar(arquivo=falso)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Envie uma foto (JPG, PNG ou WEBP) ou um PDF.")
        self.assertFalse(Autorizacao.objects.exists())

    def test_outra_pessoa_com_nome_digitado(self):
        self.enviar(quem="outra", nome="Avó Inventada da Silva")
        autorizacao = Autorizacao.objects.get()
        self.assertIsNone(autorizacao.responsavel)
        self.assertEqual(autorizacao.responsavel_nome, "Avó Inventada da Silva")

    def test_outra_pessoa_sem_nome_explica_o_que_fazer(self):
        resposta = self.enviar(quem="outra", nome="")
        self.assertContains(resposta, "Falta o nome de quem autorizou")
        self.assertFalse(Autorizacao.objects.exists())

    def test_responsavel_de_outro_aluno_ou_servico_nao_e_aceito(self):
        for responsavel in (self.responsavel_do_outro, self.responsavel_de_fora):
            resposta = self.enviar(quem=str(responsavel.pk))
            self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Autorizacao.objects.exists())

    def test_nova_coleta_nao_apaga_a_anterior(self):
        self.enviar(decisao="nao_autorizou")
        primeira = Autorizacao.objects.get()
        impressao = primeira.impressao_digital
        self.enviar(arquivo=foto_jpg("outra.jpg"))
        self.assertEqual(Autorizacao.objects.count(), 2)
        primeira.refresh_from_db()
        self.assertEqual(primeira.situacao, Situacao.RECUSADA)
        self.assertEqual(primeira.impressao_digital, impressao)
        self.assertTrue(primeira.arquivo)
        atual = Autorizacao.objects.exclude(pk=primeira.pk).get()
        self.assertEqual(atual.situacao, Situacao.VALIDA)
        self.assertTrue(libera_contato_com_a_escola(self.aluno))

    def test_autorizacoes_separadas_por_tipo(self):
        self.enviar(tipo=Tipo.USO_DADOS, decisao="autorizou")
        self.enviar(tipo=Tipo.CONTATO_ESCOLA, decisao="nao_autorizou")
        uso = Autorizacao.objects.get(tipo=Tipo.USO_DADOS)
        contato = Autorizacao.objects.get(tipo=Tipo.CONTATO_ESCOLA)
        self.assertEqual(uso.situacao, Situacao.VALIDA)
        self.assertEqual(uso.termo, self.termo_uso)
        self.assertEqual(contato.situacao, Situacao.RECUSADA)
        self.assertFalse(libera_contato_com_a_escola(self.aluno))

    def test_com_autorizacao_valida_nao_colhe_de_novo(self):
        self.coleta()
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url_colher())
        self.assertContains(resposta, "já está válida")
        self.assertNotContains(resposta, "?forma=papel")
        self.enviar()
        self.assertEqual(Autorizacao.objects.count(), 1)


class WhatsappTestes(BaseAutorizacoes):
    def enviar(self, tipo=Tipo.CONTATO_ESCOLA, **dados):
        self.client.force_login(self.professor)
        envio = {"forma": "whatsapp", "quem": str(self.responsavel.pk), "arquivo": conversa_txt(),
                 "observacoes": "A mãe respondeu sim às 14h, do número cadastrado."}
        envio.update(dados)
        return self.client.post(self.url_colher(tipo=tipo), envio)

    def test_sim_por_whatsapp_e_provisorio_e_libera_o_contato(self):
        resposta = self.enviar()
        self.assertEqual(resposta.status_code, 302)
        autorizacao = Autorizacao.objects.get()
        self.assertEqual(autorizacao.situacao, Situacao.PROVISORIA)
        self.assertEqual(autorizacao.forma, Forma.WHATSAPP)
        self.assertEqual(autorizacao.observacoes, "A mãe respondeu sim às 14h, do número cadastrado.")
        self.assertTrue(autorizacao.arquivo.name.endswith(".txt"))
        self.assertEqual(len(autorizacao.impressao_digital), 64)
        self.assertTrue(self.eventos(autorizacao, Acao.ASSINOU).exists())
        self.assertTrue(libera_contato_com_a_escola(self.aluno))
        mensagem = self.client.get(resposta["Location"])
        self.assertContains(mensagem, "Sim provisório registrado. O contato com a escola já está liberado.")

    def test_aceita_pdf_e_foto(self):
        self.enviar(tipo=Tipo.CONTATO_ESCOLA, arquivo=pdf("conversa.pdf"))
        self.enviar(tipo=Tipo.USO_DADOS, arquivo=foto_jpg("print.jpg"))
        self.assertTrue(Autorizacao.objects.get(tipo=Tipo.CONTATO_ESCOLA).arquivo.name.endswith(".pdf"))
        self.assertTrue(Autorizacao.objects.get(tipo=Tipo.USO_DADOS).arquivo.name.endswith(".jpg"))

    def test_conversa_e_obrigatoria_e_o_tipo_e_conferido(self):
        resposta = self.enviar(arquivo="")
        self.assertContains(resposta, "Falta a conversa do WhatsApp")
        zip_falso = SimpleUploadedFile("conversa.zip", b"PK\x03\x04 inventado", content_type="application/zip")
        resposta = self.enviar(arquivo=zip_falso)
        self.assertContains(resposta, "exporte de novo escolhendo “sem mídia”")
        binario = SimpleUploadedFile("conversa.txt", b"\x00\x01\x02 inventado", content_type="text/plain")
        resposta = self.enviar(arquivo=binario)
        self.assertContains(resposta, "Envie a conversa exportada do WhatsApp")
        self.assertFalse(Autorizacao.objects.exists())

    def test_arquivo_grande_demais_e_recusado(self):
        with self.settings(ENTRELACO_TAMANHO_MAXIMO_ARQUIVO=10):
            resposta = self.enviar()
        self.assertContains(resposta, "O arquivo passa de")
        self.assertFalse(Autorizacao.objects.exists())

    def test_com_sim_provisorio_o_definitivo_e_no_tablet_ou_no_papel(self):
        self.coleta(situacao=Situacao.PROVISORIA, forma=Forma.WHATSAPP)
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url_colher())
        self.assertContains(resposta, "Colher o sim definitivo")
        self.assertContains(resposta, "?forma=tablet")
        self.assertContains(resposta, "?forma=papel")
        self.assertNotContains(resposta, "?forma=whatsapp")
        self.assertNotContains(resposta, "?forma=pendente")
        self.enviar()
        self.client.post(self.url_colher(), {"forma": "pendente"})
        self.assertEqual(Autorizacao.objects.count(), 1)


class PendenteTestes(BaseAutorizacoes):
    def test_registrar_como_pendente(self):
        self.client.force_login(self.professor)
        resposta = self.client.post(self.url_colher(tipo=Tipo.USO_DADOS), {
            "forma": "pendente", "observacoes": "A mãe quer conversar com o pai antes.",
        })
        self.assertEqual(resposta.status_code, 302)
        autorizacao = Autorizacao.objects.get()
        self.assertEqual(autorizacao.situacao, Situacao.PENDENTE)
        self.assertEqual(autorizacao.forma, "")
        self.assertEqual(autorizacao.colhida_por, self.professor)
        self.assertEqual(autorizacao.termo, self.termo_uso)
        self.assertIsNone(autorizacao.colhida_em)
        evento = self.eventos(autorizacao, Acao.CRIOU).get()
        self.assertEqual(evento.aluno_id, self.aluno.pk)

    def test_forma_desconhecida_volta_para_a_escolha(self):
        self.client.force_login(self.professor)
        resposta = self.client.post(self.url_colher(), {"forma": "link"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Como a família vai responder?")
        self.assertFalse(Autorizacao.objects.exists())

    def test_termo_de_outro_servico_nunca_entra(self):
        Termo.objects.filter(servico=self.servico, tipo=Tipo.CONTATO_ESCOLA).delete()
        self.client.force_login(self.professor)
        self.client.post(self.url_colher(), {"forma": "pendente"})
        self.assertFalse(Autorizacao.objects.exists())

"""Modo assinatura no tablet (SEG-08, LGPD-03): a sessão fica presa no termo e termina pedindo o login de novo."""
import base64

from django.contrib.auth import SESSION_KEY
from django.urls import reverse

from autorizacoes import regras
from core.middleware import CHAVE_MODO_ASSINATURA

from .base import (
    Acao,
    Autorizacao,
    BaseAutorizacoes,
    Forma,
    Situacao,
    Tipo,
    data_url,
    png_de_assinatura,
)

NAVEGADOR = "Mozilla/5.0 (Linux; Android 14; Tablet Inventado) Navegador de teste"


class BaseAssinatura(BaseAutorizacoes):
    def comecar(self, tipo=Tipo.USO_DADOS, pessoa=None):
        """O professor escolhe a assinatura no tablet e confirma: a sessão entra no modo assinatura."""
        self.client.force_login(pessoa or self.professor)
        resposta = self.client.post(self.url_colher(tipo=tipo), {"forma": "tablet"})
        autorizacao = Autorizacao.objects.filter(tipo=tipo).latest("criado_em")
        return resposta, autorizacao

    def url_assinar(self, autorizacao):
        return reverse("autorizacoes:assinar", args=[autorizacao.pk])

    def assinar(self, autorizacao, **dados):
        envio = {
            "quem": str(self.responsavel.pk), "documento": "CPF inventado 000", "decisao": "autorizo",
            "assinatura_dados": data_url(png_de_assinatura()),
        }
        envio.update(dados)
        return self.client.post(self.url_assinar(autorizacao), envio, HTTP_USER_AGENT=NAVEGADOR)

    def logado(self):
        return SESSION_KEY in self.client.session


class EntrarNoModoTestes(BaseAssinatura):
    def test_confirmar_cria_a_pendente_e_prende_a_sessao(self):
        resposta, autorizacao = self.comecar()
        url = self.url_assinar(autorizacao)
        self.assertRedirects(resposta, url, fetch_redirect_response=False)
        self.assertEqual(self.client.session[CHAVE_MODO_ASSINATURA], url)
        self.assertEqual(autorizacao.situacao, Situacao.PENDENTE)
        self.assertEqual(autorizacao.forma, Forma.TABLET)
        self.assertEqual(autorizacao.termo, self.termo_uso)
        self.assertEqual(autorizacao.colhida_por, self.professor)
        self.assertTrue(self.eventos(autorizacao, Acao.CRIOU).exists())

    def test_qualquer_outra_url_volta_para_o_termo(self):
        _, autorizacao = self.comecar()
        url = self.url_assinar(autorizacao)
        for outra in (reverse("inicio"), reverse("alunos:detalhe", args=[self.aluno.pk]),
                      reverse("autorizacoes:detalhe", args=[autorizacao.pk]), reverse("agenda"),
                      reverse("entrar"), self.url_colher()):
            self.assertRedirects(self.client.get(outra), url, fetch_redirect_response=False)
        # Nem sair pelo menu: só terminando ou cancelando a assinatura.
        self.assertRedirects(self.client.post(reverse("sair")), url, fetch_redirect_response=False)
        self.assertTrue(self.logado())

    def test_tela_mostra_so_o_termo_e_o_primeiro_nome(self):
        _, autorizacao = self.comecar()
        resposta = self.client.get(self.url_assinar(autorizacao))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "<h1", count=1)
        self.assertContains(resposta, "Uso dos dados (texto provisório)")
        self.assertContains(resposta, "autorizo o uso dos dados da criança")
        self.assertContains(resposta, "<strong>Lia</strong>", html=True)
        for escondido in ("Moreira", "Lia M.", "12B", "Oncologia", "Diagnóstico inventado", "el-sidenav",
                          "el-bottomnav", reverse("alunos:lista"), "Paula Professora"):
            self.assertNotContains(resposta, escondido)
        self.assertContains(resposta, 'id="quadro-assinatura"')
        self.assertContains(resposta, 'data-destino="id_assinatura_dados"')
        self.assertContains(resposta, '<input type="hidden" id="id_assinatura_dados" name="assinatura_dados">', html=True)
        self.assertContains(resposta, 'data-limpar-assinatura="quadro-assinatura"')
        self.assertContains(resposta, "Rita Responsável Inventada")
        self.assertNotContains(resposta, "Tereza Tia Inventada")  # só responsáveis legais
        self.assertContains(resposta, "Autorizo")
        self.assertContains(resposta, "Não autorizo")
        self.assertContains(resposta, "confirmo que ele autorizou em voz alta na minha frente")

    def test_retomar_assinatura_interrompida_pede_para_entregar_o_tablet(self):
        autorizacao = self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.PENDENTE, forma=Forma.TABLET)
        self.client.force_login(self.professor)
        url = self.url_assinar(autorizacao)
        resposta = self.client.get(url)
        self.assertContains(resposta, "Entregue o tablet ao responsável. Ao terminar, a plataforma pede o seu login de novo.")
        self.assertNotIn(CHAVE_MODO_ASSINATURA, self.client.session)
        resposta = self.client.post(url, {"acao": "comecar"})
        self.assertRedirects(resposta, url, fetch_redirect_response=False)
        self.assertEqual(self.client.session[CHAVE_MODO_ASSINATURA], url)

    def test_so_quem_edita_autorizacoes_entra_no_modo(self):
        autorizacao = self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.PENDENTE, forma=Forma.TABLET)
        self.client.force_login(self.apoio)
        self.assertEqual(self.client.post(self.url_colher(tipo=Tipo.USO_DADOS), {"forma": "tablet"}).status_code, 403)
        self.assertEqual(self.client.get(self.url_assinar(autorizacao)).status_code, 403)
        self.assertEqual(self.client.post(self.url_assinar(autorizacao), {"acao": "comecar"}).status_code, 403)
        self.assertNotIn(CHAVE_MODO_ASSINATURA, self.client.session)

    def test_autorizacao_de_outro_servico_da_404(self):
        de_fora = self.coleta(
            aluno=self.aluno_de_fora, situacao=Situacao.PENDENTE, forma=Forma.TABLET, termo=self.termo_de_fora,
            colhida_por=self.de_fora,
        )
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(self.url_assinar(de_fora)).status_code, 404)
        self.assertEqual(self.client.post(self.url_assinar(de_fora), {"acao": "comecar"}).status_code, 404)

    def test_so_a_pendente_de_tablet_pode_ser_assinada(self):
        for situacao, forma in ((Situacao.VALIDA, Forma.TABLET), (Situacao.PENDENTE, "")):
            autorizacao = self.coleta(tipo=Tipo.USO_DADOS, situacao=situacao, forma=forma)
            self.client.force_login(self.professor)
            resposta = self.client.post(self.url_assinar(autorizacao), {"acao": "comecar"})
            self.assertRedirects(
                resposta, reverse("autorizacoes:detalhe", args=[autorizacao.pk]), fetch_redirect_response=False
            )
            self.assertNotIn(CHAVE_MODO_ASSINATURA, self.client.session)


class AssinarTestes(BaseAssinatura):
    def test_assinar_grava_a_prova_e_encerra_a_sessao(self):
        _, autorizacao = self.comecar()
        png = png_de_assinatura()
        resposta = self.assinar(autorizacao, assinatura_dados=data_url(png))
        self.assertRedirects(resposta, reverse("entrar") + "?assinatura=ok", fetch_redirect_response=False)
        self.assertFalse(self.logado())
        self.assertNotIn(CHAVE_MODO_ASSINATURA, self.client.session)

        autorizacao.refresh_from_db()
        self.assertEqual(autorizacao.situacao, Situacao.VALIDA)
        self.assertEqual(autorizacao.responsavel, self.responsavel)
        self.assertEqual(autorizacao.responsavel_nome, "Rita Responsável Inventada")
        self.assertEqual(autorizacao.responsavel_documento, "CPF inventado 000")
        self.assertEqual(autorizacao.aparelho, NAVEGADOR)
        self.assertIsNotNone(autorizacao.colhida_em)
        with autorizacao.assinatura.open("rb") as aberto:
            self.assertEqual(aberto.read(), png)
        esperada = regras.impressao_digital_do_tablet(
            texto_do_termo=self.termo_uso.texto, versao_do_termo=1, nome="Rita Responsável Inventada",
            documento="CPF inventado 000", decisao="autorizo", colhida_em=autorizacao.colhida_em, assinatura=png,
        )
        self.assertEqual(autorizacao.impressao_digital, esperada)
        self.assertTrue(regras.conferir_impressao_digital(autorizacao))

        evento = self.eventos(autorizacao, Acao.ASSINOU).get()
        self.assertEqual(evento.usuario, self.professor)  # quem estava logado: o professor
        self.assertEqual(evento.aluno_id, self.aluno.pk)
        self.assertEqual(evento.mudancas["situacao"]["para"], "Válida")
        self.assertTrue(self.eventos(autorizacao).filter(acao=Acao.ASSINOU).exists())

        # A tela de entrar avisa, e o resto da plataforma pede login de novo.
        self.assertContains(self.client.get(resposta["Location"]), "Resposta registrada")
        resposta = self.client.get(reverse("inicio"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("entrar"), resposta["Location"])

    def test_assinatura_e_obrigatoria_para_autorizar(self):
        _, autorizacao = self.comecar()
        resposta = self.assinar(autorizacao, assinatura_dados="")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Falta a assinatura")
        self.assertContains(resposta, 'href="#quadro-assinatura"')
        self.assertContains(resposta, 'aria-describedby="dica-assinatura erro-assinatura"')
        autorizacao.refresh_from_db()
        self.assertEqual(autorizacao.situacao, Situacao.PENDENTE)
        self.assertTrue(self.logado())

    def test_quem_nao_consegue_desenhar_autoriza_em_voz_alta(self):
        _, autorizacao = self.comecar()
        resposta = self.assinar(autorizacao, assinatura_dados="", sem_assinatura_com_o_dedo="on")
        self.assertRedirects(resposta, reverse("entrar") + "?assinatura=ok", fetch_redirect_response=False)
        autorizacao.refresh_from_db()
        self.assertEqual(autorizacao.situacao, Situacao.VALIDA)
        self.assertFalse(autorizacao.assinatura)
        self.assertIn("autorizou em voz alta", autorizacao.observacoes)
        self.assertIn("Paula Professora Inventada", autorizacao.observacoes)
        self.assertTrue(regras.conferir_impressao_digital(autorizacao))

    def test_nao_autorizo_fica_recusada(self):
        _, autorizacao = self.comecar(tipo=Tipo.CONTATO_ESCOLA)
        resposta = self.assinar(autorizacao, decisao="nao_autorizo", assinatura_dados="")
        self.assertEqual(resposta.status_code, 302)
        autorizacao.refresh_from_db()
        self.assertEqual(autorizacao.situacao, Situacao.RECUSADA)
        self.assertTrue(regras.conferir_impressao_digital(autorizacao))
        self.assertFalse(regras.libera_contato_com_a_escola(self.aluno))

    def test_nome_digitado_quando_nao_esta_na_lista(self):
        _, autorizacao = self.comecar()
        self.assinar(autorizacao, quem="outra", nome="Avó Inventada Pereira", documento="")
        autorizacao.refresh_from_db()
        self.assertIsNone(autorizacao.responsavel)
        self.assertEqual(autorizacao.responsavel_nome, "Avó Inventada Pereira")

    def test_responsavel_que_nao_e_legal_ou_de_outro_aluno_nao_e_aceito(self):
        _, autorizacao = self.comecar()
        for responsavel in (self.tia, self.responsavel_do_outro):
            resposta = self.assinar(autorizacao, quem=str(responsavel.pk))
            self.assertEqual(resposta.status_code, 200)
        autorizacao.refresh_from_db()
        self.assertEqual(autorizacao.situacao, Situacao.PENDENTE)

    def test_png_invalido_e_recusado(self):
        _, autorizacao = self.comecar()
        invalidos = [
            "data:image/png;base64,isto não é base64!",
            "data:image/jpeg;base64," + base64.b64encode(png_de_assinatura()).decode(),
            "data:image/png;base64," + base64.b64encode(b"GIF89a inventado").decode(),
            "data:image/png;base64," + base64.b64encode(png_de_assinatura()[:40]).decode(),
            "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * (1024 * 1024 + 10)).decode(),
        ]
        for texto in invalidos:
            resposta = self.assinar(autorizacao, assinatura_dados=texto)
            self.assertEqual(resposta.status_code, 200, texto[:40])
            self.assertContains(resposta, "Toque em Limpar")
        autorizacao.refresh_from_db()
        self.assertEqual(autorizacao.situacao, Situacao.PENDENTE)
        self.assertFalse(autorizacao.assinatura)

    def test_cancelar_deixa_pendente_e_encerra_a_sessao(self):
        _, autorizacao = self.comecar()
        resposta = self.client.post(self.url_assinar(autorizacao), {"acao": "cancelar"})
        self.assertRedirects(resposta, reverse("entrar"), fetch_redirect_response=False)
        self.assertFalse(self.logado())
        autorizacao.refresh_from_db()
        self.assertEqual(autorizacao.situacao, Situacao.PENDENTE)
        self.assertTrue(self.eventos(autorizacao, Acao.OUTRO).filter(descricao__icontains="cancelou").exists())
        self.assertContains(self.client.get(reverse("entrar")), "Assinatura cancelada")

    def test_autorizacao_que_deixou_de_esperar_libera_o_tablet(self):
        _, autorizacao = self.comecar()
        Autorizacao.objects.filter(pk=autorizacao.pk).update(situacao=Situacao.RECUSADA)
        resposta = self.client.get(self.url_assinar(autorizacao))
        self.assertRedirects(resposta, reverse("entrar"), fetch_redirect_response=False)
        self.assertFalse(self.logado())

    def test_nova_coleta_no_tablet_nao_apaga_a_anterior(self):
        anterior = self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.RECUSADA, forma=Forma.PAPEL)
        _, autorizacao = self.comecar()
        self.assinar(autorizacao)
        anterior.refresh_from_db()
        self.assertEqual(anterior.situacao, Situacao.RECUSADA)
        self.assertEqual(Autorizacao.objects.filter(tipo=Tipo.USO_DADOS).count(), 2)

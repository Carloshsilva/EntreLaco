"""Pessoas da equipe: lista, cadastro, link de senha, edição, papel, desativar e reativar."""
from unittest import mock
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core import mail
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import EventoAuditoria, Vinculo
from core.registro import menu_para
from core.testes import criar_papel, criar_pessoa
from equipe.edicao import assinar_estado
from equipe.formularios import PessoaEditarForm

from .base import EquipeTestCase

Usuario = get_user_model()
Acao = EventoAuditoria.Acao


class ListaDePessoasTestes(EquipeTestCase):
    def test_abre_para_quem_cuida_da_equipe(self):
        for pessoa in [self.supervisao, self.coordenacao]:
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                resposta = self.client.get(reverse("equipe:pessoas"))
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, "Paula Professora Inventada")
                self.assertContains(resposta, "abel@exemplo.org")
                self.assertNotContains(resposta, "Flora De Fora")
                self.assertContains(resposta, "<h1", count=1)

    def test_apoio_e_professor_nao_veem_a_equipe(self):
        for pessoa in [self.apoio, self.professor]:
            self.entrar(pessoa)
            for nome, args in [
                ("equipe:pessoas", []),
                ("equipe:pessoa_nova", []),
                ("equipe:pessoa_detalhe", [self.coordenacao.pk]),
                ("equipe:pessoa_editar", [self.coordenacao.pk]),
                ("equipe:pessoa_desativar", [self.coordenacao.pk]),
            ]:
                with self.subTest(pessoa=pessoa.nome, tela=nome):
                    self.assertEqual(self.client.get(reverse(nome, args=args)).status_code, 403)
            for nome in ["equipe:pessoa_link_senha", "equipe:pessoa_reativar"]:
                with self.subTest(pessoa=pessoa.nome, acao=nome):
                    self.assertEqual(self.client.post(reverse(nome, args=[self.coordenacao.pk])).status_code, 403)

    def test_menu_mostra_equipe_so_para_quem_cuida_dela(self):
        class Pedido:
            resolver_match = None

        for pessoa, ve in [(self.coordenacao, True), (self.apoio, False)]:
            pedido = Pedido()
            vinculo = pessoa.vinculos.get()
            from core.permissoes import Acesso

            pedido.acesso = Acesso.do_papel(vinculo.papel)
            pedido.servico = self.servico
            urls = [item["url"] for item in menu_para(pedido)]
            self.assertEqual(reverse("equipe:pessoas") in urls, ve)

    def test_busca_por_nome_e_trecho_htmx(self):
        self.entrar(self.coordenacao)
        resposta = self.client.get(reverse("equipe:pessoas"), {"q": "paula"})
        self.assertContains(resposta, "Paula Professora Inventada")
        self.assertNotContains(resposta, "Abel Apoio")
        trecho = self.client.get(
            reverse("equipe:pessoas"), {"q": "abel"}, HTTP_HX_REQUEST="true", HTTP_HX_TARGET="resultados"
        )
        self.assertEqual(trecho.status_code, 200)
        self.assertNotContains(trecho, "<html")
        self.assertContains(trecho, "Abel Apoio Inventado")
        self.assertNotContains(trecho, "Paula Professora")

    def test_filtro_de_situacao(self):
        Vinculo.objects.filter(usuario=self.apoio, servico=self.servico).update(ativo=False)
        self.entrar(self.coordenacao)
        self.assertNotContains(self.client.get(reverse("equipe:pessoas")), "Abel Apoio")
        resposta = self.client.get(reverse("equipe:pessoas"), {"situacao": "desativadas"})
        self.assertContains(resposta, "Abel Apoio")
        self.assertContains(resposta, "Desativada")

    def test_lista_sem_consulta_por_linha(self):
        self.entrar(self.coordenacao)
        self.client.get(reverse("equipe:pessoas"))
        with CaptureQueriesContext(connection) as poucas:
            self.client.get(reverse("equipe:pessoas"))
        for numero in range(15):
            criar_pessoa(self.servico, self.papel_professor, nome=f"Pessoa Fictícia {numero}")
        with CaptureQueriesContext(connection) as muitas:
            resposta = self.client.get(reverse("equipe:pessoas"))
        self.assertContains(resposta, "Pessoa Fictícia 14")
        self.assertEqual(len(poucas), len(muitas))


class DetalheDaPessoaTestes(EquipeTestCase):
    def test_abre_com_dados_e_historico(self):
        self.entrar(self.coordenacao)
        resposta = self.client.get(reverse("equipe:pessoa_detalhe", args=[self.professor.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "paula@exemplo.org")
        self.assertContains(resposta, "Professor")
        self.assertContains(resposta, "Histórico")
        self.assertContains(resposta, f"{reverse('agenda')}?pessoa={self.professor.pk}")

    def test_pessoa_de_outro_servico_da_404(self):
        self.entrar(self.supervisao)
        for nome in ["equipe:pessoa_detalhe", "equipe:pessoa_editar", "equipe:pessoa_desativar", "equipe:professor"]:
            with self.subTest(tela=nome):
                self.assertEqual(self.client.get(reverse(nome, args=[self.de_fora.pk])).status_code, 404)
        for nome in ["equipe:pessoa_link_senha", "equipe:pessoa_reativar"]:
            with self.subTest(acao=nome):
                self.assertEqual(self.client.post(reverse(nome, args=[self.de_fora.pk])).status_code, 404)

    def test_quem_so_cuida_da_equipe_nao_ve_botoes_para_quem_configura(self):
        self.entrar(self.coordenacao)
        resposta = self.client.get(reverse("equipe:pessoa_detalhe", args=[self.supervisao.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, reverse("equipe:pessoa_editar", args=[self.supervisao.pk]))
        self.assertNotContains(resposta, reverse("equipe:pessoa_desativar", args=[self.supervisao.pk]))
        self.assertNotContains(resposta, reverse("equipe:pessoa_link_senha", args=[self.supervisao.pk]))
        self.assertEqual(self.client.get(reverse("equipe:pessoa_editar", args=[self.supervisao.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("equipe:pessoa_desativar", args=[self.supervisao.pk])).status_code, 403)

    def test_na_propria_tela_nao_aparece_desativar(self):
        self.entrar(self.coordenacao)
        resposta = self.client.get(reverse("equipe:pessoa_detalhe", args=[self.coordenacao.pk]))
        self.assertContains(resposta, "(você)")
        self.assertNotContains(resposta, reverse("equipe:pessoa_desativar", args=[self.coordenacao.pk]))
        self.assertNotContains(resposta, reverse("equipe:pessoa_link_senha", args=[self.coordenacao.pk]))


class CadastrarPessoaTestes(EquipeTestCase):
    def dados(self, **extra):
        dados = {
            "email": "nina.nova@exemplo.org",
            "nome": "Nina Nova Inventada",
            "whatsapp_trabalho": "(11) 90000-0001",
            "papel": self.papel_professor.pk,
        }
        dados.update(extra)
        return dados

    def test_abre_o_formulario(self):
        self.entrar(self.coordenacao)
        resposta = self.client.get(reverse("equipe:pessoa_nova"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "WhatsApp de trabalho")
        self.assertContains(resposta, "(obrigatório)")

    def test_cadastra_sem_senha_e_mostra_o_link_uma_vez(self):
        self.entrar(self.coordenacao)
        resposta = self.client.post(reverse("equipe:pessoa_nova"), self.dados())
        nova = Usuario.objects.get(email="nina.nova@exemplo.org")
        self.assertRedirects(resposta, reverse("equipe:pessoa_detalhe", args=[nova.pk]), fetch_redirect_response=False)
        self.assertFalse(nova.has_usable_password())
        self.assertEqual(nova.whatsapp_trabalho, "(11) 90000-0001")
        vinculo = Vinculo.objects.get(usuario=nova, servico=self.servico)
        self.assertEqual(vinculo.papel, self.papel_professor)
        self.assertTrue(self.eventos(acao=Acao.CRIOU, modelo="core.Usuario", objeto_id=str(nova.pk)).exists())
        self.assertTrue(self.eventos(acao=Acao.CRIOU, modelo="core.Vinculo", objeto_id=str(vinculo.pk)).exists())

        tela = self.client.get(reverse("equipe:pessoa_detalhe", args=[nova.pk]))
        link = tela.context["link"]["link"]
        self.assertIn("/senha/definir/", link)
        self.assertContains(tela, link)
        self.assertContains(tela, "Copiar link")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(link, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ["nina.nova@exemplo.org"])

        de_novo = self.client.get(reverse("equipe:pessoa_detalhe", args=[nova.pk]))
        self.assertNotContains(de_novo, link)
        self.assertNotContains(de_novo, "Copiar link")

    def test_link_de_senha_funciona(self):
        self.entrar(self.coordenacao)
        self.client.post(reverse("equipe:pessoa_nova"), self.dados())
        nova = Usuario.objects.get(email="nina.nova@exemplo.org")
        link = self.client.get(reverse("equipe:pessoa_detalhe", args=[nova.pk])).context["link"]["link"]

        navegador_da_nina = Client()
        caminho = urlparse(link).path
        resposta = navegador_da_nina.get(caminho)
        self.assertEqual(resposta.status_code, 302)
        formulario = navegador_da_nina.get(resposta["Location"])
        self.assertEqual(formulario.status_code, 200)
        self.assertContains(formulario, "Salvar senha")
        senha = "uma senha nova e longa 42"
        resposta = navegador_da_nina.post(resposta["Location"], {"new_password1": senha, "new_password2": senha})
        self.assertRedirects(resposta, reverse("senha_definida"))
        nova.refresh_from_db()
        self.assertTrue(nova.check_password(senha))
        entrou = navegador_da_nina.post(reverse("entrar"), {"email": "nina.nova@exemplo.org", "senha": senha})
        self.assertRedirects(entrou, reverse("inicio"), fetch_redirect_response=False)

    def test_email_de_outro_servico_so_cria_o_vinculo(self):
        self.entrar(self.supervisao)
        total = Usuario.objects.count()
        resposta = self.client.post(
            reverse("equipe:pessoa_nova"), self.dados(email="FLORA@exemplo.org", nome="Outro Nome Qualquer")
        )
        self.assertRedirects(resposta, reverse("equipe:pessoa_detalhe", args=[self.de_fora.pk]))
        self.assertEqual(Usuario.objects.count(), total)
        self.de_fora.refresh_from_db()
        self.assertEqual(self.de_fora.nome, "Flora De Fora Inventada")
        self.assertTrue(Vinculo.objects.filter(usuario=self.de_fora, servico=self.servico, ativo=True).exists())
        self.assertTrue(Vinculo.objects.filter(usuario=self.de_fora, servico=self.outro_servico, ativo=True).exists())
        self.assertEqual(len(mail.outbox), 0)
        tela = self.client.get(reverse("equipe:pessoa_detalhe", args=[self.de_fora.pk]))
        self.assertIsNone(tela.context["link"])
        # Quem também é de outro serviço recebe o link só no próprio e-mail, nunca na tela desta equipe.
        self.assertContains(tela, "Mandar link de senha por e-mail")
        self.assertContains(tela, "Ela já criou a senha")
        resposta = self.client.post(reverse("equipe:pessoa_link_senha", args=[self.de_fora.pk]))
        self.assertRedirects(resposta, reverse("equipe:pessoa_detalhe", args=[self.de_fora.pk]),
                             fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["flora@exemplo.org"])
        depois = self.client.get(reverse("equipe:pessoa_detalhe", args=[self.de_fora.pk]))
        self.assertIsNone(depois.context["link"])
        self.assertNotContains(depois, "/senha/definir/")

    def test_email_de_quem_ainda_nao_criou_a_senha_em_outro_servico(self):
        sem_senha = Usuario.objects.create_user(email="otto.sem.senha@exemplo.org", password=None,
                                                nome="Otto Sem Senha Inventado")
        Vinculo.objects.create(usuario=sem_senha, servico=self.outro_servico, papel=self.de_fora.vinculos.get().papel)
        self.entrar(self.coordenacao)
        resposta = self.client.post(reverse("equipe:pessoa_nova"), self.dados(email="otto.sem.senha@exemplo.org"))
        self.assertRedirects(resposta, reverse("equipe:pessoa_detalhe", args=[sem_senha.pk]),
                             fetch_redirect_response=False)
        # O link vai para o e-mail dela, sem aparecer na tela de quem cadastrou.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["otto.sem.senha@exemplo.org"])
        tela = self.client.get(reverse("equipe:pessoa_detalhe", args=[sem_senha.pk]))
        self.assertIsNone(tela.context["link"])
        self.assertNotContains(tela, "/senha/definir/")
        self.assertContains(tela, "foi mandado para otto.sem.senha@exemplo.org")
        self.assertContains(tela, "Ela também trabalha em outro serviço, então o link vai só para o e-mail dela.")
        self.assertContains(tela, "Mandar link de senha por e-mail")
        self.assertTrue(self.eventos(acao=Acao.OUTRO, objeto_id=str(sem_senha.pk),
                                     descricao__startswith="Mandou por e-mail").exists())

    def test_email_que_ja_esta_na_equipe(self):
        self.entrar(self.coordenacao)
        resposta = self.client.post(reverse("equipe:pessoa_nova"), self.dados(email="Paula@exemplo.org"))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Essa pessoa já está na equipe")
        self.assertEqual(Vinculo.objects.filter(usuario=self.professor).count(), 1)

    def test_campos_obrigatorios_e_whatsapp(self):
        self.entrar(self.coordenacao)
        resposta = self.client.post(reverse("equipe:pessoa_nova"), {"whatsapp_trabalho": "abc"})
        self.assertContains(resposta, "Falta o e-mail")
        self.assertContains(resposta, "Falta o nome")
        self.assertContains(resposta, "Falta o papel")
        self.assertContains(resposta, "Digite o WhatsApp com DDD")
        self.assertContains(resposta, 'aria-invalid="true"')

    def test_quem_so_cuida_da_equipe_nao_da_papel_que_configura(self):
        self.entrar(self.coordenacao)
        tela = self.client.get(reverse("equipe:pessoa_nova"))
        self.assertNotContains(tela, f'value="{self.papel_supervisao.pk}"')
        resposta = self.client.post(reverse("equipe:pessoa_nova"), self.dados(papel=self.papel_supervisao.pk))
        self.assertContains(resposta, "Esse papel não está disponível")
        self.assertFalse(Usuario.objects.filter(email="nina.nova@exemplo.org").exists())

    def test_papel_de_outro_servico_nao_vale(self):
        papel_de_fora = self.de_fora.vinculos.get().papel
        self.entrar(self.supervisao)
        resposta = self.client.post(reverse("equipe:pessoa_nova"), self.dados(papel=papel_de_fora.pk))
        self.assertContains(resposta, "Esse papel não está disponível")


class EditarPessoaTestes(EquipeTestCase):
    def test_mudar_papel_vai_para_a_trilha(self):
        self.entrar(self.supervisao)
        url = reverse("equipe:pessoa_editar", args=[self.professor.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        resposta = self.client.post(url, {
            "nome": "Paula Professora Inventada",
            "whatsapp_trabalho": "",
            "papel": self.papel_coordenacao.pk,
            "motivo_alteracao": "Assumiu a coordenação da equipe",
        })
        self.assertRedirects(resposta, reverse("equipe:pessoa_detalhe", args=[self.professor.pk]))
        vinculo = Vinculo.objects.get(usuario=self.professor, servico=self.servico)
        self.assertEqual(vinculo.papel, self.papel_coordenacao)
        evento = self.eventos(acao=Acao.MUDOU_PAPEL, modelo="core.Vinculo", objeto_id=str(vinculo.pk)).get()
        self.assertEqual(evento.motivo, "Assumiu a coordenação da equipe")
        self.assertEqual(evento.mudancas["papel"]["de"], "Professor")
        self.assertEqual(evento.mudancas["papel"]["para"], "Coordenação de equipe")
        self.assertEqual(evento.usuario, self.supervisao)
        tela = self.client.get(reverse("equipe:pessoa_detalhe", args=[self.professor.pk]))
        self.assertContains(tela, "mudou papel")
        self.assertContains(tela, "Assumiu a coordenação da equipe")

    def test_editar_nome_pede_motivo_e_grava_trilha(self):
        self.entrar(self.coordenacao)
        url = reverse("equipe:pessoa_editar", args=[self.apoio.pk])
        dados = {"nome": "Abel Apoio Renomeado", "whatsapp_trabalho": "11 91234-5678", "papel": self.apoio.vinculos.get().papel_id}
        resposta = self.client.post(url, dados)
        self.assertContains(resposta, "Por que você está alterando?")
        self.apoio.refresh_from_db()
        self.assertEqual(self.apoio.nome, "Abel Apoio Inventado")
        dados["motivo_alteracao"] = "Corrigir o nome"
        self.client.post(url, dados)
        self.apoio.refresh_from_db()
        self.assertEqual(self.apoio.nome, "Abel Apoio Renomeado")
        evento = self.eventos(acao=Acao.ALTEROU, modelo="core.Usuario", objeto_id=str(self.apoio.pk)).get()
        self.assertEqual(evento.mudancas["nome"]["de"], "Abel Apoio Inventado")
        self.assertEqual(evento.servico, self.servico)
        self.assertFalse(self.eventos(acao=Acao.MUDOU_PAPEL).exists())

    def test_pessoa_que_tambem_trabalha_em_outro_servico(self):
        dupla = criar_pessoa(self.servico, self.papel_professor, nome="Dora Dupla Inventada",
                             whatsapp_trabalho="(11) 97777-0000")
        Vinculo.objects.create(usuario=dupla, servico=self.outro_servico, papel=self.de_fora.vinculos.get().papel)
        self.entrar(self.supervisao)
        url = reverse("equipe:pessoa_editar", args=[dupla.pk])
        tela = self.client.get(url)
        self.assertContains(tela, "também trabalha em outro serviço")
        self.assertTrue(tela.context["form"].fields["nome"].disabled)
        self.assertTrue(tela.context["form"].fields["whatsapp_trabalho"].disabled)
        # Mesmo que o envio tente mudar o nome, o cadastro comum aos serviços fica como estava; o papel muda.
        resposta = self.client.post(url, {
            "nome": "Nome Trocado Por Este Servico", "whatsapp_trabalho": "", "papel": self.papel_coordenacao.pk,
            "motivo_alteracao": "Passou a coordenar a equipe",
        })
        self.assertRedirects(resposta, reverse("equipe:pessoa_detalhe", args=[dupla.pk]))
        dupla.refresh_from_db()
        self.assertEqual(dupla.nome, "Dora Dupla Inventada")
        self.assertEqual(dupla.whatsapp_trabalho, "(11) 97777-0000")
        self.assertEqual(Vinculo.objects.get(usuario=dupla, servico=self.servico).papel, self.papel_coordenacao)
        self.assertFalse(self.eventos(acao=Acao.ALTEROU, modelo="core.Usuario", objeto_id=str(dupla.pk)).exists())
        self.assertTrue(self.eventos(acao=Acao.MUDOU_PAPEL).exists())

    def test_ninguem_muda_o_proprio_papel(self):
        self.entrar(self.supervisao)
        self.client.post(reverse("equipe:pessoa_editar", args=[self.supervisao.pk]), {
            "nome": "Sueli Supervisora Inventada", "whatsapp_trabalho": "",
            "papel": self.papel_professor.pk, "motivo_alteracao": "Teste",
        })
        self.assertEqual(Vinculo.objects.get(usuario=self.supervisao).papel, self.papel_supervisao)

    def test_conflito_de_edicao(self):
        self.entrar(self.coordenacao)
        url = reverse("equipe:pessoa_editar", args=[self.apoio.pk])
        vinculo = Vinculo.objects.select_related("usuario", "papel").get(usuario=self.apoio)
        estado = assinar_estado(PessoaEditarForm.valores_salvos(vinculo))
        # Outra pessoa muda o nome e o WhatsApp no meio do caminho.
        Usuario.objects.filter(pk=self.apoio.pk).update(nome="Abel Mudado Por Outra", whatsapp_trabalho="11 95555-0000")
        resposta = self.client.post(url, {
            "nome": "Abel Mudado Por Mim", "whatsapp_trabalho": "", "papel": vinculo.papel_id,
            "motivo_alteracao": "Corrigir", "estado_original": estado,
        })
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Outra pessoa salvou este cadastro")
        self.apoio.refresh_from_db()
        self.assertEqual(self.apoio.nome, "Abel Mudado Por Outra")
        # O WhatsApp, que só a outra pessoa mudou, volta com o valor dela no formulário.
        self.assertContains(resposta, "11 95555-0000")

    def test_erro_de_validacao_nao_esconde_mudanca_de_outra_pessoa(self):
        self.entrar(self.coordenacao)
        url = reverse("equipe:pessoa_editar", args=[self.apoio.pk])
        estado = self.client.get(url).context["estado_original"]
        Usuario.objects.filter(pk=self.apoio.pk).update(nome="Abel Mudado Por Outra")
        dados = {"nome": "Abel Mudado Por Mim", "whatsapp_trabalho": "", "papel": self.apoio.vinculos.get().papel_id,
                 "estado_original": estado}
        sem_motivo = self.client.post(url, dados)
        self.assertContains(sem_motivo, "Por que você está alterando?")
        self.assertEqual(sem_motivo.context["estado_original"], estado)
        dados["motivo_alteracao"] = "Corrigir"
        resposta = self.client.post(url, dados)
        self.assertContains(resposta, "Outra pessoa salvou este cadastro")
        self.apoio.refresh_from_db()
        self.assertEqual(self.apoio.nome, "Abel Mudado Por Outra")


class DesativarPessoaTestes(EquipeTestCase):
    def test_tela_de_confirmacao(self):
        self.entrar(self.coordenacao)
        resposta = self.client.get(reverse("equipe:pessoa_desativar", args=[self.professor.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Desativar acesso")
        self.assertContains(resposta, "sessões que ela tem abertas")

    def test_pessoa_desativada_perde_o_acesso(self):
        navegador_da_paula = Client()
        navegador_da_paula.force_login(self.professor)
        self.assertEqual(navegador_da_paula.get(reverse("minha_conta")).status_code, 200)

        self.entrar(self.coordenacao)
        resposta = self.client.post(
            reverse("equipe:pessoa_desativar", args=[self.professor.pk]), {"motivo": "Saiu do serviço"}
        )
        self.assertRedirects(resposta, reverse("equipe:pessoa_detalhe", args=[self.professor.pk]))
        self.professor.refresh_from_db()
        self.assertFalse(self.professor.is_active)
        self.assertFalse(Vinculo.objects.get(usuario=self.professor).ativo)
        sessoes_da_paula = [
            s for s in Session.objects.all() if s.get_decoded().get("_auth_user_id") == str(self.professor.pk)
        ]
        self.assertEqual(sessoes_da_paula, [])
        resposta = navegador_da_paula.get(reverse("minha_conta"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("entrar"), resposta["Location"])
        self.assertFalse(Client().login(username="paula@exemplo.org", password="senha-de-teste-123"))

        evento = self.eventos(acao=Acao.ALTEROU, modelo="core.Vinculo").get()
        self.assertEqual(evento.motivo, "Saiu do serviço")
        self.assertIn("encerrou as sessões", evento.descricao)

    def test_motivo_e_obrigatorio(self):
        self.entrar(self.coordenacao)
        resposta = self.client.post(reverse("equipe:pessoa_desativar", args=[self.professor.pk]), {"motivo": ""})
        self.assertContains(resposta, "Falta o motivo")
        self.assertTrue(Vinculo.objects.get(usuario=self.professor).ativo)

    def test_ninguem_desativa_a_si_mesmo(self):
        self.entrar(self.supervisao)
        url = reverse("equipe:pessoa_desativar", args=[self.supervisao.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"motivo": "Teste"}).status_code, 403)
        self.assertTrue(Vinculo.objects.get(usuario=self.supervisao).ativo)

    def test_quem_tem_outro_servico_continua_com_login(self):
        dupla = criar_pessoa(self.servico, self.papel_professor, nome="Dora Dupla Inventada")
        Vinculo.objects.create(usuario=dupla, servico=self.outro_servico, papel=self.de_fora.vinculos.get().papel)
        self.entrar(self.coordenacao)
        self.client.post(reverse("equipe:pessoa_desativar", args=[dupla.pk]), {"motivo": "Saiu deste serviço"})
        dupla.refresh_from_db()
        self.assertTrue(dupla.is_active)
        self.assertFalse(Vinculo.objects.get(usuario=dupla, servico=self.servico).ativo)
        self.assertTrue(Vinculo.objects.get(usuario=dupla, servico=self.outro_servico).ativo)

    def test_reativar(self):
        self.entrar(self.coordenacao)
        self.client.post(reverse("equipe:pessoa_desativar", args=[self.professor.pk]), {"motivo": "Licença"})
        tela = self.client.get(reverse("equipe:pessoa_detalhe", args=[self.professor.pk]))
        self.assertContains(tela, "Reativar acesso")
        self.assertEqual(self.client.get(reverse("equipe:pessoa_reativar", args=[self.professor.pk])).status_code, 405)
        resposta = self.client.post(reverse("equipe:pessoa_reativar", args=[self.professor.pk]))
        self.assertRedirects(resposta, reverse("equipe:pessoa_detalhe", args=[self.professor.pk]))
        self.professor.refresh_from_db()
        self.assertTrue(self.professor.is_active)
        self.assertTrue(Vinculo.objects.get(usuario=self.professor).ativo)
        self.assertTrue(self.eventos(acao=Acao.ALTEROU, descricao__startswith="Reativou").exists())


class LinkDeSenhaTestes(EquipeTestCase):
    def sem_senha(self):
        """Pessoa só deste serviço que ainda não criou a senha (o primeiro link venceu)."""
        pessoa = Usuario.objects.create_user(email="lia.sem.senha@exemplo.org", password=None,
                                             nome="Lia Sem Senha Inventada")
        Vinculo.objects.create(usuario=pessoa, servico=self.servico, papel=self.papel_professor)
        return pessoa

    def test_gerar_novo_link_para_quem_ainda_nao_criou_a_senha(self):
        pessoa = self.sem_senha()
        self.entrar(self.coordenacao)
        url = reverse("equipe:pessoa_link_senha", args=[pessoa.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertContains(self.client.get(reverse("equipe:pessoa_detalhe", args=[pessoa.pk])), "Gerar novo link de senha")
        resposta = self.client.post(url)
        self.assertRedirects(resposta, reverse("equipe:pessoa_detalhe", args=[pessoa.pk]), fetch_redirect_response=False)
        tela = self.client.get(reverse("equipe:pessoa_detalhe", args=[pessoa.pk]))
        link = tela.context["link"]["link"]
        self.assertContains(tela, link)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(link, mail.outbox[0].body)
        # O link abre o fluxo de definir senha do núcleo: 302 para a tela com o formulário, que responde 200.
        navegador = Client()
        resposta = navegador.get(urlparse(link).path)
        self.assertEqual(resposta.status_code, 302)
        self.assertContains(navegador.get(resposta["Location"]), "Salvar senha")
        self.assertTrue(self.eventos(acao=Acao.OUTRO, modelo="core.Usuario", objeto_id=str(pessoa.pk),
                                     descricao__startswith="Gerou um novo link").exists())

    def test_quem_ja_tem_senha_recebe_o_link_so_por_email(self):
        self.entrar(self.coordenacao)
        detalhe = reverse("equipe:pessoa_detalhe", args=[self.apoio.pk])
        tela = self.client.get(detalhe)
        self.assertContains(tela, "Mandar link de senha por e-mail")
        self.assertContains(tela, "Ela já criou a senha")
        self.assertNotContains(tela, "Gerar novo link de senha")
        resposta = self.client.post(reverse("equipe:pessoa_link_senha", args=[self.apoio.pk]), follow=True)
        self.assertRedirects(resposta, detalhe)
        self.assertContains(resposta, "Link para criar a senha mandado para abel@exemplo.org")
        self.assertIsNone(resposta.context["link"])
        self.assertNotContains(resposta, "/senha/definir/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["abel@exemplo.org"])
        self.assertIn("/senha/definir/", mail.outbox[0].body)
        self.assertTrue(self.eventos(acao=Acao.OUTRO, modelo="core.Usuario", objeto_id=str(self.apoio.pk),
                                     descricao__startswith="Mandou por e-mail").exists())

    def test_email_que_falha(self):
        pessoa = self.sem_senha()
        self.entrar(self.coordenacao)
        with mock.patch("equipe.views.send_mail", side_effect=OSError("servidor de e-mail fora do ar")), \
                self.assertLogs("equipe.views", "WARNING") as registro:
            na_tela = self.client.post(reverse("equipe:pessoa_link_senha", args=[pessoa.pk]), follow=True)
            so_email = self.client.post(reverse("equipe:pessoa_link_senha", args=[self.apoio.pk]), follow=True)
        self.assertEqual(len(registro.records), 2)
        # Na tela, o link continua para ser mandado pelo WhatsApp de trabalho.
        self.assertIsNotNone(na_tela.context["link"])
        self.assertContains(na_tela, "Não deu para mandar o link por e-mail agora")
        self.assertContains(so_email, "Não deu para mandar o e-mail agora")
        self.assertIsNone(so_email.context["link"])
        self.assertTrue(self.eventos(acao=Acao.OUTRO, objeto_id=str(self.apoio.pk),
                                     descricao__endswith="o e-mail não foi enviado").exists())

    def test_ninguem_gera_link_para_si_mesmo(self):
        self.entrar(self.coordenacao)
        tela = self.client.get(reverse("equipe:pessoa_detalhe", args=[self.coordenacao.pk]))
        self.assertNotContains(tela, reverse("equipe:pessoa_link_senha", args=[self.coordenacao.pk]))
        self.assertEqual(self.client.post(reverse("equipe:pessoa_link_senha", args=[self.coordenacao.pk])).status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_quem_so_cuida_da_equipe_nao_gera_link_de_quem_configura(self):
        self.entrar(self.coordenacao)
        resposta = self.client.post(reverse("equipe:pessoa_link_senha", args=[self.supervisao.pk]))
        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_pessoa_desativada_nao_recebe_link(self):
        Vinculo.objects.filter(usuario=self.apoio).update(ativo=False)
        self.entrar(self.coordenacao)
        self.assertEqual(self.client.post(reverse("equipe:pessoa_link_senha", args=[self.apoio.pk])).status_code, 403)

    def test_papel_novo_da_coordenacao_sem_configurar_nao_ve_papeis(self):
        papel = criar_papel(self.servico, "Secretaria", acoes=["gerir_equipe"])
        pessoa = criar_pessoa(self.servico, papel)
        self.entrar(pessoa)
        self.assertEqual(self.client.get(reverse("equipe:pessoas")).status_code, 200)
        self.assertEqual(self.client.get(reverse("equipe:papeis")).status_code, 403)

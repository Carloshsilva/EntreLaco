"""Testes do núcleo: login, duas etapas, permissões, trilha, conflito e separação entre serviços."""
import datetime

import pyotp
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from core import auditoria
from core.models import EventoAuditoria
from core.permissoes import Acesso, campos_permitidos
from core.registro import Pendencia
from core.testes import criar_aluno, criar_apoio, criar_pessoa, criar_professor, criar_servico, criar_supervisao


class EntrarTestes(TestCase):
    def setUp(self):
        self.servico = criar_servico()
        self.professor = criar_professor(self.servico, email="prof@exemplo.org", senha="uma-senha-longa-1")

    def test_pede_login(self):
        resposta = self.client.get(reverse("inicio"))
        self.assertRedirects(resposta, f"{reverse('entrar')}?next=/")

    def test_entra_e_registra_na_trilha(self):
        resposta = self.client.post(reverse("entrar"), {"email": "prof@exemplo.org", "senha": "uma-senha-longa-1"})
        self.assertRedirects(resposta, reverse("inicio"))
        self.assertTrue(EventoAuditoria.objects.filter(acao="entrou", usuario=self.professor).exists())

    def test_senha_errada_bloqueia_depois_de_cinco(self):
        for _ in range(5):
            self.client.post(reverse("entrar"), {"email": "prof@exemplo.org", "senha": "errada-errada"})
        resposta = self.client.post(reverse("entrar"), {"email": "prof@exemplo.org", "senha": "uma-senha-longa-1"})
        self.assertContains(resposta, "Muitas tentativas erradas")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_sair_exige_post(self):
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(reverse("sair")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("sair")), reverse("entrar"))

    def test_proximo_externo_e_ignorado(self):
        resposta = self.client.post(
            reverse("entrar") + "?next=https://exemplo.com/",
            {"email": "prof@exemplo.org", "senha": "uma-senha-longa-1", "next": "https://exemplo.com/"},
        )
        self.assertRedirects(resposta, reverse("inicio"))


class DuasEtapasTestes(TestCase):
    def setUp(self):
        self.servico = criar_servico()

    def test_esqueci_a_senha_avisa_quando_o_email_nao_esta_ligado(self):
        aviso = "O envio de e-mail ainda não está ligado"
        for caminho in ("senha_esqueci", "senha_pedido_enviado"):
            self.assertNotContains(self.client.get(reverse(caminho)), aviso)
            with override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"):
                self.assertContains(self.client.get(reverse(caminho)), aviso)

    def test_quem_configura_e_levado_a_ativar(self):
        supervisao = criar_supervisao(self.servico)
        supervisao.totp_ativo = False
        supervisao.save()
        self.client.force_login(supervisao)
        self.assertRedirects(self.client.get(reverse("inicio")), reverse("duas_etapas"))

    def test_ativar_e_entrar_com_codigo(self):
        supervisao = criar_supervisao(self.servico, email="sup@exemplo.org", senha="uma-senha-longa-2")
        supervisao.totp_ativo = False
        supervisao.totp_segredo = ""
        supervisao.save()
        self.client.force_login(supervisao)
        tela = self.client.get(reverse("duas_etapas"))
        segredo = self.client.session["duas_etapas_segredo_novo"]
        # No celular que tem o aplicativo, o botão abre o cadastro direto, sem ler o QR.
        self.assertContains(tela, f'href="otpauth://totp/EntreLa%C3%A7o:sup%40exemplo.org?secret={segredo}')
        resposta = self.client.post(reverse("duas_etapas"), {"codigo": pyotp.TOTP(segredo).now()})
        self.assertRedirects(resposta, reverse("inicio"))
        supervisao.refresh_from_db()
        self.assertTrue(supervisao.totp_ativo)

        self.client.logout()
        resposta = self.client.post(reverse("entrar"), {"email": "sup@exemplo.org", "senha": "uma-senha-longa-2"})
        self.assertRedirects(resposta, reverse("entrar_codigo"))
        self.assertNotIn("_auth_user_id", self.client.session)
        resposta = self.client.post(reverse("entrar_codigo"), {"codigo": "000000"})
        self.assertContains(resposta, "Código errado")
        resposta = self.client.post(reverse("entrar_codigo"), {"codigo": pyotp.TOTP(segredo).now()})
        self.assertRedirects(resposta, reverse("inicio"))


class TelasDoNucleoTestes(TestCase):
    def setUp(self):
        self.servico = criar_servico()
        self.professor = criar_professor(self.servico)
        self.client.force_login(self.professor)

    def test_inicio_agenda_e_conta_abrem(self):
        for nome in ["inicio", "agenda", "minha_conta", "trocar_senha"]:
            with self.subTest(nome=nome):
                resposta = self.client.get(reverse(nome))
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, "Ambiente de teste")

    def test_paginas_de_quem_esta_logado_nao_ficam_em_cache(self):
        resposta = self.client.get(reverse("inicio"))
        self.assertIn("no-store", resposta["Cache-Control"])
        self.assertIn("default-src 'self'", resposta["Content-Security-Policy"])

    def test_trilha_so_com_a_acao(self):
        self.assertEqual(self.client.get(reverse("trilha")).status_code, 403)
        supervisao = criar_supervisao(self.servico)
        self.client.force_login(supervisao)
        self.assertEqual(self.client.get(reverse("trilha")).status_code, 200)

    def test_sem_vinculo(self):
        sem_servico = criar_pessoa()
        self.client.force_login(sem_servico)
        self.assertEqual(self.client.get(reverse("inicio")).status_code, 403)

    def test_desativar_encerra_a_sessao(self):
        self.professor.is_active = False
        self.professor.save()
        resposta = self.client.get(reverse("inicio"))
        self.assertEqual(resposta.status_code, 302)


class PermissoesTestes(TestCase):
    def test_apoio_nao_ve_saude(self):
        servico = criar_servico()
        apoio = criar_apoio(servico)
        acesso = Acesso.do_papel(apoio.vinculos.get().papel)
        visiveis = campos_permitidos(Aluno, acesso)
        self.assertNotIn("diagnostico", visiveis)
        self.assertNotIn("visao", visiveis)
        self.assertIn("escola", visiveis)

    def test_quem_configura_ganha_acoes_de_cuidado(self):
        servico = criar_servico()
        supervisao = criar_supervisao(servico)
        acesso = Acesso.do_papel(supervisao.vinculos.get().papel)
        self.assertTrue(acesso.tem("ver_trilha"))
        self.assertTrue(acesso.configurar)


class TrilhaTestes(TestCase):
    def test_evento_nao_se_altera_nem_se_apaga(self):
        servico = criar_servico()
        evento = auditoria.registrar(None, EventoAuditoria.Acao.OUTRO, servico=servico, descricao="teste")
        evento.descricao = "mudou"
        with self.assertRaises(ValueError):
            evento.save()
        with self.assertRaises(ValueError):
            evento.delete()

    def test_mudancas_de_saude_ficam_escondidas_para_o_apoio(self):
        servico = criar_servico()
        aluno = criar_aluno(servico)
        antes = auditoria.fotografar(aluno, ["diagnostico", "leito"])
        aluno.diagnostico = "Diagnóstico inventado"
        aluno.leito = "12B"
        depois = auditoria.fotografar(aluno, ["diagnostico", "leito"])
        evento = auditoria.registrar(None, EventoAuditoria.Acao.ALTEROU, aluno,
                                     mudancas=auditoria.comparar(Aluno, antes, depois))
        apoio = criar_apoio(servico)
        acesso = Acesso.do_papel(apoio.vinculos.get().papel)
        self.assertEqual(set(auditoria.mudancas_visiveis(evento, acesso)), {"leito"})


class PendenciaTestes(TestCase):
    def test_situacao_do_prazo(self):
        hoje = timezone.localdate()
        self.assertEqual(Pendencia("a", "/", "t", prazo=hoje - datetime.timedelta(days=1)).situacao_do_prazo, "vencida")
        self.assertEqual(Pendencia("a", "/", "t", prazo=hoje).situacao_do_prazo, "hoje")
        self.assertEqual(Pendencia("a", "/", "t").situacao_do_prazo, "sem_prazo")

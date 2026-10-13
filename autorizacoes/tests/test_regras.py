"""Regras puras das autorizações: contato com a escola (RF-28), assinatura e prova (LGPD-03, SEG-08)."""
import base64
import datetime
import io

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.utils import timezone

from alunos.models import Aluno
from autorizacoes import regras
from core.testes import criar_aluno

from .base import BaseAutorizacoes, Forma, Situacao, Tipo, png_de_assinatura


class ContatoComAEscolaTestes(BaseAutorizacoes):
    def test_sem_coleta_nao_libera(self):
        self.assertFalse(regras.libera_contato_com_a_escola(self.aluno))

    def test_cada_situacao(self):
        esperado = {
            Situacao.VALIDA: True,
            Situacao.PROVISORIA: True,
            Situacao.PENDENTE: False,
            Situacao.RECUSADA: False,
            Situacao.REVOGADA: False,
        }
        for situacao, libera in esperado.items():
            with self.subTest(situacao=situacao):
                self.coleta(situacao=situacao, forma="" if situacao == Situacao.PENDENTE else Forma.PAPEL)
                self.assertIs(regras.libera_contato_com_a_escola(self.aluno), libera)

    def test_vale_a_coleta_mais_recente(self):
        self.coleta(situacao=Situacao.VALIDA)
        self.coleta(situacao=Situacao.REVOGADA)
        self.assertFalse(regras.libera_contato_com_a_escola(self.aluno))
        self.coleta(situacao=Situacao.VALIDA)
        self.assertTrue(regras.libera_contato_com_a_escola(self.aluno))

    def test_uso_dos_dados_nao_libera_contato(self):
        self.coleta(tipo=Tipo.USO_DADOS, situacao=Situacao.VALIDA)
        self.assertFalse(regras.libera_contato_com_a_escola(self.aluno))

    def test_filtro_de_lista_numa_consulta(self):
        terceiro = criar_aluno(self.servico, nome="Nina Inventada Rocha")
        self.coleta(situacao=Situacao.VALIDA)
        self.coleta(aluno=self.outro_aluno, situacao=Situacao.VALIDA)
        self.coleta(aluno=self.outro_aluno, situacao=Situacao.REVOGADA)
        self.coleta(aluno=terceiro, situacao=Situacao.PROVISORIA, forma=Forma.WHATSAPP)
        alunos = Aluno.objects.filter(servico=self.servico)
        with self.assertNumQueries(1):
            liberados = set(regras.alunos_com_contato_liberado(alunos).values_list("pk", flat=True))
        self.assertEqual(liberados, {self.aluno.pk, terceiro.pk})


class ImpressaoDigitalTestes(SimpleTestCase):
    dados = {
        "texto_do_termo": "Texto inventado do termo.", "versao_do_termo": 2, "nome": "Rita Responsável Inventada",
        "documento": "RG inventado 123", "decisao": regras.DECISAO_AUTORIZO,
        "colhida_em": datetime.datetime(2026, 10, 13, 14, 5, 7, tzinfo=datetime.UTC),
        "assinatura": b"bytes inventados",
    }

    def test_deterministica_e_sensivel_a_cada_dado(self):
        base = regras.impressao_digital_do_tablet(**self.dados)
        self.assertEqual(len(base), 64)
        self.assertEqual(regras.impressao_digital_do_tablet(**self.dados), base)
        mudancas = {
            "texto_do_termo": "Texto inventado do termo!", "versao_do_termo": 3, "nome": "Rita Outra Inventada",
            "documento": "RG inventado 124", "decisao": regras.DECISAO_NAO_AUTORIZO,
            "colhida_em": self.dados["colhida_em"] + datetime.timedelta(seconds=1), "assinatura": b"outros bytes",
        }
        for campo, valor in mudancas.items():
            with self.subTest(campo=campo):
                self.assertNotEqual(regras.impressao_digital_do_tablet(**{**self.dados, campo: valor}), base)

    def test_separador_impede_juntar_campos(self):
        a = regras.impressao_digital_do_tablet(**{**self.dados, "nome": "Rita", "documento": "Inventada"})
        b = regras.impressao_digital_do_tablet(**{**self.dados, "nome": "RitaInventada", "documento": ""})
        self.assertNotEqual(a, b)

    def test_momento_em_utc_sem_microssegundos(self):
        local = timezone.localtime(self.dados["colhida_em"].replace(microsecond=123456))
        self.assertEqual(regras.momento_iso(local), "2026-10-13T14:05:07+00:00")


class AssinaturaPngTestes(SimpleTestCase):
    def test_aceita_data_url_e_base64_puro(self):
        png = png_de_assinatura()
        b64 = base64.b64encode(png).decode()
        self.assertEqual(regras.ler_assinatura_png("data:image/png;base64," + b64), png)
        self.assertEqual(regras.ler_assinatura_png(b64), png)

    def test_recusa_o_que_nao_e_png(self):
        from PIL import Image

        saida = io.BytesIO()
        Image.new("RGB", (40, 20), "white").save(saida, format="JPEG")
        jpg = base64.b64encode(saida.getvalue()).decode()
        falso = base64.b64encode(regras.CABECALHO_PNG + b"nada de imagem").decode()
        for texto in ("", "   ", "data:image/png;base64,", "não é base64!", "data:image/jpeg;base64," + jpg, jpg, falso):
            with self.subTest(texto=texto[:30]):
                with self.assertRaises(ValidationError) as erro:
                    regras.ler_assinatura_png(texto)
                self.assertIn("Toque em Limpar", erro.exception.messages[0])

    def test_recusa_grande_demais(self):
        texto = "A" * (regras.LIMITE_DA_ASSINATURA * 2)
        with self.assertRaises(ValidationError) as erro:
            regras.ler_assinatura_png(texto)
        self.assertEqual(erro.exception.code, "assinatura_grande")


class ConversaDoWhatsappTestes(SimpleTestCase):
    def test_txt_em_utf8_passa(self):
        arquivo = SimpleUploadedFile("conversa.txt", "13/10/2026 - Responsável Inventada: sim".encode(), "text/plain")
        self.assertIs(regras.validar_conversa(arquivo), arquivo)

    def test_txt_que_nao_e_texto_e_recusado(self):
        for conteudo in (b"", b"texto\x00binario", "texto em latin-1: ç".encode("latin-1")):
            with self.subTest(conteudo=conteudo):
                with self.assertRaises(ValidationError) as erro:
                    regras.validar_conversa(SimpleUploadedFile("conversa.txt", conteudo, "text/plain"))
                self.assertIn("sem mídia", erro.exception.messages[0])

    def test_zip_e_recusado_com_a_dica(self):
        zipado = SimpleUploadedFile("conversa.zip", b"PK\x03\x04inventado", "application/zip")
        with self.assertRaises(ValidationError) as erro:
            regras.validar_conversa(zipado)
        self.assertIn("sem mídia", erro.exception.messages[0])


class OQueSePodeFazerTestes(SimpleTestCase):
    def coleta(self, situacao, forma=Forma.PAPEL, pk=1):
        from autorizacoes.models import Autorizacao

        return Autorizacao(pk=pk, situacao=situacao, forma=forma, termo_id=1)

    def test_pode_colher_salvo_com_a_valida(self):
        self.assertTrue(regras.pode_colher(None))
        for situacao in (Situacao.PENDENTE, Situacao.PROVISORIA, Situacao.RECUSADA, Situacao.REVOGADA):
            self.assertTrue(regras.pode_colher(self.coleta(situacao)))
        self.assertFalse(regras.pode_colher(self.coleta(Situacao.VALIDA)))

    def test_provisoria_so_aceita_o_sim_definitivo(self):
        self.assertEqual(regras.formas_permitidas(self.coleta(Situacao.PROVISORIA)), [Forma.TABLET, Forma.PAPEL])
        self.assertIn(regras.PENDENTE, regras.formas_permitidas(None))
        self.assertIn(Forma.WHATSAPP, regras.formas_permitidas(self.coleta(Situacao.RECUSADA)))

    def test_so_revoga_a_atual_valida_ou_provisoria(self):
        valida = self.coleta(Situacao.VALIDA)
        self.assertTrue(regras.pode_revogar(valida, valida))
        self.assertTrue(regras.pode_revogar(self.coleta(Situacao.PROVISORIA, Forma.WHATSAPP), self.coleta(Situacao.PROVISORIA)))
        self.assertFalse(regras.pode_revogar(valida, self.coleta(Situacao.VALIDA, pk=2)))
        self.assertFalse(regras.pode_revogar(self.coleta(Situacao.RECUSADA), self.coleta(Situacao.RECUSADA)))

    def test_so_pendente_no_tablet_se_assina(self):
        self.assertTrue(regras.assinavel_no_tablet(self.coleta(Situacao.PENDENTE, Forma.TABLET)))
        self.assertFalse(regras.assinavel_no_tablet(self.coleta(Situacao.PENDENTE, "")))
        self.assertFalse(regras.assinavel_no_tablet(self.coleta(Situacao.VALIDA, Forma.TABLET)))

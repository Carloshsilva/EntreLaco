"""Citações de alunos: citar, editar e concluir o encaminhamento (RF-17, RF-07, SEG-03, SEG-05)."""
import datetime

from django.urls import reverse

from core import auditoria
from core.models import EventoAuditoria
from core.permissoes import Acesso
from reunioes.models import CitacaoDeAluno

from .base import Acao, BaseReunioes


def acesso_de(pessoa):
    return Acesso.do_papel(pessoa.vinculos.get().papel)


class NovaCitacaoTestes(BaseReunioes):
    def url(self, reuniao=None):
        return reverse("reunioes:citacao_nova", args=[(reuniao or self.reuniao).pk])

    def dados(self, **extra):
        dados = {
            "aluno": self.aluno.pk, "texto": "A aluna quer voltar a ler gibis inventados.", "grupo_de_dado": "atas",
            "encaminhamento": "Levar gibis na quinta.", "responsavel": self.professor.pk,
            "prazo": (self.hoje + datetime.timedelta(days=3)).isoformat(),
        }
        dados.update(extra)
        return dados

    def test_abre_para_quem_edita_as_atas_com_o_aluno_escolhido(self):
        self.entrar(self.secretaria)
        resposta = self.client.get(self.url(), {"aluno": self.aluno.pk})
        self.assertEqual(resposta.status_code, 200)
        self.assertUmH1(resposta)
        self.assertContains(resposta, f'<option value="{self.aluno.pk}" selected>Lia Inventada Moreira</option>', html=True)
        self.assertNotContains(resposta, "Nina De Fora Souza")
        self.assertContains(resposta, "Se a citação fala de saúde")

    def test_403_para_quem_so_ve(self):
        self.entrar(self.professor)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 403)
        self.assertFalse(CitacaoDeAluno.objects.exists())

    def test_reuniao_ou_aluno_de_outro_servico_da_404(self):
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(self.url(self.reuniao_de_fora)).status_code, 404)
        self.assertEqual(self.client.post(self.url(self.reuniao_de_fora), self.dados()).status_code, 404)
        self.assertEqual(self.client.get(self.url(), {"aluno": self.aluno_de_fora.pk}).status_code, 404)

    def test_citar_grava_a_citacao_e_a_trilha(self):
        self.entrar(self.secretaria)
        resposta = self.client.post(self.url(), self.dados())
        citacao = CitacaoDeAluno.objects.get()
        self.assertRedirects(
            resposta, reverse("reunioes:detalhe", args=[self.reuniao.pk]) + f"#citacao-{citacao.pk}",
            fetch_redirect_response=False,
        )
        self.assertEqual(citacao.servico, self.servico)
        self.assertEqual(citacao.reuniao, self.reuniao)
        self.assertEqual(citacao.criado_por, self.secretaria)
        evento = EventoAuditoria.objects.get(modelo="reunioes.CitacaoDeAluno", objeto_id=str(citacao.pk))
        self.assertEqual(evento.acao, Acao.CRIOU)
        self.assertEqual(evento.aluno_id, self.aluno.pk)
        self.assertEqual(evento.mudancas["texto"]["grupo"], "atas")

    def test_aluno_e_responsavel_de_outro_servico_sao_recusados(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(self.url(), self.dados(aluno=self.aluno_de_fora.pk))
        self.assertContains(resposta, "Escolha um aluno da lista do serviço.")
        resposta = self.client.post(self.url(), self.dados(responsavel=self.de_fora.pk))
        self.assertContains(resposta, "Escolha uma pessoa da lista da equipe.")
        self.assertFalse(CitacaoDeAluno.objects.exists())

    def test_quem_nao_ve_saude_nao_escolhe_saude(self):
        self.entrar(self.secretaria)
        resposta = self.client.get(self.url())
        self.assertNotContains(resposta, 'value="sensivel"')
        self.assertContains(resposta, 'value="atas"')
        resposta = self.client.post(self.url(), self.dados(grupo_de_dado="sensivel"))
        self.assertContains(resposta, "Escolha um dos tipos de dado da lista.")
        self.assertFalse(CitacaoDeAluno.objects.exists())

    def test_responsavel_precisa_ver_a_citacao(self):
        self.entrar(self.supervisao)
        self.assertNotContains(self.client.get(self.url()), "Abel Apoio Inventado")  # não vê as atas
        resposta = self.client.post(self.url(), self.dados(responsavel=self.apoio.pk))
        self.assertContains(resposta, "Escolha uma pessoa da lista da equipe.")
        resposta = self.client.post(self.url(), self.dados(responsavel=self.secretaria.pk, grupo_de_dado="sensivel"))
        self.assertContains(resposta, "Rita I. não vê citações de Saúde e dados sensíveis")
        self.assertFalse(CitacaoDeAluno.objects.exists())

    def test_prazo_sem_responsavel_e_responsavel_sem_encaminhamento(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(self.url(), self.dados(responsavel=""))
        self.assertContains(resposta, "Escolha quem cuida do encaminhamento, ou deixe o prazo em branco.")
        resposta = self.client.post(self.url(), self.dados(encaminhamento=""))
        self.assertContains(resposta, "Escreva o encaminhamento que fica com o responsável")
        self.assertFalse(CitacaoDeAluno.objects.exists())

    def test_citacao_sem_encaminhamento_e_valida(self):
        self.entrar(self.supervisao)
        self.client.post(self.url(), self.dados(encaminhamento="", responsavel="", prazo=""))
        self.assertTrue(CitacaoDeAluno.objects.filter(responsavel__isnull=True).exists())

    def test_trilha_de_citacao_de_saude_fica_escondida_para_quem_nao_ve_saude(self):
        self.entrar(self.supervisao)
        self.client.post(self.url(), self.dados(grupo_de_dado="sensivel", texto="Fala de saúde inventada."))
        evento = EventoAuditoria.objects.get(modelo="reunioes.CitacaoDeAluno")
        self.assertEqual(evento.mudancas["texto"]["grupo"], "sensivel")
        self.assertEqual(auditoria.mudancas_visiveis(evento, acesso_de(self.secretaria)), {})
        self.assertIn("texto", auditoria.mudancas_visiveis(evento, acesso_de(self.supervisao)))


class EditarCitacaoTestes(BaseReunioes):
    def setUp(self):
        self.citacao = self.citar(encaminhamento="Levar gibis.", responsavel=self.professor)
        self.sensivel = self.citar(aluno=self.aluno_dois, grupo="sensivel", texto="Fala de saúde inventada.")

    def url(self, citacao=None):
        return reverse("reunioes:citacao_editar", args=[(citacao or self.citacao).pk])

    def dados(self, **extra):
        dados = {
            "aluno": self.aluno.pk, "texto": self.citacao.texto, "grupo_de_dado": "atas",
            "encaminhamento": "Levar gibis e revistas.", "responsavel": self.professor.pk, "prazo": "",
            "motivo_alteracao": "Faltou a revista no encaminhamento.",
        }
        dados.update(extra)
        return dados

    def test_abre_para_quem_edita_as_atas(self):
        self.entrar(self.secretaria)
        resposta = self.client.get(self.url())
        self.assertEqual(resposta.status_code, 200)
        self.assertUmH1(resposta)
        self.assertContains(resposta, "Por que você está alterando?")
        self.assertContains(resposta, 'name="concluida"')

    def test_403_para_quem_so_ve(self):
        self.entrar(self.professor)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 403)

    def test_citacao_de_outro_servico_da_404(self):
        de_fora = self.citar(reuniao=self.reuniao_de_fora, aluno=self.aluno_de_fora)
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(self.url(de_fora)).status_code, 404)

    def test_citacao_de_saude_da_404_para_quem_nao_ve_saude(self):
        self.entrar(self.secretaria)
        self.assertEqual(self.client.get(self.url(self.sensivel)).status_code, 404)
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(self.url(self.sensivel)).status_code, 200)

    def test_salvar_grava_o_motivo_na_trilha(self):
        self.entrar(self.secretaria)
        resposta = self.client.post(self.url(), self.dados())
        self.assertRedirects(
            resposta, reverse("reunioes:detalhe", args=[self.reuniao.pk]) + f"#citacao-{self.citacao.pk}",
            fetch_redirect_response=False,
        )
        self.citacao.refresh_from_db()
        self.assertEqual(self.citacao.encaminhamento, "Levar gibis e revistas.")
        self.assertEqual(self.citacao.versao, 2)
        evento = EventoAuditoria.objects.get(modelo="reunioes.CitacaoDeAluno", acao=Acao.ALTEROU)
        self.assertEqual(evento.motivo, "Faltou a revista no encaminhamento.")
        self.assertEqual(evento.mudancas["encaminhamento"]["para"], "Levar gibis e revistas.")
        self.assertEqual(evento.aluno_id, self.aluno.pk)

    def test_sem_motivo_nao_salva(self):
        self.entrar(self.secretaria)
        resposta = self.client.post(self.url(), self.dados(motivo_alteracao=""))
        self.assertContains(resposta, "Conte por que você está alterando")
        self.citacao.refresh_from_db()
        self.assertEqual(self.citacao.encaminhamento, "Levar gibis.")

    def test_mudar_para_saude_esconde_as_mudancas_na_trilha(self):
        self.entrar(self.supervisao)
        self.client.post(self.url(), self.dados(grupo_de_dado="sensivel", texto="Agora com saúde inventada."))
        evento = EventoAuditoria.objects.get(modelo="reunioes.CitacaoDeAluno", acao=Acao.ALTEROU)
        self.assertEqual({m["grupo"] for m in evento.mudancas.values()}, {"sensivel"})
        self.assertEqual(auditoria.mudancas_visiveis(evento, acesso_de(self.secretaria)), {})

    def test_conflito_mostra_as_duas_versoes_sem_salvar(self):
        self.entrar(self.supervisao)
        estado = self.client.get(self.url()).context["estado_original"]
        CitacaoDeAluno.objects.filter(pk=self.citacao.pk).update(encaminhamento="Versão da outra pessoa", versao=2)
        resposta = self.client.post(self.url(), self.dados(estado_original=estado))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Outra pessoa salvou este cadastro enquanto você editava")
        self.assertNotContains(resposta, "Nina De Fora Souza")  # o formulário refeito segue filtrado pelo serviço
        self.citacao.refresh_from_db()
        self.assertEqual(self.citacao.encaminhamento, "Versão da outra pessoa")
        self.assertFalse(EventoAuditoria.objects.filter(acao=Acao.ALTEROU).exists())


class ConcluirTestes(BaseReunioes):
    def setUp(self):
        self.citacao = self.citar(encaminhamento="Levar gibis.", responsavel=self.professor)

    def url(self, citacao=None):
        return reverse("reunioes:citacao_concluir", args=[(citacao or self.citacao).pk])

    def test_o_responsavel_conclui_e_fica_na_trilha(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url())
        self.assertRedirects(
            resposta, reverse("reunioes:detalhe", args=[self.reuniao.pk]) + f"#citacao-{self.citacao.pk}",
            fetch_redirect_response=False,
        )
        self.citacao.refresh_from_db()
        self.assertTrue(self.citacao.concluida)
        self.assertEqual(self.citacao.atualizado_por, self.professor)
        evento = EventoAuditoria.objects.get(modelo="reunioes.CitacaoDeAluno", acao=Acao.ALTEROU)
        self.assertEqual(evento.descricao, "Concluiu o encaminhamento")
        self.assertEqual(evento.mudancas["concluida"]["para"], "Sim")

    def test_quem_edita_as_atas_tambem_conclui(self):
        self.entrar(self.secretaria)
        self.client.post(self.url())
        self.citacao.refresh_from_db()
        self.assertTrue(self.citacao.concluida)

    def test_outra_pessoa_nao_conclui(self):
        self.entrar(self.professor_dois)
        self.assertEqual(self.client.post(self.url()).status_code, 403)
        self.citacao.refresh_from_db()
        self.assertFalse(self.citacao.concluida)
        self.assertFalse(EventoAuditoria.objects.filter(acao=Acao.ALTEROU).exists())

    def test_quem_nao_ve_as_atas_nao_conclui(self):
        self.entrar(self.apoio)
        self.assertEqual(self.client.post(self.url()).status_code, 403)

    def test_so_aceita_post(self):
        self.entrar(self.professor)
        self.assertEqual(self.client.get(self.url()).status_code, 405)

    def test_citacao_de_outro_servico_ou_invisivel_da_404(self):
        de_fora = self.citar(reuniao=self.reuniao_de_fora, aluno=self.aluno_de_fora)
        sensivel = self.citar(grupo="sensivel", encaminhamento="Conversar com a família inventada.",
                              responsavel=self.professor)
        self.entrar(self.supervisao)
        self.assertEqual(self.client.post(self.url(de_fora)).status_code, 404)
        self.entrar(self.secretaria)
        self.assertEqual(self.client.post(self.url(sensivel)).status_code, 404)

    def test_volta_para_o_endereco_pedido_so_se_for_deste_site(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url(), {"proximo": "https://exemplo.org/fora"})
        self.assertTrue(resposta["Location"].startswith(reverse("reunioes:detalhe", args=[self.reuniao.pk])))
        outra = self.citar(aluno=self.aluno_dois, encaminhamento="Ligar para a escola.", responsavel=self.professor)
        resposta = self.client.post(self.url(outra), {"proximo": "/alunos/1/#secao-citacoes"})
        self.assertEqual(resposta["Location"], "/alunos/1/#secao-citacoes")

    def test_concluir_de_novo_nao_duplica_a_trilha(self):
        self.entrar(self.professor)
        self.client.post(self.url())
        self.client.post(self.url())
        self.assertEqual(EventoAuditoria.objects.filter(acao=Acao.ALTEROU).count(), 1)

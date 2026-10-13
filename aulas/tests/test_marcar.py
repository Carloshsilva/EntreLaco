"""Marcar aula, registrar a aula marcada a partir da agenda (RF-15, RF-44) e dizer que ela não aconteceu."""
import datetime

from django.urls import reverse

from aulas.models import Aula
from core.models import EventoAuditoria

from .base import HOJE, BaseDeAulas, foto_de_teste


class MarcarAulaTestes(BaseDeAulas):
    url = reverse("aulas:marcar")

    def dados(self, **mudancas):
        dados = {
            "aluno": self.aluno.pk,
            "data": (HOJE() + datetime.timedelta(days=1)).isoformat(),
            "hora_inicio": "14:30",
            "duracao_minutos": "45",
        }
        dados.update(mudancas)
        return dados

    def test_abre_para_quem_edita_e_preenche_pelo_endereco(self):
        self.entrar(self.professor)
        amanha = HOJE() + datetime.timedelta(days=1)
        resposta = self.client.get(self.url, {"aluno": self.aluno.pk, "data": amanha.isoformat()})
        self.assertEqual(resposta.status_code, 200)
        inicial = resposta.context["form"].initial
        self.assertEqual(inicial["aluno"], self.aluno.pk)
        self.assertEqual(inicial["data"], amanha)
        self.assertContains(resposta, "<h1", count=1)

    def test_quem_nao_edita_aulas_recebe_403(self):
        for pessoa in (self.apoio, self.leitor):
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url, self.dados()).status_code, 403)

    def test_marcar_grava_a_aula_marcada_e_a_trilha(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, self.dados(), follow=True)
        aula = Aula.objects.get()
        self.assertRedirects(resposta, reverse("aulas:detalhe", args=[aula.pk]))
        self.assertEqual(aula.situacao, Aula.Situacao.MARCADA)
        self.assertEqual(aula.professor, self.professor)
        self.assertIsNone(aula.registrada_em)
        self.assertTrue(EventoAuditoria.objects.filter(
            modelo="aulas.Aula", objeto_id=str(aula.pk), acao=EventoAuditoria.Acao.CRIOU,
        ).exists())
        self.assertContains(resposta, "Ela já aparece na sua agenda.")

    def test_aula_marcada_aparece_na_agenda_e_na_tela_inicial(self):
        self.entrar(self.professor)
        self.client.post(self.url, self.dados())
        aula = Aula.objects.get()
        resposta = self.client.get(reverse("agenda"), {"semana": aula.data.isoformat()})
        self.assertContains(resposta, "Aula com Lia I.")
        self.assertContains(resposta, reverse("aulas:registrar_marcada", args=[aula.pk]))
        resposta = self.client.get(reverse("inicio"))
        self.assertContains(resposta, "Aula com Lia I.")
        # O calendário do colega não mostra a aula (RF-09).
        resposta = self.client.get(reverse("agenda"), {"semana": aula.data.isoformat(), "pessoa": self.outro_professor.pk})
        self.assertNotContains(resposta, "Aula com Lia I.")

    def test_professor_sem_permissao_nao_marca_para_outro(self):
        self.entrar(self.professor)
        self.client.post(self.url, self.dados(professor=self.outro_professor.pk))
        self.assertEqual(Aula.objects.get().professor, self.professor)

    def test_supervisao_marca_para_outro_professor(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(self.url, self.dados(professor=self.outro_professor.pk), follow=True)
        self.assertEqual(Aula.objects.get().professor, self.outro_professor)
        self.assertContains(resposta, "agenda de Bruno I.")

    def test_aluno_de_outro_servico(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, self.dados(aluno=self.aluno_de_fora.pk))
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Aula.objects.exists())


class RegistrarMarcadaTestes(BaseDeAulas):
    def setUp(self):
        super().setUp()
        self.marcada = self.criar_aula(situacao=Aula.Situacao.MARCADA, hora=datetime.time(9, 15), minutos=60)
        self.url = reverse("aulas:registrar_marcada", args=[self.marcada.pk])

    def test_abre_com_aluno_data_e_hora_preenchidos(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        form = resposta.context["form"]
        self.assertEqual(form["aluno"].value(), self.aluno.pk)
        self.assertEqual(form["data"].value(), HOJE())
        self.assertEqual(form["hora_inicio"].value(), datetime.time(9, 15))
        self.assertEqual(form["duracao_minutos"].value(), 60)
        self.assertNotIn("aluno_novo", form.fields)
        self.assertContains(resposta, 'enctype="multipart/form-data"')
        self.assertContains(resposta, reverse("aulas:nao_realizada", args=[self.marcada.pk]))

    def test_registrar_a_marcada_com_fotos(self):
        self.entrar(self.professor)
        dados = self.dados_do_registro(duracao_minutos="60", hora_inicio="09:15", novas_fotos=[foto_de_teste()])
        resposta = self.client.post(self.url, dados, follow=True)
        self.assertRedirects(resposta, reverse("aulas:detalhe", args=[self.marcada.pk]))
        self.marcada.refresh_from_db()
        self.assertEqual(self.marcada.situacao, Aula.Situacao.REGISTRADA)
        self.assertEqual(self.marcada.registrada_por, self.professor)
        self.assertEqual(self.marcada.versao, 2)
        self.assertEqual(self.marcada.fotos.count(), 1)
        evento = EventoAuditoria.objects.filter(modelo="aulas.Aula", objeto_id=str(self.marcada.pk)).first()
        self.assertEqual(evento.acao, EventoAuditoria.Acao.ALTEROU)
        self.assertEqual(evento.descricao, "Registrou a aula marcada")
        self.assertEqual(evento.mudancas["situacao"]["para"], "Registrada")
        self.assertContains(resposta, "Aula de Lia I. registrada com 1 foto.")

    def test_quem_nao_edita_aulas_recebe_403(self):
        for pessoa in (self.apoio, self.leitor):
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url, self.dados_do_registro()).status_code, 403)
        self.marcada.refresh_from_db()
        self.assertEqual(self.marcada.situacao, Aula.Situacao.MARCADA)

    def test_aula_de_outro_servico_da_404(self):
        de_fora = self.criar_aula(
            servico=self.outro_servico, aluno=self.aluno_de_fora, professor=self.professor_de_fora,
            situacao=Aula.Situacao.MARCADA,
        )
        self.entrar(self.professor)
        url = reverse("aulas:registrar_marcada", args=[de_fora.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.dados_do_registro()).status_code, 404)

    def test_aula_ja_registrada_volta_para_o_detalhe(self):
        self.marcada.situacao = Aula.Situacao.REGISTRADA
        self.marcada.save()
        self.entrar(self.professor)
        resposta = self.client.get(self.url, follow=True)
        self.assertRedirects(resposta, reverse("aulas:detalhe", args=[self.marcada.pk]))
        self.assertContains(resposta, "Esta aula já foi registrada.")
        antes = EventoAuditoria.objects.count()
        self.client.post(self.url, self.dados_do_registro())
        self.assertEqual(EventoAuditoria.objects.count(), antes)

    def test_aula_marcada_de_outro_professor_fica_em_nome_de_quem_registra(self):
        self.marcada.professor = self.outro_professor
        self.marcada.save()
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Esta aula estava marcada para Bruno I.")
        self.client.post(self.url, self.dados_do_registro(professor=self.outro_professor.pk))
        self.marcada.refresh_from_db()
        self.assertEqual(self.marcada.professor, self.professor)

    def test_supervisao_mantem_o_professor_marcado(self):
        self.marcada.professor = self.outro_professor
        self.marcada.save()
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.context["form"]["professor"].value(), self.outro_professor.pk)
        self.client.post(self.url, self.dados_do_registro(professor=self.outro_professor.pk))
        self.marcada.refresh_from_db()
        self.assertEqual(self.marcada.professor, self.outro_professor)
        self.assertEqual(self.marcada.registrada_por, self.supervisao)


class NaoRealizadaTestes(BaseDeAulas):
    def setUp(self):
        super().setUp()
        self.marcada = self.criar_aula(situacao=Aula.Situacao.MARCADA)
        self.url = reverse("aulas:nao_realizada", args=[self.marcada.pk])

    def test_motivo_e_obrigatorio(self):
        self.entrar(self.professor)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        resposta = self.client.post(self.url, {"motivo_nao_realizada": ""})
        self.assertContains(resposta, "Conte por que a aula não aconteceu")
        self.marcada.refresh_from_db()
        self.assertEqual(self.marcada.situacao, Aula.Situacao.MARCADA)

    def test_nao_aconteceu_grava_a_situacao_e_a_trilha(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, {"motivo_nao_realizada": "Exame no horário"}, follow=True)
        self.assertRedirects(resposta, reverse("aulas:detalhe", args=[self.marcada.pk]))
        self.marcada.refresh_from_db()
        self.assertEqual(self.marcada.situacao, Aula.Situacao.NAO_REALIZADA)
        self.assertEqual(self.marcada.motivo_nao_realizada, "Exame no horário")
        evento = EventoAuditoria.objects.filter(modelo="aulas.Aula", objeto_id=str(self.marcada.pk)).first()
        self.assertEqual(evento.acao, EventoAuditoria.Acao.ALTEROU)
        self.assertEqual(evento.motivo, "Exame no horário")
        self.assertEqual(evento.mudancas["situacao"]["para"], "Não aconteceu")
        self.assertContains(resposta, "Não aconteceu")
        self.assertContains(resposta, "Exame no horário")

    def test_quem_nao_edita_aulas_recebe_403(self):
        for pessoa in (self.apoio, self.leitor):
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url, {"motivo_nao_realizada": "Teste"}).status_code, 403)

    def test_aula_de_outro_servico_da_404(self):
        de_fora = self.criar_aula(
            servico=self.outro_servico, aluno=self.aluno_de_fora, professor=self.professor_de_fora,
            situacao=Aula.Situacao.MARCADA,
        )
        self.entrar(self.supervisao)
        url = reverse("aulas:nao_realizada", args=[de_fora.pk])
        self.assertEqual(self.client.post(url, {"motivo_nao_realizada": "Teste"}).status_code, 404)
        de_fora.refresh_from_db()
        self.assertEqual(de_fora.situacao, Aula.Situacao.MARCADA)

    def test_aula_registrada_nao_vira_nao_realizada(self):
        registrada = self.criar_aula()
        self.entrar(self.professor)
        url = reverse("aulas:nao_realizada", args=[registrada.pk])
        self.client.post(url, {"motivo_nao_realizada": "Engano"})
        registrada.refresh_from_db()
        self.assertEqual(registrada.situacao, Aula.Situacao.REGISTRADA)

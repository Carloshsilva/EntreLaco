"""Telas das reuniões: lista, marcar, detalhe e editar (RF-17, RF-44, SEG-05)."""
import datetime

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import EventoAuditoria, Vinculo
from core.testes import criar_professor
from reunioes.models import Reuniao

from .base import Acao, BaseReunioes


class ListaTestes(BaseReunioes):
    url = reverse("reunioes:lista")

    def test_pede_login(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("entrar"), resposta["Location"])

    def test_abre_para_quem_ve_as_atas(self):
        for pessoa in (self.professor, self.secretaria, self.supervisao):
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                resposta = self.client.get(self.url)
                self.assertEqual(resposta.status_code, 200)
                self.assertUmH1(resposta)
                self.assertContains(resposta, "Reunião semanal da equipe")
                self.assertContains(resposta, "Reunião multidisciplinar de outubro")

    def test_403_para_quem_nao_ve_as_atas(self):
        self.entrar(self.apoio)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_item_do_menu_so_para_quem_ve_as_atas(self):
        self.entrar(self.professor)
        self.assertContains(self.client.get(reverse("inicio")), f'href="{self.url}"')
        self.entrar(self.apoio)
        self.assertNotContains(self.client.get(reverse("inicio")), f'href="{self.url}"')

    def test_proximas_e_passadas_e_nada_de_outro_servico(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertEqual([r.pk for r in resposta.context["proximas"]], [self.reuniao.pk])
        self.assertEqual([r.pk for r in resposta.context["pagina"].object_list], [self.reuniao_passada.pk])
        self.assertNotContains(resposta, "Reunião do outro serviço")
        self.assertContains(resposta, 'data-label="Situação"')
        self.assertContains(resposta, "Realizada")

    def test_botao_marcar_so_para_quem_edita_as_atas(self):
        self.entrar(self.supervisao)
        self.assertContains(self.client.get(self.url), reverse("reunioes:nova"))
        self.entrar(self.professor)
        self.assertNotContains(self.client.get(self.url), reverse("reunioes:nova"))

    def test_numero_de_alunos_citados_conta_so_as_citacoes_visiveis(self):
        self.citar(aluno=self.aluno)
        self.citar(aluno=self.aluno, texto="Outra fala sobre a mesma aluna.")
        self.citar(aluno=self.aluno_dois, grupo="sensivel", texto="Fala de saúde inventada.")
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(self.url).context["proximas"][0].alunos_citados, 2)
        self.entrar(self.secretaria)
        self.assertEqual(self.client.get(self.url).context["proximas"][0].alunos_citados, 1)

    def test_citar_um_aluno_vindo_do_perfil(self):
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url, {"aluno": self.aluno.pk})
        self.assertContains(resposta, "Escolha a reunião em que você vai citar Lia M.")
        self.assertContains(resposta, f"{reverse('reunioes:citacao_nova', args=[self.reuniao.pk])}?aluno={self.aluno.pk}")

    def test_citar_vindo_do_perfil_nao_aparece_para_quem_so_ve(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url, {"aluno": self.aluno.pk})
        self.assertNotContains(resposta, reverse("reunioes:citacao_nova", args=[self.reuniao.pk]))

    def test_aluno_de_outro_servico_da_404(self):
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(self.url, {"aluno": self.aluno_de_fora.pk}).status_code, 404)

    def test_consultas_nao_crescem_com_o_numero_de_reunioes(self):
        self.entrar(self.supervisao)
        self.client.get(self.url)  # aquece sessão e menu
        with CaptureQueriesContext(connection) as poucas:
            self.client.get(self.url)
        for dia in range(15):
            reuniao = Reuniao.objects.create(
                servico=self.servico, titulo=f"Reunião inventada {dia}", data=self.hoje + datetime.timedelta(days=dia)
            )
            self.citar(reuniao=reuniao)
            Reuniao.objects.create(
                servico=self.servico, titulo=f"Reunião antiga {dia}", data=self.hoje - datetime.timedelta(days=dia + 1)
            )
        with CaptureQueriesContext(connection) as muitas:
            self.client.get(self.url)
        self.assertEqual(len(poucas), len(muitas))


class NovaReuniaoTestes(BaseReunioes):
    url = reverse("reunioes:nova")

    def dados(self, **extra):
        dados = {
            "tipo": "semanal", "titulo": "Reunião semanal inventada", "data": (self.hoje + datetime.timedelta(days=7)).isoformat(),
            "hora_inicio": "14:00", "duracao_minutos": "60", "local": "Sala inventada",
            "participantes": [self.supervisao.pk, self.professor.pk], "pauta": "Pauta inventada",
        }
        dados.update(extra)
        return dados

    def test_abre_para_quem_edita_as_atas(self):
        for pessoa in (self.supervisao, self.secretaria):
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                resposta = self.client.get(self.url)
                self.assertEqual(resposta.status_code, 200)
                self.assertUmH1(resposta)
                self.assertContains(resposta, "Marcar reunião")
                self.assertContains(resposta, 'type="checkbox" name="participantes"')

    def test_403_para_quem_so_ve_ou_nao_ve(self):
        for pessoa in (self.professor, self.apoio):
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url, self.dados()).status_code, 403)
        self.assertFalse(Reuniao.objects.filter(titulo="Reunião semanal inventada").exists())

    def test_marcar_grava_a_reuniao_e_a_trilha(self):
        self.entrar(self.secretaria)
        resposta = self.client.post(self.url, self.dados())
        reuniao = Reuniao.objects.get(titulo="Reunião semanal inventada")
        self.assertRedirects(resposta, reverse("reunioes:detalhe", args=[reuniao.pk]))
        self.assertEqual(reuniao.servico, self.servico)
        self.assertEqual(reuniao.criado_por, self.secretaria)
        self.assertEqual(set(reuniao.participantes.all()), {self.supervisao, self.professor})
        self.assertEqual(reuniao.situacao, Reuniao.Situacao.MARCADA)
        evento = EventoAuditoria.objects.get(modelo="reunioes.Reuniao", objeto_id=str(reuniao.pk))
        self.assertEqual(evento.acao, Acao.CRIOU)
        self.assertEqual(evento.usuario, self.secretaria)
        self.assertIn("participantes", evento.mudancas)

    def test_titulo_em_branco_usa_o_tipo(self):
        self.entrar(self.supervisao)
        self.client.post(self.url, self.dados(titulo="", tipo="tmo"))
        self.assertTrue(Reuniao.objects.filter(servico=self.servico, titulo="Reunião do TMO").exists())

    def test_participante_de_outro_servico_e_recusado(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(self.url, self.dados(participantes=[self.de_fora.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Escolha pessoas da lista da equipe.")
        self.assertFalse(Reuniao.objects.filter(titulo="Reunião semanal inventada").exists())

    def test_so_pessoas_ativas_do_servico_aparecem(self):
        saiu = criar_professor(self.servico, nome="Olga Saiu Inventada", email="olga@exemplo.org")
        Vinculo.objects.filter(usuario=saiu).update(ativo=False)
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Paula Professora Inventada")
        self.assertNotContains(resposta, "Flora De Fora Inventada")
        self.assertNotContains(resposta, "Olga Saiu Inventada")

    def test_quem_marca_ja_vem_como_participante_e_a_data_vem_da_url(self):
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url, {"data": "2026-11-03"})
        form = resposta.context["form"]
        self.assertEqual(form.initial["participantes"], [self.supervisao.pk])
        self.assertContains(resposta, 'value="2026-11-03"')

    def test_duracao_fora_do_limite(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(self.url, self.dados(duracao_minutos="0"))
        self.assertContains(resposta, "Informe a duração em minutos, entre 5 e 720.")
        self.assertContains(resposta, 'aria-invalid="true"')

    def test_sem_data_explica_o_que_fazer(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(self.url, self.dados(data=""))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Falta corrigir 1 ponto para salvar")


class DetalheTestes(BaseReunioes):
    def url(self, reuniao=None):
        return reverse("reunioes:detalhe", args=[(reuniao or self.reuniao).pk])

    def test_abre_para_quem_ve_as_atas(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url())
        self.assertEqual(resposta.status_code, 200)
        self.assertUmH1(resposta)
        self.assertContains(resposta, "Sala da equipe inventada")
        self.assertContains(resposta, "Paula Professora Inventada (você)")
        self.assertContains(resposta, "Revisão das pendências")
        self.assertContains(resposta, "A ata ainda não foi escrita.")

    def test_403_para_quem_nao_ve_as_atas(self):
        self.entrar(self.apoio)
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_reuniao_de_outro_servico_da_404(self):
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(self.url(self.reuniao_de_fora)).status_code, 404)

    def test_botoes_de_editar_e_citar_so_para_quem_edita(self):
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, reverse("reunioes:editar", args=[self.reuniao.pk]))
        self.assertContains(resposta, reverse("reunioes:citacao_nova", args=[self.reuniao.pk]))
        self.entrar(self.professor)
        resposta = self.client.get(self.url())
        self.assertNotContains(resposta, reverse("reunioes:editar", args=[self.reuniao.pk]))
        self.assertNotContains(resposta, reverse("reunioes:citacao_nova", args=[self.reuniao.pk]))

    def test_mostra_as_citacoes_com_encaminhamento(self):
        citacao = self.citar(
            encaminhamento="Levar livros de aventura inventados.", responsavel=self.professor,
            prazo=self.hoje + datetime.timedelta(days=5),
        )
        self.entrar(self.professor)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, f'id="citacao-{citacao.pk}"')
        self.assertContains(resposta, "Lia M.")
        self.assertContains(resposta, "Levar livros de aventura inventados.")
        self.assertContains(resposta, "Paula I. (você)")
        self.assertContains(resposta, "Pendente")
        # O responsável conclui o próprio encaminhamento, mas não edita a citação.
        self.assertContains(resposta, reverse("reunioes:citacao_concluir", args=[citacao.pk]))
        self.assertNotContains(resposta, reverse("reunioes:citacao_editar", args=[citacao.pk]))

    def test_citacao_de_saude_some_para_quem_nao_ve_saude(self):
        self.citar(aluno=self.aluno_dois, grupo="sensivel", texto="Fala de saúde inventada sobre o tratamento.")
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "Fala de saúde inventada sobre o tratamento.")
        self.assertContains(resposta, "Saúde e dados sensíveis")
        self.entrar(self.secretaria)
        resposta = self.client.get(self.url())
        self.assertNotContains(resposta, "Fala de saúde inventada")
        self.assertNotContains(resposta, "Caio P.")
        self.assertContains(resposta, "Nenhum aluno citado nesta reunião.")

    def test_historico_mostra_as_alteracoes_e_esconde_citacao_invisivel(self):
        self.entrar(self.supervisao)
        self.client.post(reverse("reunioes:citacao_nova", args=[self.reuniao.pk]), {
            "aluno": self.aluno_dois.pk, "texto": "Fala de saúde inventada.", "grupo_de_dado": "sensivel",
        })
        self.client.post(reverse("reunioes:citacao_nova", args=[self.reuniao.pk]), {
            "aluno": self.aluno.pk, "texto": "Fala sobre leitura.", "grupo_de_dado": "atas",
        })
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "Caio Fictício Prado na Reunião semanal da equipe")
        self.assertContains(resposta, "Lia Inventada Moreira na Reunião semanal da equipe")
        self.entrar(self.secretaria)
        resposta = self.client.get(self.url())
        self.assertNotContains(resposta, "Caio Fictício Prado")
        self.assertContains(resposta, "Lia Inventada Moreira na Reunião semanal da equipe")

    def test_consultas_nao_crescem_com_o_numero_de_citacoes(self):
        self.entrar(self.supervisao)
        self.citar(encaminhamento="Levar gibis.", responsavel=self.professor)
        self.client.get(self.url())
        with CaptureQueriesContext(connection) as poucas:
            self.client.get(self.url())
        for numero in range(10):
            self.citar(aluno=self.aluno_dois, texto=f"Fala inventada {numero}.", encaminhamento="Ligar para a escola.",
                       responsavel=self.professor_dois)
        with CaptureQueriesContext(connection) as muitas:
            self.client.get(self.url())
        self.assertEqual(len(poucas), len(muitas))

    def test_reuniao_cancelada_avisa_com_palavra(self):
        Reuniao.objects.filter(pk=self.reuniao.pk).update(situacao=Reuniao.Situacao.CANCELADA)
        self.entrar(self.professor)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "Esta reunião foi cancelada.")
        self.assertContains(resposta, '<span class="el-badge el-badge-danger">Cancelada</span>', html=True)


class EditarReuniaoTestes(BaseReunioes):
    def url(self, reuniao=None):
        return reverse("reunioes:editar", args=[(reuniao or self.reuniao).pk])

    def dados(self, **extra):
        dados = {
            "tipo": "semanal", "titulo": "Reunião semanal da equipe", "data": self.reuniao.data.isoformat(),
            "hora_inicio": "14:00", "duracao_minutos": "60", "local": "Sala da equipe inventada",
            "participantes": [self.supervisao.pk, self.professor.pk], "pauta": self.reuniao.pauta,
            "situacao": "marcada", "ata": "", "motivo_alteracao": "Mudou a sala.",
        }
        dados.update(extra)
        return dados

    def test_abre_para_quem_edita_as_atas(self):
        self.entrar(self.secretaria)
        resposta = self.client.get(self.url())
        self.assertEqual(resposta.status_code, 200)
        self.assertUmH1(resposta)
        self.assertContains(resposta, "Por que você está alterando?")
        self.assertContains(resposta, 'name="estado_original"')
        self.assertContains(resposta, 'name="ata"')

    def test_403_para_quem_so_ve(self):
        self.entrar(self.professor)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 403)

    def test_reuniao_de_outro_servico_da_404(self):
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(self.url(self.reuniao_de_fora)).status_code, 404)

    def test_salvar_grava_o_motivo_na_trilha(self):
        self.entrar(self.secretaria)
        resposta = self.client.post(self.url(), self.dados(local="Sala nova inventada", ata="Ata inventada."))
        self.assertRedirects(resposta, reverse("reunioes:detalhe", args=[self.reuniao.pk]))
        self.reuniao.refresh_from_db()
        self.assertEqual(self.reuniao.local, "Sala nova inventada")
        self.assertEqual(self.reuniao.versao, 2)
        evento = EventoAuditoria.objects.get(modelo="reunioes.Reuniao", objeto_id=str(self.reuniao.pk), acao=Acao.ALTEROU)
        self.assertEqual(evento.motivo, "Mudou a sala.")
        self.assertEqual(evento.mudancas["local"]["para"], "Sala nova inventada")
        self.assertIn("ata", evento.mudancas)

    def test_sem_motivo_nao_salva(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(self.url(), self.dados(local="Outra sala", motivo_alteracao=""))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Conte por que você está alterando")
        self.reuniao.refresh_from_db()
        self.assertEqual(self.reuniao.local, "Sala da equipe inventada")

    def test_reuniao_futura_nao_fica_realizada(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(self.url(), self.dados(situacao="realizada"))
        self.assertContains(resposta, "ainda não pode estar realizada")
        self.reuniao.refresh_from_db()
        self.assertEqual(self.reuniao.situacao, Reuniao.Situacao.MARCADA)

    def test_quem_saiu_da_equipe_continua_na_reuniao_antiga(self):
        Vinculo.objects.filter(usuario=self.professor).update(ativo=False)
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "Paula Professora Inventada")
        self.client.post(self.url(), self.dados(local="Sala nova inventada"))
        self.assertIn(self.professor, self.reuniao.participantes.all())

    def test_conflito_mostra_as_duas_versoes(self):
        self.entrar(self.supervisao)
        estado = self.client.get(self.url()).context["estado_original"]
        Reuniao.objects.filter(pk=self.reuniao.pk).update(local="Sala da outra pessoa", versao=2)
        resposta = self.client.post(self.url(), self.dados(local="Minha sala", estado_original=estado))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Outra pessoa salvou este cadastro enquanto você editava")
        self.assertNotContains(resposta, "Flora De Fora Inventada")  # o formulário refeito segue filtrado
        self.reuniao.refresh_from_db()
        self.assertEqual(self.reuniao.local, "Sala da outra pessoa")

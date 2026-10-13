"""Mudar situação (RF-11, RF-21, RF-22): motivo sempre, saída com motivo e responsável, trilha e histórico."""
from django.test import Client
from django.urls import reverse

from alunos.models import Aluno, MudancaDeSituacao

from .base import Acao, BaseAlunos, Situacao, dias_atras, hoje


class MudarSituacaoTestes(BaseAlunos):
    def setUp(self):
        self.url = reverse("alunos:situacao", args=[self.aluno.pk])

    def enviar(self, **dados):
        dados.setdefault("situacao_vista", self.aluno.situacao)
        dados.setdefault("data", hoje().isoformat())
        return self.client.post(self.url, dados)

    def test_abre_para_quem_tem_a_acao(self):
        for pessoa in (self.orientacao, self.supervisao):
            self.entrar(pessoa)
            resposta = self.client.get(self.url)
            self.assertEqual(resposta.status_code, 200)
            self.assertContains(resposta, '<h1 class="el-display">Mudar situação</h1>', html=True)
            self.assertContains(resposta, "Continua ativo")

    def test_403_sem_a_acao(self):
        for pessoa in (self.professor, self.apoio):
            self.entrar(pessoa)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.enviar(para="pausa", motivo="Teste").status_code, 403)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.situacao, Situacao.ATIVO)

    def test_404_para_aluno_de_outro_servico(self):
        self.entrar(self.orientacao)
        url = reverse("alunos:situacao", args=[self.aluno_de_fora.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, {"para": "pausa", "motivo": "x", "data": hoje().isoformat()}).status_code,
                         404)

    def test_sem_motivo_nao_salva(self):
        self.entrar(self.orientacao)
        resposta = self.enviar(para="pausa", motivo="   ")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Conte o motivo da mudança")
        self.assertFalse(MudancaDeSituacao.objects.exists())
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.situacao, Situacao.ATIVO)

    def test_encerrar_sem_motivo_de_saida_ou_responsavel_nao_salva(self):
        self.entrar(self.orientacao)
        resposta = self.enviar(para="encerrado", motivo="A família avisou da alta.")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Escolha o motivo de saída para encerrar o aluno.")
        self.assertContains(resposta, "Escolha a pessoa responsável pela saída para encerrar o aluno.")

        resposta = self.enviar(para="encerrado", motivo="A família avisou da alta.", motivo_saida="Alta")
        self.assertContains(resposta, "Escolha a pessoa responsável pela saída")

        resposta = self.enviar(para="encerrado", motivo="A família avisou da alta.",
                               responsavel=str(self.orientacao.pk))
        self.assertContains(resposta, "Escolha o motivo de saída")

        resposta = self.enviar(para="encerrado", motivo="A família avisou da alta.", motivo_saida="Alta",
                               responsavel=str(self.orientacao.pk), data="")
        self.assertContains(resposta, "Falta a data")
        self.assertFalse(MudancaDeSituacao.objects.exists())
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.situacao, Situacao.ATIVO)

    def test_encerrar_grava_mudanca_aluno_e_trilha(self):
        self.entrar(self.orientacao)
        data = dias_atras(2)
        resposta = self.enviar(para="encerrado", motivo="Alta hospitalar confirmada.", motivo_saida="Alta",
                               responsavel=str(self.professor.pk), data=data.isoformat())
        self.assertRedirects(resposta, reverse("alunos:detalhe", args=[self.aluno.pk]) + "#secao-situacao",
                             fetch_redirect_response=False)
        mudanca = MudancaDeSituacao.objects.get()
        self.assertEqual((mudanca.de, mudanca.para), (Situacao.ATIVO, Situacao.ENCERRADO))
        self.assertEqual(mudanca.motivo_saida, "Alta")
        self.assertEqual(mudanca.responsavel, self.professor)
        self.assertEqual(mudanca.criado_por, self.orientacao)
        self.assertEqual(mudanca.servico, self.servico)
        self.assertEqual(mudanca.data, data)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.situacao, Situacao.ENCERRADO)
        self.assertEqual(self.aluno.situacao_desde, data)
        self.assertEqual(self.aluno.versao, 2)
        evento = self.eventos(acao=Acao.MUDOU_SITUACAO).get()
        self.assertEqual(evento.aluno_id, self.aluno.pk)
        self.assertEqual(evento.motivo, "Alta hospitalar confirmada.")
        self.assertEqual(evento.mudancas["situacao"]["de"], "Ativo")
        self.assertEqual(evento.mudancas["situacao"]["para"], "Encerrado")
        self.assertEqual(evento.mudancas["motivo_saida"]["para"], "Alta")
        self.assertEqual(evento.mudancas["responsavel_saida"]["para"], self.professor.nome)

    def test_volta_a_ativo_tambem_pede_motivo(self):
        Aluno.objects.filter(pk=self.aluno.pk).update(situacao=Situacao.PAUSA)
        self.aluno.refresh_from_db()
        self.entrar(self.orientacao)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Ativo, volta aos atendimentos")
        self.assertNotContains(resposta, "Continua ativo")
        self.assertContains(self.enviar(para="ativo", motivo=""), "Conte o motivo da mudança")
        self.enviar(para="ativo", motivo="Voltou para a internação.")
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.situacao, Situacao.ATIVO)
        self.assertEqual(MudancaDeSituacao.objects.get().de, Situacao.PAUSA)

    def test_continua_ativo_registra_a_revisao(self):
        Aluno.objects.filter(pk=self.aluno.pk).update(situacao_desde=dias_atras(60))
        self.aluno.refresh_from_db()
        self.entrar(self.orientacao)
        resposta = self.enviar(para="ativo", motivo="Aula marcada para a semana que vem.")
        self.assertEqual(resposta.status_code, 302)
        mudanca = MudancaDeSituacao.objects.get()
        self.assertEqual((mudanca.de, mudanca.para), (Situacao.ATIVO, Situacao.ATIVO))
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.situacao_desde, dias_atras(60))
        evento = self.eventos(acao=Acao.MUDOU_SITUACAO).get()
        self.assertEqual(evento.descricao, "Revisou a situação: continua ativo")
        self.assertEqual(evento.mudancas["situacao"], {"rotulo": "situação", "grupo": "identificacao",
                                                       "de": "Ativo", "para": "Ativo"})
        perfil = self.client.get(reverse("alunos:detalhe", args=[self.aluno.pk]))
        self.assertContains(perfil, "Revisão: continua ativo")

    def test_responsavel_de_outro_servico_nao_vale(self):
        self.entrar(self.orientacao)
        resposta = self.enviar(para="encerrado", motivo="Alta.", motivo_saida="Alta", responsavel=str(self.de_fora.pk))
        self.assertContains(resposta, "Escolha uma pessoa da equipe do serviço.")
        self.assertNotContains(self.client.get(self.url), "Flora De Fora Inventada")
        self.assertFalse(MudancaDeSituacao.objects.exists())

    def test_motivo_de_saida_vem_da_configuracao_do_servico(self):
        self.servico.motivos_saida = ["Alta", "Mudou de cidade"]
        self.servico.save()
        self.entrar(self.orientacao)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Mudou de cidade")
        self.assertNotContains(resposta, "Óbito")
        resposta = self.enviar(para="encerrado", motivo="x", motivo_saida="Óbito", responsavel=str(self.orientacao.pk))
        self.assertContains(resposta, "Escolha um dos motivos de saída da lista.")
        self.assertFalse(MudancaDeSituacao.objects.exists())

    def test_data_no_futuro_nao_vale(self):
        self.entrar(self.orientacao)
        resposta = self.enviar(para="pausa", motivo="Exames.", data=dias_atras(-3).isoformat())
        self.assertContains(resposta, "A data não pode ser depois de hoje")
        self.assertFalse(MudancaDeSituacao.objects.exists())

    def test_outra_pessoa_mudou_no_meio_e_nada_e_salvo(self):
        self.entrar(self.orientacao)
        tela = self.client.get(self.url)
        self.assertContains(tela, 'name="situacao_vista" value="ativo"')
        outra = Client()
        outra.force_login(self.supervisao)
        outra.post(self.url, {"para": "pausa", "motivo": "Exames longos.", "data": hoje().isoformat(),
                              "situacao_vista": "ativo"})
        resposta = self.enviar(para="encerrado", motivo="Alta.", motivo_saida="Alta",
                               responsavel=str(self.orientacao.pk), situacao_vista="ativo")
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Enquanto você preenchia, Sueli I. mudou a situação para Em pausa.")
        self.assertContains(resposta, 'name="situacao_vista" value="pausa"')
        self.assertEqual(MudancaDeSituacao.objects.count(), 1)
        self.aluno.refresh_from_db()
        self.assertEqual(self.aluno.situacao, Situacao.PAUSA)

    def test_historico_no_perfil_com_motivo_pessoa_e_data(self):
        self.entrar(self.orientacao)
        self.enviar(para="pausa", motivo="Exames longos.", data=dias_atras(1).isoformat())
        resposta = self.client.get(reverse("alunos:detalhe", args=[self.aluno.pk]))
        self.assertContains(resposta, "<strong>Ativo → Em pausa</strong>", html=True)
        self.assertContains(resposta, f"a partir de {dias_atras(1):%d/%m/%Y}")
        self.assertContains(resposta, "Motivo: Exames longos.")
        self.assertContains(resposta, "Registrado por Olga Orientadora Inventada")
        self.assertContains(resposta, "Em pausa</span>")


class ProfessorDomiciliarTestes(BaseAlunos):
    """Alta do TMO: o responsável pela saída vê se precisa de professor domiciliar (RF-24)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Aluno.objects.filter(pk=cls.aluno.pk).update(tmo=True, situacao=Situacao.ENCERRADO)
        cls.aluno.refresh_from_db()
        cls.saida = MudancaDeSituacao.objects.create(
            servico=cls.servico, aluno=cls.aluno, de=Situacao.ATIVO, para=Situacao.ENCERRADO, data=dias_atras(1),
            motivo="Alta do transplante.", motivo_saida="Alta", responsavel=cls.professor, criado_por=cls.orientacao,
        )

    def setUp(self):
        self.url = reverse("alunos:domiciliar", args=[self.saida.pk])

    def test_responsavel_pela_saida_ve_o_formulario_no_perfil(self):
        self.entrar(self.professor)
        resposta = self.client.get(reverse("alunos:detalhe", args=[self.aluno.pk]))
        self.assertContains(resposta, f'action="{self.url}"')
        self.assertContains(resposta, "Saída por alta do TMO")
        self.entrar(self.professor_b)
        resposta = self.client.get(reverse("alunos:detalhe", args=[self.aluno.pk]))
        self.assertNotContains(resposta, f'action="{self.url}"')
        self.assertContains(resposta, "A pendência está com Paula I.")

    def test_quem_nao_ve_saude_nao_ve_o_bloco_que_revelaria_o_tmo(self):
        self.entrar(self.so_ver)
        resposta = self.client.get(reverse("alunos:detalhe", args=[self.aluno.pk]))
        self.assertContains(resposta, "Alta do transplante.")
        self.assertNotContains(resposta, "Professor domiciliar")

    def test_registrar_pede_a_observacao(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, {"observacao": "  "})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Conte o que foi decidido")
        self.saida.refresh_from_db()
        self.assertIsNone(self.saida.domiciliar_verificado_em)

    def test_registrar_grava_e_vai_para_a_trilha(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, {"observacao": "Não precisa: volta à escola no mês que vem."})
        self.assertRedirects(resposta, reverse("alunos:detalhe", args=[self.aluno.pk]) + "#secao-situacao",
                             fetch_redirect_response=False)
        self.saida.refresh_from_db()
        self.assertEqual(self.saida.domiciliar_verificado_em, hoje())
        self.assertEqual(self.saida.domiciliar_verificado_por, self.professor)
        self.assertEqual(self.saida.domiciliar_observacao, "Não precisa: volta à escola no mês que vem.")
        evento = self.eventos(acao=Acao.ALTEROU, modelo="alunos.MudancaDeSituacao").get()
        self.assertEqual(evento.aluno_id, self.aluno.pk)
        self.assertEqual(evento.descricao, "Registrou a decisão sobre o professor domiciliar")
        perfil = self.client.get(reverse("alunos:detalhe", args=[self.aluno.pk]))
        self.assertContains(perfil, "Não precisa: volta à escola no mês que vem.")
        self.assertNotContains(perfil, f'action="{self.url}"')

    def test_quem_muda_situacao_tambem_registra(self):
        self.entrar(self.orientacao)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url, {"observacao": "Família pediu; encaminhado."}).status_code, 302)

    def test_403_para_quem_nao_e_responsavel_nem_muda_situacao(self):
        self.entrar(self.professor_b)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"observacao": "x"}).status_code, 403)

    def test_404_para_saida_de_outro_servico(self):
        saida_de_fora = MudancaDeSituacao.objects.create(
            servico=self.outro_servico, aluno=self.aluno_de_fora, de=Situacao.ATIVO, para=Situacao.ENCERRADO,
            motivo="x", motivo_saida="Alta",
        )
        self.entrar(self.orientacao)
        self.assertEqual(self.client.get(reverse("alunos:domiciliar", args=[saida_de_fora.pk])).status_code, 404)

    def test_quem_nao_ve_saude_nao_le_tmo(self):
        papel_responsavel = self.so_ver.vinculos.get().papel
        papel_responsavel.acoes = ["mudar_situacao"]
        papel_responsavel.save()
        self.entrar(self.so_ver)
        resposta = self.client.get(reverse("alunos:detalhe", args=[self.aluno.pk]))
        self.assertContains(resposta, "Saída por alta:")
        self.assertNotContains(resposta, "TMO")

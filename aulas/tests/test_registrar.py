"""Registrar aula (RF-15), com aluno ainda não cadastrado (RF-19), fotos e BNCC (RF-16)."""
import datetime
from unittest import mock

from django.urls import reverse
from PIL import Image

from alunos.models import Aluno, Responsavel
from aulas.models import Aula, FotoDaAula
from core.models import EventoAuditoria
from core.registro import Pendencia, pendencias_para
from core.testes import criar_papel, criar_pessoa

from .base import HOJE, BaseDeAulas, foto_de_teste


class RegistrarAulaTestes(BaseDeAulas):
    url = reverse("aulas:registrar")

    def test_abre_para_quem_edita_aulas(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'enctype="multipart/form-data"')
        self.assertContains(resposta, 'name="novas_fotos"')
        self.assertContains(resposta, "multiple")
        self.assertContains(resposta, "Registrar aula")
        self.assertContains(resposta, "<h1", count=1)

    def test_quem_nao_edita_aulas_recebe_403(self):
        for pessoa in (self.apoio, self.leitor):
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(self.client.post(self.url, self.dados_do_registro()).status_code, 403)
        self.assertFalse(Aula.objects.exists())

    def test_opcoes_so_do_servico(self):
        self.entrar(self.professor)
        form = self.client.get(self.url).context["form"]
        alunos = set(form.fields["aluno"].queryset)
        self.assertEqual(alunos, {self.aluno, self.aluno_em_pausa})
        self.assertNotIn(self.aluno_de_fora, alunos)
        self.assertNotIn(self.aluno_encerrado, alunos)
        self.assertEqual(list(form.fields["componentes"].queryset), [self.componente])

    def test_aluno_vem_escolhido_pelo_endereco(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url, {"aluno": self.aluno.pk})
        self.assertEqual(resposta.context["form"].initial["aluno"], self.aluno.pk)
        resposta = self.client.get(self.url, {"aluno": self.aluno_de_fora.pk})
        self.assertNotIn("aluno", resposta.context["form"].initial)

    def test_registrar_grava_a_aula_e_a_trilha(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, self.dados_do_registro(duracao_minutos="60"), follow=True)
        aula = Aula.objects.get()
        self.assertRedirects(resposta, reverse("aulas:detalhe", args=[aula.pk]))
        self.assertEqual(aula.situacao, Aula.Situacao.REGISTRADA)
        self.assertEqual(aula.professor, self.professor)
        self.assertEqual(aula.registrada_por, self.professor)
        self.assertIsNotNone(aula.registrada_em)
        self.assertEqual(aula.servico, self.servico)
        self.assertEqual(list(aula.componentes.all()), [self.componente])
        evento = EventoAuditoria.objects.get(modelo="aulas.Aula", objeto_id=str(aula.pk))
        self.assertEqual(evento.acao, EventoAuditoria.Acao.CRIOU)
        self.assertEqual(evento.usuario, self.professor)
        self.assertEqual(evento.aluno_id, self.aluno.pk)
        self.assertContains(resposta, "Aula de Lia I. registrada.")
        self.assertContains(resposta, "2 aulas pela regra de 30 minutos")

    def test_mensagem_avisa_a_pendencia_da_ficha(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, self.dados_do_registro(), follow=True)
        self.assertContains(resposta, "A ficha de Lia I. está incompleta")
        self.assertContains(resposta, "A pendência de completar a ficha foi criada para você.")

    def test_aluno_de_outro_servico_nao_entra(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, self.dados_do_registro(aluno=self.aluno_de_fora.pk))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Esse aluno não está na lista do serviço")
        self.assertFalse(Aula.objects.exists())

    def test_componente_de_outro_servico_nao_entra(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, self.dados_do_registro(componentes=[self.componente_de_fora.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Aula.objects.exists())

    def test_data_no_futuro_nao_e_registro(self):
        self.entrar(self.professor)
        amanha = (HOJE() + datetime.timedelta(days=1)).isoformat()
        resposta = self.client.post(self.url, self.dados_do_registro(data=amanha))
        self.assertContains(resposta, "use Marcar aula")
        self.assertFalse(Aula.objects.exists())

    def test_minutos_precisam_fazer_sentido(self):
        self.entrar(self.professor)
        for minutos in ("0", "900"):
            with self.subTest(minutos=minutos):
                resposta = self.client.post(self.url, self.dados_do_registro(duracao_minutos=minutos))
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, "el-form-errors")
        self.assertFalse(Aula.objects.exists())


class AlunoNovoTestes(BaseDeAulas):
    """RF-19: o professor registra aula antes do cadastro completo."""

    url = reverse("aulas:registrar")

    def test_registrar_com_aluno_novo_cria_o_aluno_e_a_aula(self):
        self.entrar(self.professor)
        dados = self.dados_do_registro(aluno="", aluno_novo="  Nina   Barros Inventada ")
        resposta = self.client.post(self.url, dados, follow=True)
        aluno = Aluno.objects.get(nome="Nina Barros Inventada")
        self.assertEqual(aluno.servico, self.servico)
        self.assertEqual(aluno.criado_por, self.professor)
        aula = Aula.objects.get(aluno=aluno)
        self.assertEqual(aula.situacao, Aula.Situacao.REGISTRADA)
        self.assertTrue(EventoAuditoria.objects.filter(
            modelo="alunos.Aluno", objeto_id=str(aluno.pk), acao=EventoAuditoria.Acao.CRIOU, usuario=self.professor,
        ).exists())
        self.assertContains(resposta, "O cadastro de Nina I. foi criado só com o nome.")
        self.assertContains(resposta, "A pendência de completar a ficha foi criada para você.")
        # A pendência existe na hora, para quem deu a aula.
        chaves = [p.chave for p in pendencias_para(self.requisicao(self.professor))]
        self.assertIn(f"ficha-{aluno.pk}-{self.professor.pk}", chaves)
        chaves_do_colega = [p.chave for p in pendencias_para(self.requisicao(self.outro_professor))]
        self.assertNotIn(f"ficha-{aluno.pk}-{self.professor.pk}", chaves_do_colega)

    def test_aluno_da_lista_e_nome_novo_juntos_pede_para_escolher(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, self.dados_do_registro(aluno_novo="Nina Barros Inventada"))
        self.assertContains(resposta, "Deixe só um")
        self.assertFalse(Aula.objects.exists())
        self.assertFalse(Aluno.objects.filter(nome="Nina Barros Inventada").exists())

    def test_sem_aluno_nenhum(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, self.dados_do_registro(aluno=""))
        self.assertContains(resposta, "Falta o aluno. Escolha na lista")
        self.assertFalse(Aula.objects.exists())

    def test_sem_editar_identificacao_nao_cadastra_aluno(self):
        papel = criar_papel(self.servico, "Só aulas", editar=["aulas"], ver=["identificacao"])
        pessoa = criar_pessoa(self.servico, papel, nome="Iara Mota Inventada")
        self.entrar(pessoa)
        resposta = self.client.get(self.url)
        self.assertNotIn("aluno_novo", resposta.context["form"].fields)
        resposta = self.client.post(self.url, self.dados_do_registro(aluno="", aluno_novo="Nina Barros Inventada"))
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Aluno.objects.filter(nome="Nina Barros Inventada").exists())
        self.assertFalse(Aula.objects.exists())


class ProfessorDaAulaTestes(BaseDeAulas):
    url = reverse("aulas:registrar")

    def test_professor_sem_permissao_nao_registra_em_nome_de_outro(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertNotIn("professor", resposta.context["form"].fields)
        self.assertNotContains(resposta, 'name="professor"')
        self.client.post(self.url, self.dados_do_registro(professor=self.outro_professor.pk))
        self.assertEqual(Aula.objects.get().professor, self.professor)

    def test_quem_ve_tarefas_de_todos_escolhe_o_professor(self):
        self.entrar(self.supervisao)
        resposta = self.client.get(self.url)
        campo = resposta.context["form"].fields["professor"]
        self.assertIn(self.outro_professor, campo.queryset)
        self.assertNotIn(self.professor_de_fora, campo.queryset)
        self.client.post(self.url, self.dados_do_registro(professor=self.outro_professor.pk))
        aula = Aula.objects.get()
        self.assertEqual(aula.professor, self.outro_professor)
        self.assertEqual(aula.registrada_por, self.supervisao)

    def test_professor_de_outro_servico_nao_entra(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(self.url, self.dados_do_registro(professor=self.professor_de_fora.pk))
        self.assertContains(resposta, "Essa pessoa não está na equipe do serviço")
        self.assertFalse(Aula.objects.exists())


class FotosNoRegistroTestes(BaseDeAulas):
    url = reverse("aulas:registrar")

    def test_varias_fotos_de_uma_vez_e_sem_exif(self):
        original = foto_de_teste(com_exif=True)
        self.assertTrue(Image.open(original).getexif())  # a foto enviada tem EXIF
        original.seek(0)
        self.entrar(self.professor)
        dados = self.dados_do_registro(novas_fotos=[original, foto_de_teste("segunda.png", formato="PNG")])
        resposta = self.client.post(self.url, dados, follow=True)
        aula = Aula.objects.get()
        fotos = list(aula.fotos.all())
        self.assertEqual(len(fotos), 2)
        self.assertContains(resposta, "registrada com 2 fotos")
        for foto in fotos:
            self.assertEqual(foto.servico, self.servico)
            self.assertIn(f"servico_{self.servico.pk}/aulas/", foto.arquivo.name)
            with foto.arquivo.open("rb") as arquivo:
                imagem = Image.open(arquivo)
                imagem.load()
                self.assertEqual(len(imagem.getexif()), 0)
                self.assertNotIn("exif", imagem.info)
        self.assertEqual(
            EventoAuditoria.objects.filter(modelo="aulas.FotoDaAula", acao=EventoAuditoria.Acao.CRIOU).count(), 2
        )
        self.assertContains(resposta, reverse("aulas:foto", args=[fotos[0].pk]))

    def test_mais_de_dez_fotos_nao_entra(self):
        self.entrar(self.professor)
        fotos = [foto_de_teste(f"foto{n}.jpg") for n in range(11)]
        resposta = self.client.post(self.url, self.dados_do_registro(novas_fotos=fotos))
        self.assertContains(resposta, "Você escolheu 11 fotos. Envie até 10 por vez")
        self.assertContains(resposta, "escolha de novo antes de salvar")
        self.assertFalse(Aula.objects.exists())
        self.assertFalse(FotoDaAula.objects.exists())

    def test_arquivo_que_nao_e_foto(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.entrar(self.professor)
        texto = SimpleUploadedFile("anotacao.jpg", b"isto nao e uma foto", content_type="image/jpeg")
        resposta = self.client.post(self.url, self.dados_do_registro(novas_fotos=[texto]))
        self.assertContains(resposta, "não é uma foto que a plataforma consegue abrir")
        self.assertFalse(Aula.objects.exists())


class BnccNoRegistroTestes(BaseDeAulas):
    """RF-16: desligada, o registro não mostra o campo; ligada, a pessoa escolhe itens da lista do serviço."""

    url = reverse("aulas:registrar")

    def test_habilidades_so_aparecem_com_a_bncc_ligada(self):
        ativa = self.criar_habilidade("EF01LP01")
        self.criar_habilidade("EF01LP02", ativa=False)
        self.criar_habilidade("EF01LP01", servico=self.outro_servico)
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertNotIn("habilidades", resposta.context["form"].fields)
        self.assertNotContains(resposta, "Habilidades da BNCC")
        # Com a lista desligada, um envio com habilidades é ignorado.
        self.client.post(self.url, self.dados_do_registro(habilidades=[ativa.pk]))
        self.assertFalse(Aula.objects.get().habilidades.exists())

        self.servico.bncc_ativa = True
        self.servico.save()
        resposta = self.client.get(self.url)
        self.assertEqual(list(resposta.context["form"].fields["habilidades"].queryset), [ativa])
        self.assertContains(resposta, "Habilidades da BNCC")
        self.client.post(self.url, self.dados_do_registro(habilidades=[ativa.pk]))
        self.assertEqual(list(Aula.objects.order_by("-pk").first().habilidades.all()), [ativa])


class AvisoDaFichaTestes(BaseDeAulas):
    """RF-19: a mensagem diz que a pendência da ficha foi criada para quem deu a aula, e só quando ela existe.

    A pendência é calculada pelo módulo de alunos; aqui uma fonte falsa isola a regra da mensagem.
    """

    url = reverse("aulas:registrar")

    def fonte_da_ficha(self, request, usuario, todas):
        return [Pendencia(
            titulo="Completar a ficha", url="/", tipo="Ficha incompleta", chave=f"ficha-{self.aluno.pk}-{usuario.pk}",
        )]

    def registrar(self, fontes, **dados):
        with mock.patch("core.registro._FONTES_DE_PENDENCIA", fontes):
            return self.client.post(self.url, self.dados_do_registro(**dados), follow=True)

    def test_criada_na_primeira_aula_e_continua_nas_seguintes(self):
        self.entrar(self.professor)
        resposta = self.registrar([self.fonte_da_ficha])
        self.assertContains(resposta, "A ficha de Lia I. está incompleta: falta data de nascimento")
        self.assertContains(resposta, "A pendência de completar a ficha foi criada para você.")
        resposta = self.registrar([self.fonte_da_ficha])
        self.assertContains(resposta, "A pendência de completar a ficha continua com você.")

    def test_registro_em_nome_de_outro_professor(self):
        self.entrar(self.supervisao)
        resposta = self.registrar([self.fonte_da_ficha], professor=self.outro_professor.pk)
        self.assertContains(resposta, "A pendência de completar a ficha foi criada para Bruno I.")
        self.assertNotContains(resposta, "Bruno I..")

    def test_sem_a_pendencia_a_mensagem_nao_promete(self):
        self.entrar(self.professor)
        resposta = self.registrar([])
        self.assertContains(resposta, "A ficha de Lia I. está incompleta")
        self.assertNotContains(resposta, "A pendência de completar a ficha")

    def test_ficha_completa_nao_tem_aviso(self):
        self.aluno.data_nascimento = datetime.date(2016, 5, 1)
        self.aluno.unidade = "Internação inventada"
        self.aluno.ano_escolar = "3ano"
        self.aluno.sem_matricula = True
        self.aluno.save()
        Responsavel.objects.create(servico=self.servico, aluno=self.aluno, nome="Rita Inventada", parentesco="mae")
        self.entrar(self.professor)
        resposta = self.registrar([self.fonte_da_ficha])
        self.assertContains(resposta, "Aula de Lia I. registrada.")
        self.assertNotContains(resposta, "está incompleta")

    def test_defeito_em_outro_modulo_nao_derruba_o_registro(self):
        def quebrada(request, usuario, todas):
            raise RuntimeError("defeito inventado")

        self.entrar(self.professor)
        with self.assertLogs("aulas.views", level="ERROR"):
            resposta = self.registrar([quebrada])
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Aula.objects.count(), 1)
        self.assertContains(resposta, "Aula de Lia I. registrada.")

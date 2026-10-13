"""Detalhe da aula, edição com motivo e conflito (RNF-04) e fotos (só por view protegida)."""
from django.db.models import F
from django.urls import reverse

from aulas.models import Aula, FotoDaAula
from core.models import EventoAuditoria

from .base import BaseDeAulas, foto_de_teste


class DetalheTestes(BaseDeAulas):
    def setUp(self):
        super().setUp()
        self.aula = self.criar_aula(minutos=60, conteudo="Contagem com tampinhas inventadas.")
        self.aula.componentes.add(self.componente)
        self.url = reverse("aulas:detalhe", args=[self.aula.pk])

    def test_abre_para_quem_ve_aulas(self):
        self.entrar(self.leitor)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "<h1", count=1)
        self.assertContains(resposta, "Aula com Lia I.")
        self.assertContains(resposta, "2 aulas pela regra de 30 minutos")
        self.assertContains(resposta, "Matemática")
        self.assertContains(resposta, "Histórico da aula")
        # Quem só vê não recebe os botões de editar e de fotos.
        self.assertNotContains(resposta, reverse("aulas:editar", args=[self.aula.pk]))
        self.assertNotContains(resposta, reverse("aulas:foto_nova", args=[self.aula.pk]))

    def test_quem_edita_ve_os_botoes(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, reverse("aulas:editar", args=[self.aula.pk]))
        self.assertContains(resposta, reverse("aulas:foto_nova", args=[self.aula.pk]))

    def test_marcada_mostra_registrar_e_nao_aconteceu(self):
        marcada = self.criar_aula(situacao=Aula.Situacao.MARCADA)
        self.entrar(self.professor)
        resposta = self.client.get(reverse("aulas:detalhe", args=[marcada.pk]))
        self.assertContains(resposta, reverse("aulas:registrar_marcada", args=[marcada.pk]))
        self.assertContains(resposta, reverse("aulas:nao_realizada", args=[marcada.pk]))
        self.assertContains(resposta, "Conta quando a aula for registrada")

    def test_apoio_administrativo_recebe_403(self):
        self.entrar(self.apoio)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_aula_de_outro_servico_da_404(self):
        de_fora = self.criar_aula(servico=self.outro_servico, aluno=self.aluno_de_fora, professor=self.professor_de_fora)
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(reverse("aulas:detalhe", args=[de_fora.pk])).status_code, 404)

    def test_fotos_na_galeria_apontam_para_a_view_protegida(self):
        foto = FotoDaAula.objects.create(servico=self.servico, aula=self.aula, arquivo=foto_de_teste(), legenda="Cartaz")
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'class="el-gallery"')
        self.assertContains(resposta, f'src="{reverse("aulas:foto", args=[foto.pk])}"')
        self.assertContains(resposta, 'hx-boost="false"')
        self.assertNotContains(resposta, foto.arquivo.name)


class EditarTestes(BaseDeAulas):
    def setUp(self):
        super().setUp()
        self.aula = self.criar_aula(conteudo="Versão inicial inventada.")
        self.url = reverse("aulas:editar", args=[self.aula.pk])

    def dados(self, **mudancas):
        resposta = self.client.get(self.url)
        dados = self.dados_do_registro(
            conteudo="Versão corrigida inventada.", motivo_alteracao="Corrigi o que foi trabalhado.",
            estado_original=resposta.context["estado_original"],
        )
        dados.update(mudancas)
        return dados

    def test_editar_pede_motivo_e_grava_a_trilha(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Por que você está alterando?")
        self.assertNotIn("professor", resposta.context["form"].fields)
        sem_motivo = self.client.post(self.url, self.dados(motivo_alteracao=""))
        self.assertContains(sem_motivo, "Conte por que você está alterando")
        self.aula.refresh_from_db()
        self.assertEqual(self.aula.conteudo, "Versão inicial inventada.")

        resposta = self.client.post(self.url, self.dados(), follow=True)
        self.assertRedirects(resposta, reverse("aulas:detalhe", args=[self.aula.pk]))
        self.aula.refresh_from_db()
        self.assertEqual(self.aula.conteudo, "Versão corrigida inventada.")
        evento = EventoAuditoria.objects.filter(modelo="aulas.Aula", objeto_id=str(self.aula.pk)).first()
        self.assertEqual(evento.acao, EventoAuditoria.Acao.ALTEROU)
        self.assertEqual(evento.motivo, "Corrigi o que foi trabalhado.")
        self.assertIn("conteudo", evento.mudancas)
        self.assertContains(resposta, "Corrigi o que foi trabalhado.")

    def test_conflito_mostra_as_duas_versoes_e_nao_salva(self):
        self.entrar(self.professor)
        dados = self.dados()
        # Outra pessoa salva o mesmo campo enquanto esta edita.
        Aula.objects.filter(pk=self.aula.pk).update(conteudo="Versão da outra pessoa.", versao=F("versao") + 1)
        resposta = self.client.post(self.url, dados)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Outra pessoa salvou este cadastro enquanto você editava")
        self.assertContains(resposta, "Versão da outra pessoa.")
        self.aula.refresh_from_db()
        self.assertEqual(self.aula.conteudo, "Versão da outra pessoa.")

    def test_professor_sem_permissao_nao_troca_o_professor(self):
        self.entrar(self.professor)
        self.client.post(self.url, self.dados(professor=self.outro_professor.pk))
        self.aula.refresh_from_db()
        self.assertEqual(self.aula.professor, self.professor)

    def test_quem_nao_edita_recebe_403(self):
        for pessoa in (self.apoio, self.leitor):
            with self.subTest(pessoa=pessoa.nome):
                self.entrar(pessoa)
                self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_aula_de_outro_servico_da_404(self):
        de_fora = self.criar_aula(servico=self.outro_servico, aluno=self.aluno_de_fora, professor=self.professor_de_fora)
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(reverse("aulas:editar", args=[de_fora.pk])).status_code, 404)

    def test_campos_conforme_a_situacao(self):
        marcada = self.criar_aula(situacao=Aula.Situacao.MARCADA)
        nao_realizada = self.criar_aula(situacao=Aula.Situacao.NAO_REALIZADA, motivo_nao_realizada="Exame")
        self.entrar(self.professor)
        campos = self.client.get(reverse("aulas:editar", args=[marcada.pk])).context["form"].fields
        self.assertNotIn("conteudo", campos)
        campos = self.client.get(reverse("aulas:editar", args=[nao_realizada.pk])).context["form"].fields
        self.assertIn("motivo_nao_realizada", campos)


class FotoTestes(BaseDeAulas):
    def setUp(self):
        super().setUp()
        self.aula = self.criar_aula()
        self.foto = FotoDaAula.objects.create(servico=self.servico, aula=self.aula, arquivo=foto_de_teste())
        self.url = reverse("aulas:foto", args=[self.foto.pk])

    def test_foto_sai_para_quem_ve_aulas(self):
        self.entrar(self.leitor)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta["Content-Type"].startswith("image/"))
        self.assertIn("no-store", resposta["Cache-Control"])
        b"".join(resposta.streaming_content)

    def test_sem_login_nao_sai(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)

    def test_apoio_administrativo_recebe_403(self):
        self.entrar(self.apoio)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_foto_de_outro_servico_da_404(self):
        aula_de_fora = self.criar_aula(servico=self.outro_servico, aluno=self.aluno_de_fora, professor=self.professor_de_fora)
        foto_de_fora = FotoDaAula.objects.create(servico=self.outro_servico, aula=aula_de_fora, arquivo=foto_de_teste())
        self.entrar(self.supervisao)
        self.assertEqual(self.client.get(reverse("aulas:foto", args=[foto_de_fora.pk])).status_code, 404)


class FotoNovaTestes(BaseDeAulas):
    def setUp(self):
        super().setUp()
        self.aula = self.criar_aula()
        self.url = reverse("aulas:foto_nova", args=[self.aula.pk])

    def test_adicionar_fotos_grava_e_vai_para_a_trilha(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, 'enctype="multipart/form-data"')
        resposta = self.client.post(
            self.url, {"novas_fotos": [foto_de_teste("a.jpg", com_exif=True), foto_de_teste("b.jpg")], "legenda": "Cartaz"},
            follow=True,
        )
        self.assertRedirects(resposta, reverse("aulas:detalhe", args=[self.aula.pk]) + "#fotos")
        self.assertEqual(self.aula.fotos.count(), 2)
        self.assertEqual(set(self.aula.fotos.values_list("legenda", flat=True)), {"Cartaz"})
        self.assertEqual(EventoAuditoria.objects.filter(modelo="aulas.FotoDaAula", aluno_id=self.aluno.pk).count(), 2)
        self.assertContains(resposta, "2 fotos adicionadas à aula de Lia I.")

    def test_sem_foto_pede_para_escolher(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, {"legenda": "Cartaz"})
        self.assertContains(resposta, "Escolha pelo menos uma foto para enviar.")

    def test_quem_so_ve_recebe_403(self):
        self.entrar(self.leitor)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, {"novas_fotos": [foto_de_teste()]}).status_code, 403)
        self.assertFalse(self.aula.fotos.exists())

    def test_aula_de_outro_servico_da_404(self):
        de_fora = self.criar_aula(servico=self.outro_servico, aluno=self.aluno_de_fora, professor=self.professor_de_fora)
        self.entrar(self.supervisao)
        url = reverse("aulas:foto_nova", args=[de_fora.pk])
        self.assertEqual(self.client.post(url, {"novas_fotos": [foto_de_teste()]}).status_code, 404)
        self.assertFalse(de_fora.fotos.exists())

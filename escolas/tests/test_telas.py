"""Telas do módulo escolas: quem abre, quem não abre, separação entre serviços e trilha (RF-13, RF-14, SEG-05)."""
import datetime
import re

from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from core.models import EventoAuditoria
from core.testes import criar_escola, criar_pessoa
from escolas.models import ContatoEscola, Escola

from .base import BaseEscolas

Acao = EventoAuditoria.Acao


class ListaTestes(BaseEscolas):
    url = reverse("escolas:lista")

    def test_pede_login(self):
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 302)
        self.assertIn(reverse("entrar"), resposta["Location"])

    def test_sem_servico_nao_abre(self):
        self.client.force_login(criar_pessoa(email="sem.servico@exemplo.org"))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_abre_para_apoio_e_professor(self):
        for pessoa in (self.apoio, self.professor, self.supervisao):
            self.client.force_login(pessoa)
            resposta = self.client.get(self.url)
            self.assertEqual(resposta.status_code, 200)
            self.assertContains(resposta, "Escola Municipal Inventada Alfa")
            self.assertContains(resposta, '<span class="el-data">91000001</span>', html=True)

    def test_403_para_quem_nao_ve_contatos(self):
        self.client.force_login(self.so_aulas)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_item_do_menu_so_para_quem_ve_contatos(self):
        self.client.force_login(self.professor)
        self.assertContains(self.client.get(reverse("inicio")), f'href="{self.url}"')
        self.client.force_login(self.so_aulas)
        self.assertNotContains(self.client.get(reverse("inicio")), f'href="{self.url}"')

    def test_botao_cadastrar_so_para_quem_edita(self):
        self.client.force_login(self.apoio)
        self.assertContains(self.client.get(self.url), reverse("escolas:nova"))
        self.client.force_login(self.professor)
        self.assertNotContains(self.client.get(self.url), reverse("escolas:nova"))

    def test_busca_por_nome_inep_e_municipio(self):
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url, {"q": "imaginário"})
        self.assertContains(resposta, "Colégio Estadual Imaginário")
        self.assertNotContains(resposta, "Escola Municipal Inventada Alfa")

        resposta = self.client.get(self.url, {"q": "91000001"})
        self.assertContains(resposta, "Escola Municipal Inventada Alfa")
        self.assertNotContains(resposta, "Colégio Estadual Imaginário")

        resposta = self.client.get(self.url, {"q": "9100"})  # começo do código
        self.assertContains(resposta, "Escola Municipal Inventada Alfa")
        self.assertContains(resposta, "Colégio Estadual Imaginário")
        self.assertNotContains(resposta, "Escola Rural Faz de Conta")

        resposta = self.client.get(self.url, {"q": "Vila Inventada"})
        self.assertContains(resposta, "Colégio Estadual Imaginário")
        self.assertNotContains(resposta, "Escola Rural Faz de Conta")

    def test_busca_sem_resultado_explica_o_que_fazer(self):
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url, {"q": "nenhuma escola assim"})
        self.assertContains(resposta, "Nenhuma escola encontrada")

    def test_htmx_devolve_so_os_resultados(self):
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url, {"q": "rural"}, HTTP_HX_REQUEST="true", HTTP_HX_TARGET="resultados")
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "<html")
        self.assertNotContains(resposta, "<h1")
        self.assertContains(resposta, "Escola Rural Faz de Conta")

    def test_navegacao_com_boost_devolve_a_pagina_inteira(self):
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url, HTTP_HX_REQUEST="true", HTTP_HX_BOOSTED="true", HTTP_HX_TARGET="conteudo")
        self.assertContains(resposta, "<h1", count=1)

    def test_selo_mostra_so_o_contato_deste_servico(self):
        self.contato(servico=self.outro_servico, situacao=ContatoEscola.Situacao.ATUALIZADO)
        self.contato(escola=self.escola_b, situacao=ContatoEscola.Situacao.PRECISA_ATUALIZAR)
        self.client.force_login(self.apoio)
        linhas = self._linhas(self.client.get(self.url))
        self.assertIn("Sem contato", linhas["Escola Municipal Inventada Alfa"])
        self.assertIn("Precisa atualizar", linhas["Colégio Estadual Imaginário"])

        self.client.force_login(self.apoio_outro)
        linhas = self._linhas(self.client.get(self.url))
        self.assertIn("Atualizado", linhas["Escola Municipal Inventada Alfa"])
        self.assertIn("Sem contato", linhas["Colégio Estadual Imaginário"])

    def test_filtro_escolas_com_alunos_ativos(self):
        self.aluno(escola=self.escola_b)
        self.aluno(nome="Rui Inventado Prado", escola=self.escola_c, situacao=Aluno.Situacao.ENCERRADO)
        self.aluno(nome="Ana Outra Inventada", escola=self.escola, servico=self.outro_servico)
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url, {"com_alunos": "1"})
        self.assertContains(resposta, "Colégio Estadual Imaginário")
        self.assertNotContains(resposta, "Escola Rural Faz de Conta")  # só aluno encerrado
        self.assertNotContains(resposta, "Escola Municipal Inventada Alfa")  # aluno é de outro serviço

    def test_filtro_com_alunos_some_para_quem_nao_ve_vida_escolar(self):
        self.aluno(escola=self.escola_b)
        self.client.force_login(self.so_contato)
        resposta = self.client.get(self.url, {"com_alunos": "1"})
        self.assertNotContains(resposta, 'name="com_alunos"')
        self.assertContains(resposta, "Escola Municipal Inventada Alfa")  # o filtro não vale

    def test_filtro_contato_precisa_atualizar(self):
        self.contato(situacao=ContatoEscola.Situacao.ATUALIZADO)
        self.contato(escola=self.escola_b, situacao=ContatoEscola.Situacao.PRECISA_ATUALIZAR)
        self.contato(escola=self.escola_c, servico=self.outro_servico, situacao=ContatoEscola.Situacao.ATUALIZADO)
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url, {"precisa": "1"})
        self.assertNotContains(resposta, "Escola Municipal Inventada Alfa")
        self.assertContains(resposta, "Colégio Estadual Imaginário")
        self.assertContains(resposta, "Escola Rural Faz de Conta")  # sem contato neste serviço

    def test_paginacao_de_30(self):
        for numero in range(32):
            criar_escola(f"Escola Inventada Número {numero:02d}", codigo=f"93{numero:06d}")
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url, {"q": "Número"})
        self.assertEqual(len(resposta.context["pagina"].object_list), 30)
        self.assertContains(resposta, "Página 1 de 2")
        resposta = self.client.get(self.url, {"q": "Número", "pagina": "2"})
        self.assertEqual(len(resposta.context["pagina"].object_list), 2)
        resposta = self.client.get(self.url, {"q": "Número", "pagina": "99"})
        self.assertEqual(resposta.status_code, 200)

    def test_consultas_nao_crescem_com_as_linhas(self):
        self.client.force_login(self.apoio)
        self._consultas({})  # aquece a sessão
        uma = self._consultas({"q": "Alfa"})
        for numero in range(20):
            escola = criar_escola(f"Escola Inventada Extra {numero:02d}", codigo=f"94{numero:06d}")
            if numero % 2:
                self.contato(escola=escola)
        muitas = self._consultas({"q": "Inventada"})
        self.assertEqual(uma, muitas)

    def _consultas(self, params):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as contexto:
            self.client.get(self.url, params)
        return len(contexto.captured_queries)

    @staticmethod
    def _linhas(resposta):
        """Texto de cada linha da tabela, pelo nome da escola."""
        html = resposta.content.decode()
        linhas = {}
        for linha in re.findall(r"<tr>(.*?)</tr>", html, flags=re.S):
            nome = re.search(r'<a href="[^"]+">([^<]+)</a>', linha)
            if nome:
                linhas[nome.group(1)] = re.sub(r"<[^>]+>", " ", linha)
        return linhas


class DetalheTestes(BaseEscolas):
    def url(self, escola=None):
        return reverse("escolas:detalhe", args=[(escola or self.escola).pk])

    def test_abre_para_apoio_e_professor(self):
        for pessoa in (self.apoio, self.professor):
            self.client.force_login(pessoa)
            resposta = self.client.get(self.url())
            self.assertEqual(resposta.status_code, 200)
            self.assertContains(resposta, "<h1", count=1)
            self.assertContains(resposta, "Dados públicos")
            self.assertContains(resposta, "Rua Inventada, 10")
            self.assertContains(resposta, "Contato confirmado por Serviço Alfa Inventado")

    def test_403_e_404(self):
        self.client.force_login(self.so_aulas)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.client.force_login(self.apoio)
        self.assertEqual(self.client.get(reverse("escolas:detalhe", args=[999999])).status_code, 404)

    def test_contato_de_outro_servico_nao_aparece(self):
        self.contato(servico=self.outro_servico, email="so.do.beta@exemplo.org", quem_atende="Pessoa do Beta",
                     observacoes="Anotação do serviço Beta")
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url())
        self.assertNotContains(resposta, "so.do.beta@exemplo.org")
        self.assertNotContains(resposta, "Pessoa do Beta")
        self.assertNotContains(resposta, "Anotação do serviço Beta")
        self.assertContains(resposta, "Sem contato")
        self.assertIsNone(resposta.context["contato"])

    def test_mostra_o_contato_deste_servico(self):
        self.contato(situacao=ContatoEscola.Situacao.ATUALIZADO, confirmado_em=datetime.date(2026, 9, 1),
                     confirmado_por=self.apoio, observacoes="Ligar depois das 14h")
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "secretaria.alfa@exemplo.org")
        self.assertContains(resposta, "Marta Inventada, coordenadora")
        self.assertContains(resposta, "01/09/2026, por Dora Apoio Inventada")
        self.assertContains(resposta, "Ligar depois das 14h")
        self.assertContains(resposta, 'href="tel:1130001111"')

    def test_botoes_so_para_quem_edita(self):
        self.contato()
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, reverse("escolas:confirmar_contato", args=[self.escola.pk]))
        self.assertContains(resposta, reverse("escolas:contato", args=[self.escola.pk]))
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url())
        self.assertNotContains(resposta, reverse("escolas:confirmar_contato", args=[self.escola.pk]))
        self.assertNotContains(resposta, reverse("escolas:contato", args=[self.escola.pk]))

    def test_alunos_ativos_do_servico(self):
        ativo = self.aluno(diagnostico="Diagnóstico inventado XYZ", ano_escolar="5ano")
        self.aluno(nome="Rui Inventado Prado", situacao=Aluno.Situacao.PAUSA)
        self.aluno(nome="Ana Outra Inventada", servico=self.outro_servico)
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "Lia M.")
        self.assertContains(resposta, reverse("alunos:detalhe", args=[ativo.pk]))
        self.assertContains(resposta, "5º ano")
        self.assertNotContains(resposta, "Lia Inventada Moreira")  # nome completo só no perfil
        self.assertNotContains(resposta, "Rui P.")  # em pausa
        self.assertNotContains(resposta, "Ana I.")  # outro serviço
        self.assertNotContains(resposta, "Diagnóstico inventado XYZ")

    def test_alunos_somem_para_quem_nao_ve_identificacao(self):
        self.aluno()
        self.client.force_login(self.so_contato)
        resposta = self.client.get(self.url())
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "Lia M.")
        self.assertNotContains(resposta, "Alunos ativos do serviço nesta escola")

    def test_historico_so_do_servico(self):
        contato = self.contato()
        EventoAuditoria.objects.create(servico=self.servico, usuario_nome="Dora Apoio Inventada",
                                       acao=Acao.VALIDOU, modelo="escolas.ContatoEscola", objeto_id=str(contato.pk),
                                       descricao="Confirmou o contato da escola")
        EventoAuditoria.objects.create(servico=self.outro_servico, usuario_nome="Beto Apoio Inventado",
                                       acao=Acao.CRIOU, modelo="escolas.Escola", objeto_id=str(self.escola.pk))
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "Confirmou o contato da escola")
        self.assertNotContains(resposta, "Beto Apoio Inventado")


class NovaEscolaTestes(BaseEscolas):
    url = reverse("escolas:nova")

    def dados(self, **extra):
        dados = {
            "codigo_inep": "9500 0001", "nome": "  Escola   Inventada Nova ", "rede": "municipal",
            "endereco": "Avenida Fictícia, 200", "bairro": "Centro", "municipio": "Cidade Fictícia", "uf": "SP",
            "cep": "01234567", "telefone": "11 3000 2222",
        }
        dados.update(extra)
        return dados

    def test_abre_para_quem_edita(self):
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "<h1", count=1)
        self.assertContains(resposta, "Código INEP")
        self.assertContains(resposta, '<option value="SP">São Paulo (SP)</option>', html=True)

    def test_403_para_quem_so_ve(self):
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.dados()).status_code, 403)
        self.assertFalse(Escola.objects.filter(codigo_inep="95000001").exists())

    def test_cadastra_com_fonte_do_servico_e_trilha(self):
        self.client.force_login(self.apoio)
        resposta = self.client.post(self.url, self.dados())
        escola = Escola.objects.get(codigo_inep="95000001")
        self.assertRedirects(resposta, reverse("escolas:detalhe", args=[escola.pk]))
        self.assertEqual(escola.nome, "Escola Inventada Nova")
        self.assertEqual(escola.fonte, "Cadastrada por Serviço Alfa Inventado")
        self.assertEqual(escola.cep, "01234-567")
        self.assertEqual(escola.telefone, "(11) 3000-2222")
        evento = EventoAuditoria.objects.get(modelo="escolas.Escola", objeto_id=str(escola.pk))
        self.assertEqual(evento.acao, Acao.CRIOU)
        self.assertEqual(evento.servico, self.servico)
        self.assertEqual(evento.usuario, self.apoio)
        self.assertEqual(evento.mudancas["codigo_inep"]["para"], "95000001")

    def test_codigo_inep_com_8_numeros_e_unico(self):
        self.client.force_login(self.apoio)
        resposta = self.client.post(self.url, self.dados(codigo_inep="1234567"))
        self.assertContains(resposta, "O código INEP tem 8 números")
        self.assertContains(resposta, 'aria-invalid="true"')
        resposta = self.client.post(self.url, self.dados(codigo_inep="91000001"))
        self.assertContains(resposta, "Já existe uma escola com este código INEP")
        self.assertEqual(Escola.objects.filter(codigo_inep="91000001").count(), 1)

    def test_campos_obrigatorios_e_formatos(self):
        self.client.force_login(self.apoio)
        resposta = self.client.post(self.url, self.dados(nome="", uf="", rede="", cep="123", telefone="3000"))
        form = resposta.context["form"]
        self.assertEqual(set(form.errors), {"nome", "uf", "rede", "cep", "telefone"})
        self.assertContains(resposta, "Digite o telefone com DDD")
        self.assertContains(resposta, "Escolha a UF onde fica a escola.")
        self.assertNotContains(resposta, "Este campo é obrigatório")

    def test_volta_para_a_tela_que_pediu(self):
        self.client.force_login(self.apoio)
        resposta = self.client.post(f"{self.url}?proximo=/alunos/novo/", self.dados())
        self.assertRedirects(resposta, "/alunos/novo/", fetch_redirect_response=False)
        resposta = self.client.post(f"{self.url}?proximo=https://exemplo.org/", self.dados(codigo_inep="95000002"))
        escola = Escola.objects.get(codigo_inep="95000002")
        self.assertRedirects(resposta, reverse("escolas:detalhe", args=[escola.pk]))


class ContatoTestes(BaseEscolas):
    def url(self, escola=None):
        return reverse("escolas:contato", args=[(escola or self.escola).pk])

    def dados(self, **extra):
        dados = {
            "quem_atende": "Joana Inventada, secretária", "email": "secretaria@exemplo.org",
            "telefone": "(11) 3000-3333", "observacoes": "", "situacao": "precisa_atualizar",
        }
        dados.update(extra)
        return dados

    def test_cadastrar_abre_para_quem_edita(self):
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url())
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Cadastrar contato")
        self.assertNotContains(resposta, "motivo_alteracao")

    def test_403_para_quem_so_ve_e_404_para_escola_inexistente(self):
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url(), self.dados()).status_code, 403)
        self.client.force_login(self.so_aulas)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.client.force_login(self.apoio)
        self.assertEqual(self.client.get(reverse("escolas:contato", args=[999999])).status_code, 404)
        self.assertFalse(ContatoEscola.objects.exists())

    def test_cadastrar_grava_o_servico_e_a_trilha(self):
        self.client.force_login(self.apoio)
        resposta = self.client.post(self.url(), self.dados(telefone="11 3000 3333"))
        self.assertRedirects(resposta, reverse("escolas:detalhe", args=[self.escola.pk]))
        contato = ContatoEscola.objects.get()
        self.assertEqual(contato.servico, self.servico)
        self.assertEqual(contato.criado_por, self.apoio)
        self.assertEqual(contato.telefone, "(11) 3000-3333")
        self.assertIsNone(contato.confirmado_em)
        evento = EventoAuditoria.objects.get(modelo="escolas.ContatoEscola", objeto_id=str(contato.pk))
        self.assertEqual(evento.acao, Acao.CRIOU)
        self.assertEqual(evento.servico, self.servico)
        self.assertEqual(evento.mudancas["email"]["grupo"], "escola_contato")

    def test_cadastrar_como_atualizado_confirma(self):
        self.client.force_login(self.apoio)
        self.client.post(self.url(), self.dados(situacao="atualizado"))
        contato = ContatoEscola.objects.get()
        self.assertEqual(contato.confirmado_em, timezone.localdate())
        self.assertEqual(contato.confirmado_por, self.apoio)
        acoes = set(EventoAuditoria.objects.filter(modelo="escolas.ContatoEscola").values_list("acao", flat=True))
        self.assertEqual(acoes, {Acao.CRIOU, Acao.VALIDOU})

    def test_atualizado_pede_email_ou_telefone(self):
        self.client.force_login(self.apoio)
        resposta = self.client.post(self.url(), self.dados(situacao="atualizado", email="", telefone=""))
        self.assertContains(resposta, "Para marcar o contato como atualizado, preencha o e-mail ou o telefone")
        self.assertIn("email", resposta.context["form"].errors)
        self.assertFalse(ContatoEscola.objects.exists())

    def test_cada_servico_tem_o_seu_contato(self):
        do_outro = self.contato(servico=self.outro_servico, email="beta@exemplo.org")
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "Cadastrar contato")  # o do outro serviço não existe para este
        self.assertNotContains(resposta, "beta@exemplo.org")
        self.client.post(self.url(), self.dados())
        self.assertEqual(ContatoEscola.objects.filter(escola=self.escola).count(), 2)
        do_outro.refresh_from_db()
        self.assertEqual(do_outro.email, "beta@exemplo.org")
        self.assertEqual(do_outro.versao, 1)

    def test_editar_pede_motivo_e_grava_na_trilha(self):
        contato = self.contato()
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "Editar contato")
        self.assertContains(resposta, "Por que você está alterando?")
        self.assertContains(resposta, 'name="estado_original"')
        resposta = self.client.post(self.url(), self.dados(email="nova.secretaria@exemplo.org"))
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("motivo_alteracao", resposta.context["form"].errors)
        resposta = self.client.post(self.url(), self.dados(
            email="nova.secretaria@exemplo.org", motivo_alteracao="A escola trocou o e-mail da secretaria."
        ))
        self.assertRedirects(resposta, reverse("escolas:detalhe", args=[self.escola.pk]))
        contato.refresh_from_db()
        self.assertEqual(contato.email, "nova.secretaria@exemplo.org")
        self.assertEqual(contato.versao, 2)
        evento = EventoAuditoria.objects.get(acao=Acao.ALTEROU, objeto_id=str(contato.pk))
        self.assertEqual(evento.motivo, "A escola trocou o e-mail da secretaria.")
        self.assertEqual(evento.mudancas["email"]["para"], "nova.secretaria@exemplo.org")

    def test_editar_dados_de_contato_atualizado_renova_a_confirmacao(self):
        contato = self.contato(situacao="atualizado", confirmado_em=datetime.date(2026, 1, 10),
                               confirmado_por=self.supervisao)
        self.client.force_login(self.apoio)
        self.client.post(self.url(), self.dados(
            email="outra@exemplo.org", situacao="atualizado", motivo_alteracao="Conferido por telefone.",
        ))
        contato.refresh_from_db()
        self.assertEqual(contato.confirmado_em, timezone.localdate())
        self.assertEqual(contato.confirmado_por, self.apoio)
        self.assertTrue(EventoAuditoria.objects.filter(acao=Acao.VALIDOU, objeto_id=str(contato.pk)).exists())

    def test_marcar_precisa_atualizar_guarda_a_ultima_confirmacao(self):
        contato = self.contato(situacao="atualizado", confirmado_em=datetime.date(2026, 1, 10),
                               confirmado_por=self.supervisao)
        self.client.force_login(self.apoio)
        self.client.post(self.url(), self.dados(
            email=contato.email, telefone=contato.telefone, quem_atende=contato.quem_atende,
            situacao="precisa_atualizar", motivo_alteracao="O e-mail voltou.",
        ))
        contato.refresh_from_db()
        self.assertEqual(contato.situacao, "precisa_atualizar")
        self.assertEqual(contato.confirmado_em, datetime.date(2026, 1, 10))
        self.assertFalse(EventoAuditoria.objects.filter(acao=Acao.VALIDOU).exists())

    def test_conflito_com_outra_pessoa_nao_salva(self):
        contato = self.contato()
        self.client.force_login(self.apoio)
        resposta = self.client.get(self.url())
        estado = resposta.context["estado_original"]
        ContatoEscola.objects.filter(pk=contato.pk).update(email="da.outra.pessoa@exemplo.org", versao=2)
        resposta = self.client.post(self.url(), self.dados(
            email="minha.versao@exemplo.org", estado_original=estado, motivo_alteracao="Correção."
        ))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Outra pessoa salvou este cadastro")
        contato.refresh_from_db()
        self.assertEqual(contato.email, "da.outra.pessoa@exemplo.org")

    def test_editar_403_para_quem_so_ve(self):
        contato = self.contato()
        self.client.force_login(self.professor)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url(), self.dados(motivo_alteracao="x")).status_code, 403)
        contato.refresh_from_db()
        self.assertEqual(contato.versao, 1)


class ConfirmarContatoTestes(BaseEscolas):
    def url(self, escola=None):
        return reverse("escolas:confirmar_contato", args=[(escola or self.escola).pk])

    def test_so_por_post(self):
        self.client.force_login(self.apoio)
        self.assertEqual(self.client.get(self.url()).status_code, 405)

    def test_403_para_quem_so_ve(self):
        contato = self.contato()
        self.client.force_login(self.professor)
        self.assertEqual(self.client.post(self.url()).status_code, 403)
        contato.refresh_from_db()
        self.assertEqual(contato.situacao, "precisa_atualizar")

    def test_404_para_escola_inexistente(self):
        self.client.force_login(self.apoio)
        self.assertEqual(self.client.post(reverse("escolas:confirmar_contato", args=[999999])).status_code, 404)

    def test_confirma_e_registra_validou(self):
        contato = self.contato()
        self.client.force_login(self.apoio)
        resposta = self.client.post(self.url())
        self.assertRedirects(resposta, reverse("escolas:detalhe", args=[self.escola.pk]))
        contato.refresh_from_db()
        self.assertEqual(contato.situacao, "atualizado")
        self.assertEqual(contato.confirmado_em, timezone.localdate())
        self.assertEqual(contato.confirmado_por, self.apoio)
        self.assertEqual(contato.versao, 2)
        evento = EventoAuditoria.objects.get(acao=Acao.VALIDOU)
        self.assertEqual(evento.servico, self.servico)
        self.assertEqual(evento.objeto_id, str(contato.pk))
        self.assertEqual(evento.mudancas["situacao"]["para"], "Atualizado")

    def test_sem_contato_manda_cadastrar(self):
        self.client.force_login(self.apoio)
        resposta = self.client.post(self.url())
        self.assertRedirects(resposta, reverse("escolas:contato", args=[self.escola.pk]))
        self.assertFalse(ContatoEscola.objects.exists())
        self.assertFalse(EventoAuditoria.objects.filter(acao=Acao.VALIDOU).exists())

    def test_contato_vazio_nao_se_confirma(self):
        contato = self.contato(email="", telefone="")
        self.client.force_login(self.apoio)
        self.assertRedirects(self.client.post(self.url()), reverse("escolas:contato", args=[self.escola.pk]))
        contato.refresh_from_db()
        self.assertEqual(contato.situacao, "precisa_atualizar")

    def test_nao_confirma_o_contato_de_outro_servico(self):
        contato = self.contato()
        self.client.force_login(self.apoio_outro)
        self.assertRedirects(self.client.post(self.url()), reverse("escolas:contato", args=[self.escola.pk]))
        contato.refresh_from_db()
        self.assertEqual(contato.situacao, "precisa_atualizar")
        self.assertIsNone(contato.confirmado_em)


class BuscarTestes(BaseEscolas):
    url = reverse("escolas:buscar")

    def test_exige_login_e_servico(self):
        self.assertEqual(self.client.get(self.url, {"q": "Alfa"}).status_code, 302)
        self.client.force_login(criar_pessoa(email="sem.servico.busca@exemplo.org"))
        self.assertEqual(self.client.get(self.url, {"q": "Alfa"}).status_code, 403)

    def test_qualquer_pessoa_do_servico_busca(self):
        self.client.force_login(self.so_aulas)
        resposta = self.client.get(self.url, {"q": "Alfa"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, f'<option value="{self.escola.pk}">')

    def test_busca_por_inep_devolve_opcoes_de_select(self):
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url, {"q": "91000002"})
        self.assertContains(resposta, f'<option value="{self.escola_b.pk}">')
        self.assertContains(resposta, "INEP 91000002")
        self.assertNotContains(resposta, "Escola Municipal Inventada Alfa")
        self.assertNotContains(resposta, "<html")

    def test_formato_datalist_e_campo(self):
        self.client.force_login(self.professor)
        resposta = self.client.get(self.url, {"formato": "datalist", "campo": "escola", "escola": "rural"})
        self.assertContains(resposta, 'value="92000003 · Escola Rural Faz de Conta (Cidade Fictícia/SP)"')

    def test_busca_curta_e_sem_resultado(self):
        self.client.force_login(self.professor)
        self.assertContains(self.client.get(self.url, {"q": "a"}), "Digite pelo menos 3 letras")
        self.assertContains(self.client.get(self.url, {"q": "nada parecido"}), "Nenhuma escola encontrada")

    def test_nunca_mostra_contato(self):
        self.contato(email="nao.aparece@exemplo.org")
        self.client.force_login(self.apoio)
        self.assertNotContains(self.client.get(self.url, {"q": "Alfa"}), "nao.aparece@exemplo.org")

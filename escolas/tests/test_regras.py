"""Regras do módulo escolas: pendência do contato, seção do perfil do aluno e campo de escola com busca."""
from django import forms
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from alunos.models import Aluno
from core.formularios import ModeloFormularioBase
from core.registro import pendencias_para, secoes_do_aluno
from escolas import encaixes
from escolas.consultas import com_artigo
from escolas.formularios import CampoEscola, FormularioEscola, normalizar_telefone, usar_campo_escola
from escolas.models import ContatoEscola

from .base import BaseEscolas, requisicao


def pendencias_de_contato(request, todas=False):
    return [p for p in pendencias_para(request, todas=todas) if p.tipo == "Contato da escola"]


class PendenciaDoContatoTestes(BaseEscolas):
    def test_escola_sem_contato_com_aluno_ativo_gera_pendencia_para_o_apoio(self):
        self.aluno()
        pendencias = pendencias_de_contato(requisicao(self.apoio))
        self.assertEqual(len(pendencias), 1)
        p = pendencias[0]
        self.assertEqual(p.titulo, "Confirmar o contato da Escola Municipal Inventada Alfa")
        self.assertEqual(p.url, reverse("escolas:detalhe", args=[self.escola.pk]))
        self.assertEqual(p.origem, "Aluno ativo desta escola: Lia M.")
        self.assertEqual(p.chave, f"contato-{self.escola.pk}-{self.apoio.pk}")
        self.assertIsNone(p.prazo)
        self.assertEqual(p.responsavel, "")
        self.assertEqual(p.detalhe, "O serviço ainda não tem o contato desta escola.")

    def test_contato_precisa_atualizar_tambem_gera(self):
        self.aluno()
        self.contato(situacao=ContatoEscola.Situacao.PRECISA_ATUALIZAR)
        pendencias = pendencias_de_contato(requisicao(self.apoio))
        self.assertEqual([p.detalhe for p in pendencias], ["O contato está marcado como precisa atualizar."])

    def test_pendencia_some_depois_de_confirmar(self):
        self.aluno()
        self.contato()
        self.assertEqual(len(pendencias_de_contato(requisicao(self.apoio))), 1)
        self.client.force_login(self.apoio)
        self.client.post(reverse("escolas:confirmar_contato", args=[self.escola.pk]))
        self.assertEqual(pendencias_de_contato(requisicao(self.apoio)), [])

    def test_pendencia_aparece_na_tela_inicial(self):
        self.aluno()
        self.client.force_login(self.apoio)
        resposta = self.client.get(reverse("inicio"))
        self.assertContains(resposta, "Confirmar o contato da Escola Municipal Inventada Alfa")

    def test_so_para_quem_edita_contatos(self):
        self.aluno()
        self.assertEqual(pendencias_de_contato(requisicao(self.professor)), [])
        self.assertEqual(pendencias_de_contato(requisicao(self.so_contato)), [])
        self.assertEqual(len(pendencias_de_contato(requisicao(self.supervisao))), 1)

    def test_aluno_em_pausa_ou_encerrado_nao_gera(self):
        self.aluno(situacao=Aluno.Situacao.PAUSA)
        self.aluno(nome="Rui Inventado Prado", escola=self.escola_b, situacao=Aluno.Situacao.ENCERRADO)
        self.aluno(nome="Bia Sem Escola", escola=None)
        self.assertEqual(pendencias_de_contato(requisicao(self.apoio)), [])

    def test_contato_de_outro_servico_nao_conta(self):
        self.aluno()
        self.contato(servico=self.outro_servico, situacao=ContatoEscola.Situacao.ATUALIZADO)
        self.assertEqual(len(pendencias_de_contato(requisicao(self.apoio))), 1)
        # e o aluno deste serviço não gera pendência para o outro serviço
        self.assertEqual(pendencias_de_contato(requisicao(self.apoio_outro)), [])

    def test_uma_por_escola_com_varios_alunos(self):
        self.aluno()
        self.aluno(nome="Rui Inventado Prado")
        self.aluno(nome="Ana Inventada Souza")
        self.aluno(nome="Téo Inventado Lima")
        pendencias = pendencias_de_contato(requisicao(self.apoio))
        self.assertEqual(len(pendencias), 1)
        self.assertEqual(pendencias[0].origem, "Alunos ativos desta escola: Ana S., Lia M., Rui P. e mais 1")

    def test_sem_identificacao_a_origem_so_conta_os_alunos(self):
        from core.testes import criar_papel, criar_pessoa

        so_contatos = criar_pessoa(self.servico, criar_papel(self.servico, "Contatos", editar=["escola_contato"]),
                                   email="contatos@exemplo.org")
        self.aluno()
        self.aluno(nome="Rui Inventado Prado")
        pendencias = pendencias_de_contato(requisicao(so_contatos))
        self.assertEqual([p.origem for p in pendencias], ["2 alunos ativos desta escola"])

    def test_de_todos_com_responsavel(self):
        self.aluno()
        self.aluno(nome="Rui Inventado Prado", escola=self.escola_b)
        pendencias = pendencias_de_contato(requisicao(self.supervisao), todas=True)
        self.assertEqual(len(pendencias), 2)
        self.assertEqual({p.responsavel for p in pendencias}, {"Apoio administrativo"})
        self.assertEqual({p.titulo for p in pendencias}, {
            "Confirmar o contato da Escola Municipal Inventada Alfa",
            "Confirmar o contato do Colégio Estadual Imaginário",
        })

    def test_consultas_constantes(self):
        for numero in range(6):
            self.aluno(nome=f"Aluno Inventado {numero}", escola=[self.escola, self.escola_b, self.escola_c][numero % 3])
        request = requisicao(self.apoio)
        with self.assertNumQueries(2):
            encaixes.pendencias_de_contato(request, self.apoio, False)


class SecaoDoAlunoTestes(BaseEscolas):
    def secao(self, usuario, aluno):
        request = requisicao(usuario)
        return next((s for s in secoes_do_aluno(request, aluno) if s["chave"] == "escola"), None), request

    def html(self, usuario, aluno):
        secao, request = self.secao(usuario, aluno)
        return render_to_string(secao["template"], {
            "dados": secao["contexto"], "aluno": aluno, "acesso": request.acesso, "request": request,
        })

    def test_mostra_escola_ano_turma_ra_e_contato(self):
        self.contato(situacao=ContatoEscola.Situacao.ATUALIZADO)
        aluno = self.aluno(ano_escolar="3ano", turma="B", ra="RA-000123")
        secao, _ = self.secao(self.apoio, aluno)
        self.assertEqual(secao["titulo"], "Escola de origem")
        html = self.html(self.apoio, aluno)
        self.assertIn(reverse("escolas:detalhe", args=[self.escola.pk]), html)
        self.assertIn("3º ano", html)
        self.assertIn("RA-000123", html)
        self.assertIn("secretaria.alfa@exemplo.org", html)
        self.assertIn("Atualizado", html)
        self.assertNotIn("<h2", html)

    def test_sem_matricula(self):
        aluno = self.aluno(escola=None, sem_matricula=True)
        self.assertIn("Sem matrícula", self.html(self.apoio, aluno))

    def test_contato_so_para_quem_ve_contatos(self):
        self.contato(email="escondido@exemplo.org")
        papel = self.professor.vinculos.get().papel
        papel.acessos["escola_contato"] = "nenhum"
        papel.save()
        aluno = self.aluno()
        html = self.html(self.professor, aluno)
        self.assertIn("Escola Municipal Inventada Alfa", html)
        self.assertNotIn("escondido@exemplo.org", html)
        self.assertNotIn(reverse("escolas:detalhe", args=[self.escola.pk]), html)

    def test_contato_de_outro_servico_nao_aparece(self):
        self.contato(servico=self.outro_servico, email="beta@exemplo.org")
        html = self.html(self.apoio, self.aluno())
        self.assertNotIn("beta@exemplo.org", html)
        self.assertIn("Sem contato", html)

    def test_some_para_quem_nao_ve_vida_escolar(self):
        secao, _ = self.secao(self.so_aulas, self.aluno())
        self.assertIsNone(secao)

    def test_aluno_de_outro_servico_nao_tem_secao(self):
        aluno = self.aluno(servico=self.outro_servico)
        self.assertIsNone(encaixes.secao_escola_do_aluno(requisicao(self.apoio), aluno))


class CampoEscolaTestes(BaseEscolas):
    class Formulario(forms.Form):
        escola = CampoEscola(required=False)

    def test_aceita_texto_da_sugestao_codigo_ou_numero_interno(self):
        for valor in (f"91000002 · {self.escola_b.nome} (Vila Inventada/MG)", "91000002", str(self.escola_b.pk)):
            form = self.Formulario({"escola": valor})
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["escola"], self.escola_b)

    def test_vazio_e_desconhecido(self):
        form = self.Formulario({"escola": ""})
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data["escola"])
        form = self.Formulario({"escola": "Escola que não existe"})
        self.assertFalse(form.is_valid())
        self.assertIn("Não encontramos essa escola", form.errors["escola"][0])

    def test_widget_com_datalist_e_busca(self):
        form = self.Formulario(initial={"escola": self.escola.pk})
        html = str(form["escola"])
        self.assertIn('list="id_escola_opcoes"', html)
        self.assertIn('<datalist id="id_escola_opcoes">', html)
        self.assertIn("formato=datalist", html)
        self.assertIn("campo=escola", html)
        self.assertIn('hx-target="#id_escola_opcoes"', html)
        self.assertIn('value="91000001 · Escola Municipal Inventada Alfa (Cidade Fictícia/SP)"', html)

    def test_sem_mudanca_quando_a_escola_e_a_mesma(self):
        form = self.Formulario({"escola": "91000001"}, initial={"escola": self.escola.pk})
        self.assertFalse(form.has_changed())
        form = self.Formulario({"escola": "91000002"}, initial={"escola": self.escola.pk})
        self.assertTrue(form.has_changed())

    def test_usar_campo_escola_num_formulario_de_aluno(self):
        class FormularioAluno(ModeloFormularioBase):
            class Meta:
                model = Aluno
                fields = ["nome", "escola"]

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                usar_campo_escola(self)

        aluno = self.aluno()
        form = FormularioAluno({"nome": aluno.nome, "escola": "92000003"}, instance=aluno)
        self.assertIsInstance(form.fields["escola"], CampoEscola)
        self.assertEqual(form.fields["escola"].label, "Escola de origem")
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        aluno.refresh_from_db()
        self.assertEqual(aluno.escola, self.escola_c)

        class SemEscola(ModeloFormularioBase):
            class Meta:
                model = Aluno
                fields = ["nome"]

        self.assertIsNone(usar_campo_escola(SemEscola()))


class AjudasTestes(TestCase):
    def test_artigo_do_nome(self):
        self.assertEqual(com_artigo("Escola Estadual Inventada"), "da Escola Estadual Inventada")
        self.assertEqual(com_artigo("Colégio Inventado"), "do Colégio Inventado")
        self.assertEqual(com_artigo("EMEF Inventada"), "da EMEF Inventada")
        self.assertEqual(com_artigo("Recanto Inventado"), "da escola Recanto Inventado")

    def test_telefone(self):
        self.assertEqual(normalizar_telefone("11 3000 4444"), "(11) 3000-4444")
        self.assertEqual(normalizar_telefone("011 93000-4444"), "(11) 93000-4444")
        self.assertEqual(normalizar_telefone("(11) 3000-4444 ramal 21"), "(11) 3000-4444 ramal 21")
        self.assertEqual(normalizar_telefone(""), "")
        with self.assertRaises(forms.ValidationError):
            normalizar_telefone("3000-4444")

    def test_uf_e_lista_de_opcoes(self):
        form = FormularioEscola()
        self.assertEqual(len(form.fields["uf"].choices), 28)
        self.assertEqual(form.fields["rede"].choices[0], ("", "Escolha a rede"))

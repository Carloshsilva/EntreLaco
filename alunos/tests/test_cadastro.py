"""Cadastrar aluno: só o nome é obrigatório (RF-19), campos por permissão (RF-07) e trilha (SEG-03)."""
from django.contrib.messages import get_messages
from django.urls import reverse

from alunos.models import Aluno
from core.testes import criar_papel, criar_pessoa

from .base import Acao, BaseAlunos, dias_atras, hoje


class CadastrarAlunoTestes(BaseAlunos):
    url = reverse("alunos:novo")

    def test_abre_para_quem_edita_a_identificacao(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, '<h1 class="el-display">Cadastrar aluno</h1>', html=True)
        self.assertContains(resposta, "Nome completo <span class=\"el-req\">(obrigatório)</span>", html=True)
        # Só o nome é obrigatório: nenhum outro campo leva a marca.
        self.assertContains(resposta, "(obrigatório)", count=1)

    def test_403_para_quem_nao_edita_a_identificacao(self):
        for pessoa in (self.apoio, self.so_ver, self.so_aulas):
            self.entrar(pessoa)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.post(self.url, {"nome": "Ana Inventada"}).status_code, 403)
        self.assertFalse(Aluno.objects.filter(nome="Ana Inventada").exists())

    def test_so_o_nome_basta_e_grava_a_trilha(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, {"nome": "  Ana   Inventada Costa "})
        aluno = Aluno.objects.get(nome="Ana Inventada Costa")
        self.assertRedirects(resposta, reverse("alunos:detalhe", args=[aluno.pk]), fetch_redirect_response=False)
        self.assertEqual(aluno.servico, self.servico)
        self.assertEqual(aluno.criado_por, self.professor)
        self.assertEqual(aluno.situacao, Aluno.Situacao.ATIVO)
        self.assertEqual(aluno.situacao_desde, hoje())
        self.assertEqual(aluno.visao, Aluno.Condicao.NAO_AVALIADO)
        evento = self.eventos(acao=Acao.CRIOU, modelo="alunos.Aluno", objeto_id=str(aluno.pk)).get()
        self.assertEqual(evento.aluno_id, aluno.pk)
        self.assertEqual(evento.usuario, self.professor)
        self.assertEqual(evento.mudancas["nome"]["para"], "Ana Inventada Costa")
        mensagens = [str(m) for m in get_messages(resposta.wsgi_request)]
        self.assertEqual(
            mensagens,
            ["Aluno cadastrado. Falta: data de nascimento, unidade de atendimento, ano escolar, escola de origem "
             "e um responsável."],
        )

    def test_sem_nome_nao_salva_e_explica(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, {"nome": "   ", "leito": "3"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Falta o nome do aluno")
        self.assertContains(resposta, 'aria-invalid="true"')
        self.assertFalse(Aluno.objects.filter(leito="3").exists())

    def test_secoes_por_tipo_de_dado(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        for titulo in ("Identificação do aluno", "Condições e aprendizagem", "Saúde e dados sensíveis", "Vida escolar"):
            self.assertContains(resposta, f"<legend>{titulo}</legend>", html=True)
        self.assertNotContains(resposta, 'name="situacao"')
        self.assertNotContains(resposta, 'name="situacao_desde"')

    def test_so_os_campos_que_o_papel_edita(self):
        papel = criar_papel(self.servico, "Só identificação", editar=["identificacao"])
        pessoa = criar_pessoa(self.servico, papel, email="so.identificacao@exemplo.org")
        self.entrar(pessoa)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, 'name="nome"')
        self.assertNotContains(resposta, 'name="diagnostico"')
        self.assertNotContains(resposta, 'name="visao"')
        self.assertNotContains(resposta, "Saúde e dados sensíveis")
        # Mesmo enviando, o diagnóstico não é gravado.
        self.client.post(self.url, {"nome": "Bia Inventada Reis", "diagnostico": "Não deveria salvar"})
        self.assertEqual(Aluno.objects.get(nome="Bia Inventada Reis").diagnostico, "")

    def test_escola_pela_busca_da_base_comum(self):
        self.entrar(self.professor)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, reverse("escolas:buscar"))
        self.assertContains(resposta, 'list="id_escola_opcoes"')
        self.client.post(self.url, {"nome": "Caio Inventado Prado",
                                    "escola": "93000001 · Escola Municipal Inventada Alfa (Cidade Fictícia/SP)"})
        self.assertEqual(Aluno.objects.get(nome="Caio Inventado Prado").escola, self.escola)

    def test_escola_que_nao_existe_mostra_como_resolver(self):
        self.entrar(self.professor)
        resposta = self.client.post(self.url, {"nome": "Caio Inventado Prado", "escola": "Escola que não existe"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Não encontramos essa escola")
        self.assertFalse(Aluno.objects.filter(nome="Caio Inventado Prado").exists())

    def test_datas_no_futuro_nao_valem(self):
        self.entrar(self.professor)
        amanha = dias_atras(-1).isoformat()
        resposta = self.client.post(self.url, {"nome": "Caio Inventado Prado", "data_nascimento": amanha,
                                               "data_internacao": amanha})
        self.assertContains(resposta, "A data de nascimento não pode ser depois de hoje")
        self.assertContains(resposta, "A data de internação não pode ser depois de hoje")
        self.assertFalse(Aluno.objects.filter(nome="Caio Inventado Prado").exists())

    def test_ficha_completa_nao_lista_faltas_que_o_papel_nao_ve(self):
        papel = criar_papel(self.servico, "Identificação sem escola", editar=["identificacao"])
        pessoa = criar_pessoa(self.servico, papel, email="sem.escola@exemplo.org")
        self.entrar(pessoa)
        resposta = self.client.post(self.url, {"nome": "Rui Inventado Paz", "data_nascimento": "2018-03-04",
                                               "unidade": "Pediatria Fictícia"})
        mensagens = [str(m) for m in get_messages(resposta.wsgi_request)]
        self.assertEqual(mensagens, ["Aluno cadastrado. A ficha ainda está incompleta."])

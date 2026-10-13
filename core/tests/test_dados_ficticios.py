"""Testes do comando carregar_dados_ficticios: só dado inventado, sem duplicar, e telas abrindo com ele."""
import datetime
import hashlib
import re
import shutil
import tempfile
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from alunos.models import Aluno, MudancaDeSituacao, Responsavel
from aulas.models import Aula, FotoDaAula
from autorizacoes.models import Autorizacao, Termo
from core.management.commands.carregar_dados_ficticios import (
    DESCRICAO_DA_CARGA,
    DIAGNOSTICO,
    NOME_DO_SERVICO,
    TEXTO_PROVISORIO,
)
from core.models import EventoAuditoria, Papel, Servico, Vinculo
from documentos.models import Documento
from equipe.models import ComponenteCurricular, PerfilProfessor
from escolas.models import ContatoEscola, Escola
from reunioes.models import CitacaoDeAluno, Reuniao

SENHA = "senha-de-teste-ficticia-1"
PALAVRAS_DE_MENTIRA = ("Fictíci", "Inventad", "Exemplo", "Teste", "Faz-de-Conta", "Exemplar", "Imaginária")


def carregar(**opcoes):
    saida = StringIO()
    call_command("carregar_dados_ficticios", stdout=saida, **opcoes)
    return saida.getvalue()


class PastaPrivadaTemporaria:
    """Os arquivos gerados vão para uma pasta temporária, apagada no fim da classe."""

    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp(prefix="entrelaco-ficticios-")
        cls.addClassCleanup(shutil.rmtree, cls.pasta, ignore_errors=True)
        configuracao = override_settings(MEDIA_ROOT=cls.pasta)
        configuracao.enable()
        cls.addClassCleanup(configuracao.disable)
        super().setUpClass()


def contagens(servico):
    return {
        modelo.__name__: modelo.objects.filter(servico=servico).count()
        for modelo in (Aluno, Responsavel, Autorizacao, Aula, FotoDaAula, Reuniao, CitacaoDeAluno, Documento,
                       ContatoEscola, ComponenteCurricular, Termo, PerfilProfessor, Papel, Vinculo)
    }


class CargaTestes(PastaPrivadaTemporaria, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.saida = carregar(senha=SENHA)
        cls.servico = Servico.objects.get(nome=NOME_DO_SERVICO)
        cls.pessoas = get_user_model().objects.filter(vinculos__servico=cls.servico)

    def pessoa(self, papel):
        """A primeira pessoa do papel, pelo nome (para o professor, a Ana)."""
        return self.pessoas.filter(vinculos__papel__nome=papel).order_by("nome").first()

    def test_cria_o_servico_com_papeis_componentes_e_termos(self):
        self.assertEqual(
            set(Papel.objects.filter(servico=self.servico).values_list("nome", flat=True)),
            {"Supervisão", "Coordenação", "Orientação pedagógica", "Professor", "Apoio administrativo"},
        )
        supervisao = Papel.objects.get(servico=self.servico, nome="Supervisão")
        self.assertTrue(supervisao.pode_configurar)
        self.assertEqual(
            set(supervisao.acoes), {"gerir_equipe", "mudar_situacao", "ver_trilha", "ver_tarefas_de_todos"}
        )
        self.assertEqual(set(supervisao.acessos.values()), {"editar"})
        coordenacao = Papel.objects.get(servico=self.servico, nome="Coordenação")
        self.assertEqual(set(coordenacao.acoes), {"mudar_situacao", "ver_trilha", "ver_tarefas_de_todos"})
        orientacao = Papel.objects.get(servico=self.servico, nome="Orientação pedagógica")
        self.assertEqual(set(orientacao.acoes), {"mudar_situacao", "ver_tarefas_de_todos"})
        professor = Papel.objects.get(servico=self.servico, nome="Professor")
        self.assertEqual(professor.acessos["atas"], "ver")
        self.assertEqual(professor.acessos["escola_contato"], "ver")
        self.assertEqual(professor.acessos["sensivel"], "editar")
        apoio = Papel.objects.get(servico=self.servico, nome="Apoio administrativo")
        for tipo in ("sensivel", "aprendizagem", "aulas", "atas"):
            self.assertEqual(apoio.acessos[tipo], "nenhum", tipo)
        for tipo in ("identificacao", "familia", "autorizacoes"):
            self.assertEqual(apoio.acessos[tipo], "ver", tipo)
        for tipo in ("escolar", "documentos", "escola_contato"):
            self.assertEqual(apoio.acessos[tipo], "editar", tipo)

        self.assertEqual(ComponenteCurricular.objects.filter(servico=self.servico).count(), 8)
        termos = Termo.objects.filter(servico=self.servico, vigente=True)
        self.assertEqual(termos.count(), 2)
        for termo in termos:
            self.assertTrue(termo.texto.startswith(TEXTO_PROVISORIO))

    def test_contagens(self):
        numeros = contagens(self.servico)
        self.assertEqual(numeros["Aluno"], 15)
        self.assertEqual(numeros["Vinculo"], 9)
        self.assertEqual(numeros["PerfilProfessor"], 5)
        self.assertEqual(numeros["Documento"], 2)
        self.assertEqual(Reuniao.objects.filter(servico=self.servico).exclude(ata="").count(), 2)
        self.assertGreaterEqual(numeros["CitacaoDeAluno"], 4)
        self.assertGreaterEqual(numeros["FotoDaAula"], 6)
        self.assertGreaterEqual(numeros["Responsavel"], 14)
        self.assertEqual(Escola.objects.filter(codigo_inep__startswith="99").count(), 15)
        self.assertIn(f'Serviço "{NOME_DO_SERVICO}" criado', self.saida)

    def test_pessoas_por_papel_e_perfis_de_professor(self):
        por_papel = {}
        for vinculo in Vinculo.objects.filter(servico=self.servico).select_related("papel"):
            por_papel[vinculo.papel.nome] = por_papel.get(vinculo.papel.nome, 0) + 1
        self.assertEqual(por_papel, {
            "Supervisão": 1, "Coordenação": 1, "Orientação pedagógica": 1, "Professor": 5, "Apoio administrativo": 1,
        })
        for perfil in PerfilProfessor.objects.filter(servico=self.servico).prefetch_related("componentes"):
            self.assertTrue(perfil.componentes.exists(), perfil)
            self.assertTrue(perfil.etapas, perfil)

    def test_so_dado_inventado(self):
        for pessoa in self.pessoas:
            self.assertTrue(pessoa.email.endswith("@exemplo.org"), pessoa.email)
            self.assertTrue(any(palavra in pessoa.nome for palavra in PALAVRAS_DE_MENTIRA), pessoa.nome)
        emails = []
        for modelo in (Responsavel, ContatoEscola):
            emails += modelo.objects.filter(servico=self.servico).exclude(email="").values_list("email", flat=True)
        self.assertTrue(emails)
        for email in emails:
            self.assertTrue(email.endswith("@exemplo.org"), email)
        for aluno in Aluno.objects.filter(servico=self.servico):
            self.assertTrue(any(palavra in aluno.nome for palavra in PALAVRAS_DE_MENTIRA), aluno.nome)
            self.assertEqual(aluno.diagnostico, DIAGNOSTICO)
        for escola in Escola.objects.filter(codigo_inep__startswith="99"):
            self.assertTrue("Fictíci" in escola.nome or "Inventad" in escola.nome, escola.nome)
            self.assertEqual(escola.uf, "SP")

    def test_alunos_em_situacoes_variadas(self):
        alunos = Aluno.objects.filter(servico=self.servico)
        self.assertEqual(alunos.filter(situacao=Aluno.Situacao.PAUSA).count(), 1)
        self.assertGreaterEqual(alunos.filter(situacao=Aluno.Situacao.ATIVO).count(), 12)
        encerrado = alunos.get(situacao=Aluno.Situacao.ENCERRADO)
        self.assertTrue(encerrado.tmo)
        saida = MudancaDeSituacao.objects.get(aluno=encerrado)
        self.assertTrue(saida.pede_professor_domiciliar)
        self.assertEqual(alunos.filter(sem_matricula=True, escola__isnull=True).count(), 1)
        self.assertGreaterEqual(alunos.filter(risco_evasao=True).count(), 1)
        incompletas = [aluno for aluno in alunos.filter(situacao=Aluno.Situacao.ATIVO) if not aluno.ficha_completa]
        self.assertGreaterEqual(len(incompletas), 2)

    def test_autorizacoes_em_todas_as_situacoes_com_prova(self):
        autorizacoes = Autorizacao.objects.filter(servico=self.servico)
        self.assertEqual(set(autorizacoes.values_list("situacao", flat=True)), set(Autorizacao.Situacao.values))
        for autorizacao in autorizacoes.exclude(situacao=Autorizacao.Situacao.PENDENTE):
            self.assertTrue(autorizacao.impressao_digital, autorizacao)
            if autorizacao.forma == Autorizacao.Forma.TABLET:
                self.assertTrue(default_storage.exists(autorizacao.assinatura.name))
            else:
                with autorizacao.arquivo.open("rb") as arquivo:
                    self.assertEqual(hashlib.sha256(arquivo.read()).hexdigest(), autorizacao.impressao_digital)

    def test_prova_do_tablet_confere(self):
        from autorizacoes.regras import conferir_impressao_digital

        tablet = Autorizacao.objects.filter(
            servico=self.servico, forma=Autorizacao.Forma.TABLET, situacao=Autorizacao.Situacao.VALIDA
        )
        self.assertTrue(tablet.exists())
        for autorizacao in tablet:
            self.assertIs(conferir_impressao_digital(autorizacao), True, autorizacao)

    def test_aulas_nas_ultimas_quatro_semanas_e_nas_proximas_duas(self):
        hoje = timezone.localdate()
        aulas = Aula.objects.filter(servico=self.servico)
        self.assertFalse(aulas.filter(data__lt=hoje - datetime.timedelta(weeks=4)).exists())
        self.assertFalse(aulas.filter(data__gt=hoje + datetime.timedelta(weeks=2)).exists())
        self.assertFalse(aulas.filter(data__week_day__in=[1, 7]).exists())  # domingo e sábado
        self.assertTrue(aulas.filter(situacao=Aula.Situacao.REGISTRADA, data__lt=hoje).exists())
        self.assertTrue(aulas.filter(situacao=Aula.Situacao.MARCADA, data__gt=hoje).exists())
        # Marcadas no passado e sem registro: viram pendência do professor.
        self.assertGreaterEqual(aulas.filter(situacao=Aula.Situacao.MARCADA, data__lt=hoje).count(), 3)
        for aula in aulas.filter(situacao=Aula.Situacao.REGISTRADA)[:20]:
            self.assertTrue(aula.conteudo)
            self.assertTrue(aula.componentes.exists())
        for foto in FotoDaAula.objects.filter(servico=self.servico):
            self.assertTrue(default_storage.exists(foto.arquivo.name))

    def test_reunioes_com_citacao_de_saude_e_documentos(self):
        self.assertTrue(CitacaoDeAluno.objects.filter(servico=self.servico, grupo_de_dado="sensivel").exists())
        for documento in Documento.objects.filter(servico=self.servico):
            with documento.arquivo.open("rb") as arquivo:
                dados = arquivo.read()
            self.assertEqual(len(dados), documento.tamanho)
            self.assertEqual(hashlib.sha256(dados).hexdigest(), documento.impressao_digital)

    def test_trilha_marca_a_carga(self):
        eventos = EventoAuditoria.objects.filter(servico=self.servico)
        self.assertTrue(eventos.exists())
        self.assertFalse(eventos.exclude(descricao__startswith=DESCRICAO_DA_CARGA).exists())
        for aluno in Aluno.objects.filter(servico=self.servico):
            self.assertTrue(eventos.filter(acao="criou", aluno_id=aluno.pk, modelo="alunos.Aluno").exists())
        self.assertTrue(eventos.filter(acao="mudou_situacao").exists())
        self.assertTrue(eventos.filter(acao="liberou_permissao").exists())
        # A citação de saúde fica com o tipo de dado dela na trilha.
        saude = CitacaoDeAluno.objects.get(servico=self.servico, grupo_de_dado="sensivel")
        evento = eventos.get(modelo="reunioes.CitacaoDeAluno", objeto_id=str(saude.pk))
        self.assertEqual(evento.grupo, "atas+sensivel")
        self.assertEqual({m["grupo"] for m in evento.mudancas.values()}, {"sensivel"})

    def test_senha_dada_vale_para_todos_e_duas_etapas_fica_para_o_primeiro_login(self):
        for pessoa in self.pessoas:
            self.assertTrue(pessoa.check_password(SENHA), pessoa.email)
        self.assertNotIn(SENHA, self.saida)
        supervisao = self.pessoa("Supervisão")
        self.assertFalse(supervisao.totp_ativo)
        self.assertTrue(self.client.login(email=supervisao.email, password=SENHA))
        self.assertRedirects(self.client.get(reverse("inicio")), reverse("duas_etapas"))

    def test_rodar_de_novo_sem_recriar_nao_duplica(self):
        antes = contagens(self.servico)
        eventos = EventoAuditoria.objects.count()
        saida = carregar(senha=SENHA)
        self.assertIn("já existe", saida)
        self.assertEqual(Servico.objects.filter(nome=NOME_DO_SERVICO).count(), 1)
        self.assertEqual(contagens(self.servico), antes)
        self.assertEqual(Escola.objects.filter(codigo_inep__startswith="99").count(), 15)
        self.assertEqual(EventoAuditoria.objects.count(), eventos)

    # ------------------------------------------------------------ telas com os dados

    def test_telas_do_professor(self):
        professor = self.pessoa("Professor")
        self.client.force_login(professor)
        resposta = self.client.get(reverse("inicio"))
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["pendencias"])
        self.assertEqual(self.client.get(reverse("agenda")).status_code, 200)
        resposta = self.client.get(reverse("agenda"), {"pessoa": "todos"})
        self.assertEqual(resposta.status_code, 200)
        self.assertGreater(resposta.context["total"], 0)

    def test_telas_do_apoio_sem_dado_de_saude(self):
        apoio = self.pessoa("Apoio administrativo")
        self.client.force_login(apoio)
        resposta = self.client.get(reverse("inicio"))
        self.assertEqual(resposta.status_code, 200)
        tipos = {pendencia.tipo for pendencia in resposta.context["pendencias"]}
        self.assertIn("Contato da escola", tipos)
        self.assertNotIn("Aula sem registro", tipos)
        self.assertNotContains(resposta, DIAGNOSTICO)
        resposta = self.client.get(reverse("agenda"), {"pessoa": "todos"})
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, DIAGNOSTICO)

    def test_perfil_do_aluno_respeita_o_papel(self):
        try:
            reverse("alunos:detalhe", args=[1])
        except NoReverseMatch:
            self.skipTest("A tela do perfil do aluno ainda não existe.")
        aluno = Aluno.objects.get(servico=self.servico, tmo=True, situacao=Aluno.Situacao.ATIVO)
        url = reverse("alunos:detalhe", args=[aluno.pk])
        self.client.force_login(self.pessoa("Professor"))
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, DIAGNOSTICO)
        self.client.force_login(self.pessoa("Apoio administrativo"))
        resposta = self.client.get(url)
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, aluno.nome)
        self.assertNotContains(resposta, DIAGNOSTICO)
        self.assertNotContains(resposta, "Dado de saúde fictício")
        self.assertNotContains(resposta, "Observação de saúde fictícia")


class RecriarTestes(PastaPrivadaTemporaria, TestCase):
    def test_recriar_apaga_so_o_servico_de_teste_e_cria_de_novo(self):
        carregar(senha=SENHA)
        servico = Servico.objects.get(nome=NOME_DO_SERVICO)
        outro = Servico.objects.create(nome="Outro serviço inventado", slug="outro-servico-inventado")
        antes = contagens(servico)
        alunos_antigos = set(Aluno.objects.filter(servico=servico).values_list("pk", flat=True))
        foto_antiga = FotoDaAula.objects.filter(servico=servico).first().arquivo.name
        eventos_antigos = EventoAuditoria.objects.filter(servico=servico).count()

        with self.captureOnCommitCallbacks(execute=True):
            saida = carregar(senha=SENHA, recriar=True)

        self.assertIn("recriado", saida)
        self.assertEqual(Servico.objects.get(nome=NOME_DO_SERVICO).pk, servico.pk)
        self.assertTrue(Servico.objects.filter(pk=outro.pk).exists())
        self.assertEqual(contagens(servico), antes)
        self.assertFalse(Aluno.objects.filter(pk__in=alunos_antigos).exists())
        self.assertFalse(default_storage.exists(foto_antiga))
        self.assertEqual(get_user_model().objects.filter(email__endswith="@exemplo.org").count(), 9)
        # A trilha antiga fica, com a exclusão registrada.
        self.assertGreater(EventoAuditoria.objects.filter(servico=servico).count(), eventos_antigos)
        self.assertTrue(EventoAuditoria.objects.filter(servico=servico, acao="excluiu").exists())


class SenhasAleatoriasTestes(PastaPrivadaTemporaria, TestCase):
    def test_sem_senha_cada_pessoa_recebe_uma_e_a_tabela_aparece_uma_vez(self):
        saida = carregar()
        pessoas = get_user_model().objects.filter(vinculos__servico__nome=NOME_DO_SERVICO)
        self.assertEqual(pessoas.count(), 9)
        senhas = {}
        for pessoa in pessoas:
            linha = re.search(rf"^\s+{re.escape(pessoa.email)}\s+.+?\s+(\S+)$", saida, re.MULTILINE)
            self.assertIsNotNone(linha, pessoa.email)
            senhas[pessoa.email] = linha.group(1)
            self.assertGreaterEqual(len(senhas[pessoa.email]), 16)
            self.assertTrue(pessoa.check_password(senhas[pessoa.email]), pessoa.email)
        self.assertEqual(len(set(senhas.values())), 9)
        self.assertIn("não aparecem de novo", saida)
        # Rodar de novo não mostra as senhas outra vez.
        segunda = carregar()
        for senha in senhas.values():
            self.assertNotIn(senha, segunda)


@override_settings(AMBIENTE_DE_TESTE=False)
class ForaDoAmbienteDeTesteTestes(TestCase):
    def test_recusa_rodar(self):
        with self.assertRaisesMessage(CommandError, "só roda no ambiente de teste"):
            carregar(senha=SENHA)
        self.assertFalse(Servico.objects.filter(nome=NOME_DO_SERVICO).exists())


class SenhaFracaTestes(TestCase):
    def test_recusa_senha_fraca(self):
        with self.assertRaisesMessage(CommandError, "não serve"):
            carregar(senha="123")
        self.assertFalse(Servico.objects.filter(nome=NOME_DO_SERVICO).exists())

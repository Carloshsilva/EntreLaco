"""Pendências do módulo alunos: ficha incompleta (RF-19), matrícula (RF-20), revisão de ativo (RF-21)
e professor domiciliar (RF-24)."""
import datetime

from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from alunos.pendencias import pendencias_de_alunos
from core.testes import criar_aluno

from .base import BaseAlunos, Situacao, dias_atras, hoje, requisicao


def por_tipo(pendencias, tipo):
    return [p for p in pendencias if p.tipo == tipo]


class BasePendencias(BaseAlunos):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # A aluna da base tem a ficha completa e uma aula recente: não gera pendência.
        cls.servico.prazo_revisao_ativo_dias = 21
        cls.servico.save()

    def setUp(self):
        self.aula(self.aluno, dias_atras(1))

    def pendencias(self, usuario, todas=False, quem_ve=None):
        return pendencias_de_alunos(requisicao(quem_ve or usuario), usuario, todas)

    def aluno_antigo(self, nome, dias=40, **extra):
        """Aluno cadastrado há `dias` dias."""
        extra.setdefault("criado_por", self.professor)
        aluno = criar_aluno(self.servico, nome=nome, **extra)
        Aluno.objects.filter(pk=aluno.pk).update(criado_em=timezone.now() - datetime.timedelta(days=dias))
        aluno.refresh_from_db()
        return aluno


class FichaIncompletaTestes(BasePendencias):
    def test_para_quem_cadastrou_quando_ainda_nao_teve_aula(self):
        aluno = criar_aluno(self.servico, nome="Gil Inventado Rocha", criado_por=self.professor_b)
        pendencias = por_tipo(self.pendencias(self.professor_b), "Ficha incompleta")
        self.assertEqual(len(pendencias), 1)
        pendencia = pendencias[0]
        self.assertEqual(pendencia.titulo, "Completar a ficha de Gil R.")
        self.assertEqual(pendencia.url, reverse("alunos:editar", args=[aluno.pk]))
        self.assertEqual(pendencia.detalhe, "Falta: data de nascimento, unidade de atendimento, ano escolar, "
                                            "escola de origem e um responsável.")
        self.assertEqual(pendencia.origem, f"Cadastro de {hoje():%d/%m}")
        self.assertEqual(pendencia.prazo, hoje() + datetime.timedelta(days=3))
        self.assertEqual(pendencia.chave, f"ficha-{aluno.pk}-{self.professor_b.pk}")
        self.assertEqual(pendencia.aluno, "Gil R.")
        self.assertEqual(por_tipo(self.pendencias(self.professor), "Ficha incompleta"), [])

    def test_para_o_professor_da_primeira_aula_registrada(self):
        aluno = criar_aluno(self.servico, nome="Gil Inventado Rocha", criado_por=self.supervisao)
        self.aula(aluno, dias_atras(5), professor=self.professor, situacao="marcada")
        self.aula(aluno, dias_atras(4), professor=self.professor_b)
        self.aula(aluno, dias_atras(2), professor=self.professor)
        pendencia = por_tipo(self.pendencias(self.professor_b), "Ficha incompleta")[0]
        self.assertEqual(pendencia.origem, f"Aula de {dias_atras(4):%d/%m} registrada antes do cadastro completo")
        self.assertEqual(pendencia.prazo, dias_atras(1))
        self.assertEqual(pendencia.situacao_do_prazo, "vencida")
        self.assertEqual(por_tipo(self.pendencias(self.supervisao), "Ficha incompleta"), [])
        self.assertEqual(por_tipo(self.pendencias(self.professor), "Ficha incompleta"), [])

    def test_ficha_completa_ou_aluno_encerrado_nao_geram(self):
        criar_aluno(self.servico, nome="Gil Inventado Rocha", criado_por=self.professor, situacao=Situacao.ENCERRADO)
        self.assertEqual(por_tipo(self.pendencias(self.professor), "Ficha incompleta"), [])

    def test_aluno_em_pausa_tambem_gera(self):
        criar_aluno(self.servico, nome="Gil Inventado Rocha", criado_por=self.professor, situacao=Situacao.PAUSA)
        self.assertEqual(len(por_tipo(self.pendencias(self.professor), "Ficha incompleta")), 1)

    def test_aparece_na_tela_inicial(self):
        criar_aluno(self.servico, nome="Gil Inventado Rocha", criado_por=self.professor)
        self.entrar(self.professor)
        resposta = self.client.get(reverse("inicio"))
        self.assertContains(resposta, "Completar a ficha de Gil R.")
        self.assertContains(resposta, "Ficha incompleta")


class RevisaoDeAtivoTestes(BasePendencias):
    def test_nasce_com_tres_semanas_e_um_dia_sem_aula(self):
        aluno = self.aluno_antigo("Hugo Inventado Reis")
        self.aula(aluno, dias_atras(22))
        pendencias = por_tipo(self.pendencias(self.orientacao), "Revisão de ativo")
        self.assertEqual([p.titulo for p in pendencias], ["Revisar a situação de Hugo R."])
        pendencia = pendencias[0]
        self.assertEqual(pendencia.url, reverse("alunos:situacao", args=[aluno.pk]))
        self.assertEqual(pendencia.prazo, dias_atras(1))
        self.assertEqual(pendencia.origem, f"Última aula em {dias_atras(22):%d/%m/%Y}")
        self.assertEqual(pendencia.chave, f"revisao-{aluno.pk}-{self.orientacao.pk}")

    def test_nao_nasce_com_tres_semanas_exatas(self):
        aluno = self.aluno_antigo("Hugo Inventado Reis")
        self.aula(aluno, dias_atras(21))
        self.assertEqual(por_tipo(self.pendencias(self.orientacao), "Revisão de ativo"), [])

    def test_muda_com_o_prazo_do_servico(self):
        aluno = self.aluno_antigo("Hugo Inventado Reis")
        self.aula(aluno, dias_atras(22))
        self.servico.prazo_revisao_ativo_dias = 28
        self.servico.save()
        self.assertEqual(por_tipo(self.pendencias(self.orientacao), "Revisão de ativo"), [])
        Aluno.objects.filter(pk=aluno.pk).update(criado_em=timezone.now() - datetime.timedelta(days=60))
        aluno.aulas.update(data=dias_atras(29))
        pendencias = por_tipo(self.pendencias(self.orientacao), "Revisão de ativo")
        self.assertEqual(len(pendencias), 1)
        self.assertEqual(pendencias[0].prazo, dias_atras(1))

    def test_conta_aula_marcada_mudanca_e_cadastro(self):
        self.aluno_antigo("Ivo Sem Aula", dias=22)
        com_marcada = self.aluno_antigo("Jade Com Marcada")
        self.aula(com_marcada, dias_atras(30))
        self.aula(com_marcada, hoje() + datetime.timedelta(days=2), situacao="marcada")
        revisto = self.aluno_antigo("Leo Revisto")
        self.mudanca(revisto, "ativo", "ativo", data=dias_atras(5))
        recem_cadastrado = self.aluno_antigo("Mia Recente", dias=3)
        titulos = [p.titulo for p in por_tipo(self.pendencias(self.orientacao), "Revisão de ativo")]
        self.assertEqual(titulos, ["Revisar a situação de Ivo A."])
        self.assertNotIn(com_marcada.nome_curto, " ".join(titulos))
        self.assertTrue(revisto.pk and recem_cadastrado.pk)

    def test_aula_que_nao_aconteceu_nao_conta(self):
        aluno = self.aluno_antigo("Hugo Inventado Reis")
        self.aula(aluno, dias_atras(3), situacao="nao_realizada")
        self.assertEqual(len(por_tipo(self.pendencias(self.orientacao), "Revisão de ativo")), 1)

    def test_continua_ativo_reinicia_a_contagem(self):
        aluno = self.aluno_antigo("Hugo Inventado Reis")
        self.assertEqual(len(por_tipo(self.pendencias(self.orientacao), "Revisão de ativo")), 1)
        self.entrar(self.orientacao)
        self.client.post(reverse("alunos:situacao", args=[aluno.pk]), {
            "para": "ativo", "motivo": "Aula marcada para segunda.", "data": hoje().isoformat(),
            "situacao_vista": "ativo",
        })
        self.assertEqual(por_tipo(self.pendencias(self.orientacao), "Revisão de ativo"), [])

    def test_so_para_quem_muda_situacao(self):
        self.aluno_antigo("Hugo Inventado Reis")
        self.assertEqual(por_tipo(self.pendencias(self.professor), "Revisão de ativo"), [])
        self.assertEqual(len(por_tipo(self.pendencias(self.supervisao), "Revisão de ativo")), 1)

    def test_aluno_em_pausa_nao_entra_em_revisao(self):
        self.aluno_antigo("Hugo Inventado Reis", situacao=Situacao.PAUSA)
        self.assertEqual(por_tipo(self.pendencias(self.orientacao), "Revisão de ativo"), [])


class MatriculaTestes(BasePendencias):
    def test_aluno_sem_matricula_para_quem_muda_situacao(self):
        aluno = criar_aluno(self.servico, nome="Nara Inventada Lins", sem_matricula=True)
        pendencias = por_tipo(self.pendencias(self.orientacao), "Matrícula")
        self.assertEqual([p.titulo for p in pendencias], ["Acompanhar a matrícula de Nara L."])
        self.assertEqual(pendencias[0].chave, f"matricula-{aluno.pk}-{self.orientacao.pk}")
        self.assertEqual(por_tipo(self.pendencias(self.professor), "Matrícula"), [])

    def test_aluno_com_matricula_ou_encerrado_nao_gera(self):
        criar_aluno(self.servico, nome="Nara Inventada Lins", sem_matricula=True, situacao=Situacao.ENCERRADO)
        self.assertEqual(por_tipo(self.pendencias(self.orientacao), "Matrícula"), [])


class ProfessorDomiciliarPendenciaTestes(BasePendencias):
    def saida(self, aluno, motivo_saida="Alta", responsavel=None):
        Aluno.objects.filter(pk=aluno.pk).update(situacao=Situacao.ENCERRADO)
        return self.mudanca(aluno, "ativo", "encerrado", motivo_saida=motivo_saida,
                            responsavel=responsavel or self.professor_b)

    def test_nasce_na_alta_do_tmo_para_o_responsavel_pela_saida(self):
        aluno = criar_aluno(self.servico, nome="Otávio Inventado Paz", tmo=True)
        saida = self.saida(aluno)
        pendencias = por_tipo(self.pendencias(self.professor_b), "Professor domiciliar")
        self.assertEqual([p.titulo for p in pendencias], ["Ver se Otávio P. precisa de professor domiciliar"])
        self.assertEqual(pendencias[0].url, reverse("alunos:detalhe", args=[aluno.pk]) + "#secao-situacao")
        self.assertEqual(pendencias[0].chave, f"domiciliar-{saida.pk}")
        self.assertEqual(por_tipo(self.pendencias(self.professor), "Professor domiciliar"), [])

    def test_nao_nasce_sem_tmo_sem_alta_ou_ja_verificado(self):
        sem_tmo = criar_aluno(self.servico, nome="Pia Sem Tmo")
        self.saida(sem_tmo)
        obito = criar_aluno(self.servico, nome="Quim Outro Motivo", tmo=True)
        self.saida(obito, motivo_saida="Transferência")
        verificado = criar_aluno(self.servico, nome="Rui Verificado", tmo=True)
        saida = self.saida(verificado)
        saida.domiciliar_verificado_em = hoje()
        saida.save()
        self.assertEqual(por_tipo(self.pendencias(self.professor_b), "Professor domiciliar"), [])

    def test_aluno_que_voltou_a_ativo_nao_gera(self):
        aluno = criar_aluno(self.servico, nome="Otávio Inventado Paz", tmo=True)
        self.saida(aluno)
        Aluno.objects.filter(pk=aluno.pk).update(situacao=Situacao.ATIVO)
        self.assertEqual(por_tipo(self.pendencias(self.professor_b), "Professor domiciliar"), [])

    def test_encerrar_pela_tela_cria_a_pendencia(self):
        aluno = criar_aluno(self.servico, nome="Otávio Inventado Paz", tmo=True)
        self.entrar(self.orientacao)
        resposta = self.client.post(reverse("alunos:situacao", args=[aluno.pk]), {
            "para": "encerrado", "motivo": "Alta do transplante.", "motivo_saida": "Alta",
            "responsavel": str(self.professor_b.pk), "data": hoje().isoformat(), "situacao_vista": "ativo",
        }, follow=True)
        self.assertContains(resposta, "a pendência ficou com Bruno I.")
        self.assertEqual(len(por_tipo(self.pendencias(self.professor_b), "Professor domiciliar")), 1)


class TodasAsPendenciasTestes(BasePendencias):
    def test_com_todas_vem_o_responsavel(self):
        criar_aluno(self.servico, nome="Gil Inventado Rocha", criado_por=self.professor_b)
        self.aluno_antigo("Hugo Inventado Reis", criado_por=None, ano_escolar="1ano", unidade="Pediatria",
                          data_nascimento=dias_atras(3000), sem_matricula=True)
        pendencias = self.pendencias(self.supervisao, todas=True)
        ficha = [p for p in por_tipo(pendencias, "Ficha incompleta") if p.aluno == "Gil R."][0]
        self.assertEqual(ficha.responsavel, "Bruno I.")
        revisoes = por_tipo(pendencias, "Revisão de ativo")
        # Uma para cada pessoa que muda situação: orientação e supervisão.
        self.assertEqual(sorted(p.responsavel for p in revisoes), ["Olga I.", "Sueli I."])
        sem_dono = [p for p in por_tipo(pendencias, "Ficha incompleta") if p.aluno == "Hugo R."][0]
        self.assertEqual(sem_dono.responsavel, "Sem responsável")
        self.assertTrue(all(p.responsavel for p in pendencias))

    def test_tela_inicial_de_todos(self):
        criar_aluno(self.servico, nome="Gil Inventado Rocha", criado_por=self.professor_b)
        self.entrar(self.supervisao)
        resposta = self.client.get(reverse("inicio"), {"ver": "todas"})
        self.assertContains(resposta, "Completar a ficha de Gil R.")
        self.assertContains(resposta, "Com Bruno I.")

    def test_quem_nao_ve_a_identificacao_nao_recebe(self):
        criar_aluno(self.servico, nome="Gil Inventado Rocha", criado_por=self.so_aulas)
        self.assertEqual(self.pendencias(self.so_aulas), [])

    def test_matricula_some_para_quem_nao_ve_a_vida_escolar(self):
        criar_aluno(self.servico, nome="Nara Inventada Lins", sem_matricula=True)
        papel = self.so_ver.vinculos.get().papel
        papel.acoes = ["mudar_situacao"]
        papel.save()
        self.assertEqual(por_tipo(self.pendencias(self.so_ver), "Matrícula"), [])

    def test_detalhe_da_ficha_nao_mostra_o_que_a_pessoa_nao_ve(self):
        criar_aluno(self.servico, nome="Gil Inventado Rocha", criado_por=self.so_ver, data_nascimento=dias_atras(3000),
                    unidade="Pediatria")
        pendencia = por_tipo(self.pendencias(self.so_ver), "Ficha incompleta")[0]
        self.assertEqual(pendencia.detalhe, "Falta completar dados da ficha.")

    def test_outro_servico_nao_aparece(self):
        criar_aluno(self.outro_servico, nome="Tito De Fora", sem_matricula=True, criado_por=self.de_fora)
        pendencias = self.pendencias(self.supervisao, todas=True)
        self.assertFalse([p for p in pendencias if "Tito" in p.titulo])

    def test_consultas_nao_crescem_com_o_numero_de_alunos(self):
        for numero in range(3):
            aluno = self.aluno_antigo(f"Aluno Inventado {numero}", sem_matricula=True)
            self.aula(aluno, dias_atras(30), professor=self.professor_b)
        request = requisicao(self.supervisao)
        poucas = self.contar_consultas(lambda: pendencias_de_alunos(request, self.supervisao, True))
        for numero in range(3, 15):
            aluno = self.aluno_antigo(f"Aluno Inventado {numero}", sem_matricula=True, tmo=True)
            self.aula(aluno, dias_atras(30), professor=self.professor_b)
            Aluno.objects.filter(pk=aluno.pk).update(situacao=Situacao.ENCERRADO)
            self.mudanca(aluno, "ativo", "encerrado", motivo_saida="Alta", responsavel=self.professor)
        muitas = self.contar_consultas(lambda: pendencias_de_alunos(request, self.supervisao, True))
        self.assertEqual(poucas, muitas)

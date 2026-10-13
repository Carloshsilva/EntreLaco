"""Quem configura o serviço: papéis e permissões, parâmetros do serviço e componentes curriculares."""
from django.urls import reverse

from core.models import EventoAuditoria, Papel, Servico
from core.permissoes import CODIGOS_DE_GRUPO, EDITAR, NENHUM, VER, Acesso
from core.testes import criar_pessoa
from equipe.edicao import assinar_estado
from equipe.formularios import ConfiguracaoForm
from equipe.models import ComponenteCurricular

from .base import EquipeTestCase

Acao = EventoAuditoria.Acao


def dados_do_papel(nome="Estagiário", acessos=None, acoes=(), **extra):
    dados = {"nome": nome, "descricao": "Papel inventado para teste"}
    for grupo in CODIGOS_DE_GRUPO:
        dados[f"acesso_{grupo}"] = (acessos or {}).get(grupo, NENHUM)
    dados["acoes"] = list(acoes)
    dados.update(extra)
    return dados


class PermissaoDasTelasDeConfiguracaoTestes(EquipeTestCase):
    TELAS = ["equipe:configuracao", "equipe:papeis", "equipe:papel_novo", "equipe:componentes", "equipe:componente_novo"]

    def test_abrem_para_quem_configura(self):
        self.entrar(self.supervisao)
        for nome in self.TELAS:
            with self.subTest(tela=nome):
                resposta = self.client.get(reverse(nome))
                self.assertEqual(resposta.status_code, 200)
                self.assertContains(resposta, "<h1", count=1)

    def test_403_para_quem_nao_configura(self):
        for pessoa in [self.coordenacao, self.professor, self.apoio]:
            self.entrar(pessoa)
            for nome in self.TELAS:
                with self.subTest(pessoa=pessoa.nome, tela=nome):
                    self.assertEqual(self.client.get(reverse(nome)).status_code, 403)
            papel = self.papel_professor
            self.assertEqual(self.client.get(reverse("equipe:papel_editar", args=[papel.pk])).status_code, 403)


class PapeisTestes(EquipeTestCase):
    def test_lista_mostra_os_papeis_do_servico(self):
        self.entrar(self.supervisao)
        resposta = self.client.get(reverse("equipe:papeis"))
        self.assertContains(resposta, "Coordenação de equipe")
        self.assertContains(resposta, "Apoio administrativo")
        papel_de_fora = self.de_fora.vinculos.get().papel
        self.assertNotContains(resposta, reverse("equipe:papel_editar", args=[papel_de_fora.pk]))

    def test_grade_acessivel(self):
        self.entrar(self.supervisao)
        resposta = self.client.get(reverse("equipe:papel_novo"))
        self.assertContains(resposta, "<legend", count=len(CODIGOS_DE_GRUPO) + 1)
        self.assertContains(resposta, "Saúde e dados sensíveis")
        self.assertContains(resposta, "Vê e edita")
        self.assertContains(resposta, "Só o administrador da plataforma libera")
        self.assertNotContains(resposta, 'name="pode_configurar"')

    def test_papel_novo_nunca_configura(self):
        self.entrar(self.supervisao)
        dados = dados_do_papel(
            acessos={"identificacao": VER, "aulas": EDITAR}, acoes=["ver_trilha"], pode_configurar="on"
        )
        resposta = self.client.post(reverse("equipe:papel_novo"), dados)
        self.assertRedirects(resposta, reverse("equipe:papeis"))
        papel = Papel.objects.get(servico=self.servico, nome="Estagiário")
        self.assertFalse(papel.pode_configurar)
        self.assertEqual(papel.acessos["aulas"], EDITAR)
        self.assertEqual(papel.acessos["sensivel"], NENHUM)
        self.assertEqual(papel.acoes, ["ver_trilha"])
        acesso = Acesso.do_papel(papel)
        self.assertTrue(acesso.pode_editar("aulas"))
        self.assertFalse(acesso.pode_ver("sensivel"))
        self.assertFalse(acesso.configurar)
        self.assertTrue(self.eventos(acao=Acao.CRIOU, modelo="core.Papel", objeto_id=str(papel.pk)).exists())
        liberou = self.eventos(acao=Acao.LIBEROU_PERMISSAO, modelo="core.Papel", objeto_id=str(papel.pk)).get()
        self.assertEqual(liberou.mudancas["acesso_aulas"]["para"], "Vê e edita")
        self.assertEqual(liberou.servico, self.servico)

    def test_editar_registra_antes_e_depois_e_nao_mexe_em_configurar(self):
        self.entrar(self.supervisao)
        papel = self.papel_professor
        url = reverse("equipe:papel_editar", args=[papel.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        acessos = dict(papel.acessos)
        acessos["sensivel"] = NENHUM
        dados = dados_do_papel("Professor", acessos=acessos, pode_configurar="on",
                               motivo_alteracao="Professor não precisa do diagnóstico")
        resposta = self.client.post(url, dados)
        self.assertRedirects(resposta, reverse("equipe:papeis"))
        papel.refresh_from_db()
        self.assertEqual(papel.acessos["sensivel"], NENHUM)
        self.assertFalse(papel.pode_configurar)
        evento = self.eventos(acao=Acao.LIBEROU_PERMISSAO, modelo="core.Papel", objeto_id=str(papel.pk)).get()
        self.assertEqual(evento.mudancas["acesso_sensivel"], {
            "rotulo": "Saúde e dados sensíveis", "grupo": None, "de": "Vê e edita", "para": "Não vê",
        })
        self.assertEqual(evento.motivo, "Professor não precisa do diagnóstico")
        self.assertContains(self.client.get(url), "Professor não precisa do diagnóstico")

    def test_papel_que_configura_continua_configurando(self):
        self.entrar(self.supervisao)
        papel = self.papel_supervisao
        dados = dados_do_papel("Supervisão", acessos=papel.acessos, acoes=papel.acoes,
                               motivo_alteracao="Ajuste do nome", descricao="Coordena o serviço")
        self.client.post(reverse("equipe:papel_editar", args=[papel.pk]), dados)
        papel.refresh_from_db()
        self.assertTrue(papel.pode_configurar)
        self.assertEqual(papel.descricao, "Coordena o serviço")
        self.assertTrue(self.eventos(acao=Acao.ALTEROU, modelo="core.Papel").exists())
        self.assertFalse(self.eventos(acao=Acao.LIBEROU_PERMISSAO).exists())

    def test_editar_pede_motivo(self):
        self.entrar(self.supervisao)
        papel = self.papel_professor
        resposta = self.client.post(reverse("equipe:papel_editar", args=[papel.pk]), dados_do_papel("Professor"))
        self.assertContains(resposta, "Por que você está alterando?")
        papel.refresh_from_db()
        self.assertEqual(papel.acessos["aulas"], EDITAR)

    def test_nome_repetido(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(reverse("equipe:papel_novo"), dados_do_papel("professor"))
        self.assertContains(resposta, "Já existe um papel com esse nome")

    def test_falta_escolher_um_acesso(self):
        self.entrar(self.supervisao)
        dados = dados_do_papel()
        del dados["acesso_sensivel"]
        resposta = self.client.post(reverse("equipe:papel_novo"), dados)
        self.assertContains(resposta, "Falta escolher o acesso a “Saúde e dados sensíveis”")

    def test_papel_de_outro_servico_da_404(self):
        self.entrar(self.supervisao)
        papel_de_fora = self.de_fora.vinculos.get().papel
        self.assertEqual(self.client.get(reverse("equipe:papel_editar", args=[papel_de_fora.pk])).status_code, 404)

    def test_conflito_ao_editar_papel(self):
        self.entrar(self.supervisao)
        papel = self.papel_professor
        from equipe.formularios import PapelForm

        estado = assinar_estado(PapelForm.valores_salvos(papel))
        acessos = dict(papel.acessos)
        acessos["sensivel"] = VER
        Papel.objects.filter(pk=papel.pk).update(acessos=acessos)
        enviado = dict(papel.acessos)
        enviado["sensivel"] = NENHUM
        resposta = self.client.post(reverse("equipe:papel_editar", args=[papel.pk]), dados_do_papel(
            "Professor", acessos=enviado, motivo_alteracao="Teste", estado_original=estado,
        ))
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "Outra pessoa salvou este cadastro")
        papel.refresh_from_db()
        self.assertEqual(papel.acessos["sensivel"], VER)


class ConfiguracaoDoServicoTestes(EquipeTestCase):
    def dados(self, **extra):
        dados = {
            "minutos_por_aula": "45",
            "bncc_ativa": "on",
            "prazo_revisao_ativo_dias": "14",
            "motivos_saida": "Alta\n\n  Volta à escola  \nalta\nTransferência",
            "motivo_alteracao": "Combinado na reunião de equipe",
        }
        dados.update(extra)
        return dados

    def test_tela_tem_atalhos(self):
        self.entrar(self.supervisao)
        resposta = self.client.get(reverse("equipe:configuracao"))
        self.assertContains(resposta, reverse("equipe:papeis"))
        self.assertContains(resposta, reverse("equipe:componentes"))
        self.assertContains(resposta, "Minutos de atendimento que contam 1 aula")

    def test_salvar_grava_e_registra_antes_e_depois(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(reverse("equipe:configuracao"), self.dados())
        self.assertRedirects(resposta, reverse("equipe:configuracao"))
        servico = Servico.objects.get(pk=self.servico.pk)
        self.assertEqual(servico.minutos_por_aula, 45)
        self.assertTrue(servico.bncc_ativa)
        self.assertEqual(servico.prazo_revisao_ativo_dias, 14)
        self.assertEqual(servico.motivos_saida, ["Alta", "Volta à escola", "Transferência"])
        evento = self.eventos(acao=Acao.ALTEROU, modelo="core.Servico", objeto_id=str(servico.pk)).get()
        self.assertEqual(evento.servico, self.servico)
        self.assertEqual(evento.mudancas["minutos_por_aula"]["de"], "30")
        self.assertEqual(evento.mudancas["minutos_por_aula"]["para"], "45")
        self.assertEqual(evento.motivo, "Combinado na reunião de equipe")
        self.assertContains(self.client.get(reverse("equipe:configuracao")), "Combinado na reunião de equipe")

    def test_ao_menos_um_motivo_de_saida(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(reverse("equipe:configuracao"), self.dados(motivos_saida="  \n \n"))
        self.assertContains(resposta, "Escreva ao menos um motivo de saída")
        self.assertEqual(Servico.objects.get(pk=self.servico.pk).minutos_por_aula, 30)

    def test_numeros_fora_do_limite(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(
            reverse("equipe:configuracao"), self.dados(minutos_por_aula="1", prazo_revisao_ativo_dias="0")
        )
        self.assertContains(resposta, "Use pelo menos 5 minutos")
        self.assertContains(resposta, "Use pelo menos 1 dia")

    def test_sem_mudanca_nao_grava_trilha(self):
        self.entrar(self.supervisao)
        servico = self.servico
        self.client.post(reverse("equipe:configuracao"), {
            "minutos_por_aula": servico.minutos_por_aula, "prazo_revisao_ativo_dias": servico.prazo_revisao_ativo_dias,
            "motivos_saida": "\n".join(servico.motivos_saida), "motivo_alteracao": "Nada",
        })
        self.assertFalse(self.eventos(modelo="core.Servico").exists())

    def test_campo_que_so_a_outra_pessoa_mudou_e_mantido(self):
        self.entrar(self.supervisao)
        estado = assinar_estado(ConfiguracaoForm.valores_salvos(self.servico))
        Servico.objects.filter(pk=self.servico.pk).update(prazo_revisao_ativo_dias=30)
        self.client.post(reverse("equipe:configuracao"), self.dados(
            prazo_revisao_ativo_dias="21", estado_original=estado,
        ))
        servico = Servico.objects.get(pk=self.servico.pk)
        self.assertEqual(servico.prazo_revisao_ativo_dias, 30)
        self.assertEqual(servico.minutos_por_aula, 45)

    def test_outro_servico_nao_muda(self):
        self.entrar(self.supervisao)
        self.client.post(reverse("equipe:configuracao"), self.dados())
        self.assertEqual(Servico.objects.get(pk=self.outro_servico.pk).minutos_por_aula, 30)


class ComponentesTestes(EquipeTestCase):
    def test_criar_editar_e_trilha(self):
        self.entrar(self.supervisao)
        resposta = self.client.post(reverse("equipe:componente_novo"), {"nome": "  Matemática ", "ativo": "on"})
        self.assertRedirects(resposta, reverse("equipe:componentes"))
        componente = ComponenteCurricular.objects.get(servico=self.servico)
        self.assertEqual(componente.nome, "Matemática")
        self.assertEqual(componente.criado_por, self.supervisao)
        self.assertTrue(self.eventos(acao=Acao.CRIOU, modelo="equipe.ComponenteCurricular").exists())
        self.assertContains(self.client.get(reverse("equipe:componentes")), "Matemática")

        url = reverse("equipe:componente_editar", args=[componente.pk])
        self.assertContains(self.client.get(url), "Por que você está alterando?")
        resposta = self.client.post(url, {"nome": "Matemática", "motivo_alteracao": "Não é mais oferecido"})
        self.assertRedirects(resposta, reverse("equipe:componentes"))
        componente.refresh_from_db()
        self.assertFalse(componente.ativo)
        evento = self.eventos(acao=Acao.ALTEROU, modelo="equipe.ComponenteCurricular").get()
        self.assertEqual(evento.motivo, "Não é mais oferecido")
        self.assertContains(self.client.get(reverse("equipe:componentes")), "Inativo")

    def test_nome_repetido_no_servico(self):
        ComponenteCurricular.objects.create(servico=self.servico, nome="Arte")
        ComponenteCurricular.objects.create(servico=self.outro_servico, nome="Ciências")
        self.entrar(self.supervisao)
        resposta = self.client.post(reverse("equipe:componente_novo"), {"nome": "arte", "ativo": "on"})
        self.assertContains(resposta, "Já existe um componente com esse nome")
        resposta = self.client.post(reverse("equipe:componente_novo"), {"nome": "Ciências", "ativo": "on"})
        self.assertRedirects(resposta, reverse("equipe:componentes"))

    def test_componente_de_outro_servico(self):
        de_fora = ComponenteCurricular.objects.create(servico=self.outro_servico, nome="Geografia Fictícia")
        self.entrar(self.supervisao)
        self.assertNotContains(self.client.get(reverse("equipe:componentes")), "Geografia Fictícia")
        self.assertEqual(self.client.get(reverse("equipe:componente_editar", args=[de_fora.pk])).status_code, 404)

    def test_quem_so_cuida_da_equipe_nao_edita_componente(self):
        componente = ComponenteCurricular.objects.create(servico=self.servico, nome="Arte")
        self.entrar(self.coordenacao)
        self.assertEqual(self.client.get(reverse("equipe:componente_editar", args=[componente.pk])).status_code, 403)
        papel = Papel.objects.create(servico=self.servico, nome="Sem nada")
        sem_nada = criar_pessoa(self.servico, papel)
        self.entrar(sem_nada)
        self.assertEqual(self.client.get(reverse("equipe:componentes")).status_code, 403)

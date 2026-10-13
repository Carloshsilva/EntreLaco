"""Dados inventados comuns aos testes do módulo escolas."""
from django.test import RequestFactory, TestCase

from core.permissoes import Acesso
from core.testes import (
    criar_aluno,
    criar_apoio,
    criar_escola,
    criar_papel,
    criar_pessoa,
    criar_professor,
    criar_servico,
    criar_supervisao,
)
from escolas.models import ContatoEscola


PADRAO = object()


def requisicao(usuario, caminho="/"):
    """Requisição com serviço e acesso, como o ServicoMiddleware deixaria."""
    request = RequestFactory().get(caminho)
    request.user = usuario
    vinculo = usuario.vinculos.select_related("servico", "papel").get()
    request.servico = vinculo.servico
    request.vinculo = vinculo
    request.acesso = Acesso.do_papel(vinculo.papel)
    return request


class BaseEscolas(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.servico = criar_servico("Serviço Alfa Inventado")
        cls.outro_servico = criar_servico("Serviço Beta Inventado")
        cls.apoio = criar_apoio(cls.servico, nome="Dora Apoio Inventada", email="dora.apoio@exemplo.org")
        cls.professor = criar_professor(cls.servico, nome="Caio Professor Inventado", email="caio.prof@exemplo.org")
        cls.supervisao = criar_supervisao(cls.servico, nome="Sara Supervisão Inventada", email="sara.sup@exemplo.org")
        cls.so_aulas = criar_pessoa(
            cls.servico, criar_papel(cls.servico, "Só aulas", editar=["aulas"]), email="so.aulas@exemplo.org"
        )
        cls.so_contato = criar_pessoa(
            cls.servico, criar_papel(cls.servico, "Só contatos", ver=["escola_contato"]), email="so.contato@exemplo.org"
        )
        cls.apoio_outro = criar_apoio(cls.outro_servico, nome="Beto Apoio Inventado", email="beto.apoio@exemplo.org")

        cls.escola = criar_escola(
            "Escola Municipal Inventada Alfa", codigo="91000001", municipio="Cidade Fictícia", uf="SP",
            rede="municipal", telefone="(11) 3000-0001", endereco="Rua Inventada, 10",
        )
        cls.escola_b = criar_escola("Colégio Estadual Imaginário", codigo="91000002", municipio="Vila Inventada",
                                    uf="MG", rede="estadual")
        cls.escola_c = criar_escola("Escola Rural Faz de Conta", codigo="92000003", municipio="Cidade Fictícia",
                                    uf="SP", rede="municipal")

    def contato(self, escola=None, servico=None, **extra):
        extra.setdefault("email", "secretaria.alfa@exemplo.org")
        extra.setdefault("telefone", "(11) 3000-1111")
        extra.setdefault("quem_atende", "Marta Inventada, coordenadora")
        return ContatoEscola.objects.create(servico=servico or self.servico, escola=escola or self.escola, **extra)

    def aluno(self, nome="Lia Inventada Moreira", escola=PADRAO, servico=None, **extra):
        """Aluno inventado; por padrão, ativo e da escola Alfa. `escola=None` para aluno sem escola."""
        return criar_aluno(servico or self.servico, nome=nome, escola=self.escola if escola is PADRAO else escola,
                           **extra)

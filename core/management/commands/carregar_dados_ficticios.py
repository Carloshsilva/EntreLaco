"""Carrega o serviço "Escola Móvel (teste)" com dados inventados, para a equipe testar a plataforma.

Pedido do Carlos: nada de dado real, nada. Nomes, e-mails (sempre @exemplo.org), telefones, escolas
(código INEP começando por 99), diagnósticos e arquivos são todos de mentira; fotos, papéis assinados,
assinaturas e documentos são imagens geradas na hora com o Pillow.

Uso:
    python manage.py carregar_dados_ficticios                   cria o serviço de teste, se ainda não existe
    python manage.py carregar_dados_ficticios --recriar         apaga os dados do serviço de teste e cria de novo
    python manage.py carregar_dados_ficticios --senha "..."     a mesma senha (forte) para todas as pessoas

Sem --senha, cada pessoa recebe uma senha aleatória forte, mostrada uma única vez no fim.
O comando só roda com o ambiente de teste ligado (ENTRELACO_AMBIENTE_DE_TESTE, settings.AMBIENTE_DE_TESTE).
Tudo entra na trilha de auditoria com a descrição "Carga de dados fictícios".
"""
import datetime
import hashlib
import io
import math
import random
import secrets
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import FileField, ProtectedError, RestrictedError
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from alunos.models import Aluno, MudancaDeSituacao, Responsavel
from aulas.models import Aula, FotoDaAula
from autorizacoes.models import Autorizacao, Termo, Tipo
from autorizacoes.regras import DECISAO_AUTORIZO, impressao_digital_do_tablet
from core import auditoria
from core.models import ModeloDoServico, Papel, Servico, Vinculo, motivos_de_saida_padrao
from core.permissoes import ACOES, CODIGOS_DE_GRUPO, EDITAR, NENHUM, NIVEIS, NOMES_DE_GRUPO, VER
from documentos.models import Documento
from equipe.models import ComponenteCurricular, PerfilProfessor
from escolas.models import ContatoEscola, Escola
from reunioes.models import CitacaoDeAluno, Reuniao

Acao = auditoria.Acao

NOME_DO_SERVICO = "Escola Móvel (teste)"
SLUG_DO_SERVICO = "escola-movel-teste"
DESCRICAO_DA_CARGA = "Carga de dados fictícios"
DOMINIO_DOS_EMAILS = "@exemplo.org"
# A mesma sequência a cada carga: os dados mudam só com a data de hoje.
SEMENTE = 20261012
UM_DIA = datetime.timedelta(days=1)
SEMANAS_PARA_TRAS = 4
SEMANAS_PARA_FRENTE = 2

TEXTO_PROVISORIO = (
    "TEXTO PROVISÓRIO DE TESTE. O texto definitivo será escrito ou revisado pelo advogado (LGPD-02)."
)
DIAGNOSTICO = "Diagnóstico fictício de teste"
TRATAMENTO = "Tratamento fictício de teste"
FONTE_DAS_ESCOLAS = "Base fictícia de teste"

# ---------------------------------------------------------------- papéis e pessoas


@dataclass(frozen=True)
class PapelFicticio:
    chave: str
    nome: str
    descricao: str
    editar: tuple = ()
    ver: tuple = ()
    acoes: tuple = ()
    configurar: bool = False


TODOS_OS_TIPOS = tuple(CODIGOS_DE_GRUPO)
TODAS_AS_ACOES = tuple(codigo for codigo, _ in ACOES)

PAPEIS = (
    PapelFicticio(
        "supervisao", "Supervisão", "Configura o serviço, cuida da equipe e acompanha tudo.",
        editar=TODOS_OS_TIPOS, acoes=TODAS_AS_ACOES, configurar=True,
    ),
    PapelFicticio(
        "coordenacao", "Coordenação", "Acompanha alunos, aulas e reuniões e muda a situação dos alunos.",
        editar=TODOS_OS_TIPOS, acoes=("mudar_situacao", "ver_trilha", "ver_tarefas_de_todos"),
    ),
    PapelFicticio(
        "orientacao", "Orientação pedagógica", "Acompanha a vida escolar, a matrícula e as saídas dos alunos.",
        editar=TODOS_OS_TIPOS, acoes=("mudar_situacao", "ver_tarefas_de_todos"),
    ),
    PapelFicticio(
        "professor", "Professor", "Cadastra alunos, colhe as autorizações da família e registra aulas.",
        editar=("identificacao", "aprendizagem", "sensivel", "familia", "escolar", "autorizacoes", "aulas",
                "documentos"),
        ver=("atas", "escola_contato"),
    ),
    PapelFicticio(
        "apoio", "Apoio administrativo", "Cuida da vida escolar, dos documentos e dos contatos das escolas.",
        editar=("escolar", "documentos", "escola_contato"), ver=("identificacao", "familia", "autorizacoes"),
    ),
)


@dataclass(frozen=True)
class PessoaFicticia:
    chave: str
    nome: str
    email: str
    papel: str
    componentes: tuple = ()
    etapas: tuple = ()  # campos booleanos do perfil do professor


PESSOAS = (
    PessoaFicticia("helena", "Helena Maria Exemplo", "helena.exemplo@exemplo.org", "supervisao"),
    PessoaFicticia("marcos", "Marcos Antônio Fictício", "marcos.ficticio@exemplo.org", "coordenacao"),
    PessoaFicticia("rita", "Rita de Cássia Imaginária", "rita.imaginaria@exemplo.org", "orientacao"),
    PessoaFicticia(
        "ana", "Ana Paula Teste", "ana.teste@exemplo.org", "professor",
        ("Língua Portuguesa", "Alfabetização"), ("educacao_infantil", "anos_iniciais"),
    ),
    PessoaFicticia(
        "bruno", "Bruno Inventado", "bruno.inventado@exemplo.org", "professor",
        ("Matemática", "Ciências"), ("anos_iniciais", "anos_finais"),
    ),
    PessoaFicticia(
        "carla", "Carla Faz-de-Conta", "carla.fazdeconta@exemplo.org", "professor",
        ("História", "Geografia"), ("anos_finais", "ensino_medio"),
    ),
    PessoaFicticia(
        "diego", "Diego Exemplar", "diego.exemplar@exemplo.org", "professor",
        ("Arte",), ("educacao_infantil", "anos_iniciais", "anos_finais"),
    ),
    PessoaFicticia(
        "elisa", "Elisa Fictícia", "elisa.ficticia@exemplo.org", "professor",
        ("Inglês", "Língua Portuguesa"), ("anos_finais", "ensino_medio", "eja"),
    ),
    PessoaFicticia("fabio", "Fábio Exemplo Teste", "fabio.teste@exemplo.org", "apoio"),
)
PESSOAS_POR_CHAVE = {pessoa.chave: pessoa for pessoa in PESSOAS}

COMPONENTES = (
    "Língua Portuguesa", "Matemática", "Ciências", "História", "Geografia", "Arte", "Inglês", "Alfabetização",
)

TERMOS = {
    Tipo.USO_DADOS: (
        "Autorização de uso dos dados",
        "Este termo existe só para a equipe testar a plataforma com dados inventados. Ele não vale como "
        "autorização de verdade e não deve ser mostrado a nenhuma família.\n\n"
        "Na versão definitiva, aqui vai a explicação de quais dados o serviço guarda, para quê, por quanto "
        "tempo e como a família pede para ver, corrigir ou apagar esses dados.",
    ),
    Tipo.CONTATO_ESCOLA: (
        "Autorização de contato com a escola",
        "Este termo existe só para a equipe testar a plataforma com dados inventados. Ele não vale como "
        "autorização de verdade e não deve ser mostrado a nenhuma família.\n\n"
        "Na versão definitiva, aqui vai a explicação do que o serviço conta à escola de origem sobre as "
        "aulas no hospital e de como a família revoga esta autorização a qualquer momento.",
    ),
}

# ---------------------------------------------------------------- escolas (base comum, todas inventadas)

# (código INEP começando por 99, nome inventado, rede, município real de SP, DDD)
ESCOLAS = (
    ("99000001", "EMEF Fictícia Jardim das Gaivotas", "municipal", "São Paulo", "11"),
    ("99000002", "EE Fictícia Professora Aurora Lunar", "estadual", "São Paulo", "11"),
    ("99000003", "EMEF Inventada Vale dos Vagalumes", "municipal", "Guarulhos", "11"),
    ("99000004", "EE Inventada Monte das Pipas", "estadual", "Campinas", "19"),
    ("99000005", "Escola Municipal Fictícia Rio das Pedrinhas", "municipal", "Santo André", "11"),
    ("99000006", "EE Fictícia Ponte do Arco-Íris", "estadual", "São Bernardo do Campo", "11"),
    ("99000007", "EMEI Inventada Pomar Encantado", "municipal", "Osasco", "11"),
    ("99000008", "EE Fictícia Colina dos Cata-Ventos", "estadual", "Sorocaba", "15"),
    ("99000009", "Colégio Inventado Estrela-Guia", "privada", "Ribeirão Preto", "16"),
    ("99000010", "EMEB Fictícia Bosque dos Sabiás", "municipal", "Jundiaí", "11"),
    ("99000011", "EE Inventada Lago Sereno", "estadual", "Barretos", "17"),
    ("99000012", "EM Fictícia Farol do Mar Azul", "municipal", "Santos", "13"),
    ("99000013", "EE Fictícia Serra das Nuvens", "estadual", "Mogi das Cruzes", "11"),
    ("99000014", "EMEF Inventada Ciranda Alegre", "municipal", "Diadema", "11"),
    ("99000015", "EE Inventada Quintal das Letras", "estadual", "Botucatu", "14"),
)
ESCOLAS_PARALISADAS = {"99000011"}

# Contato que o serviço confirmou: (situação, dias desde a confirmação). Escola fora desta lista não tem contato.
CONTATOS = {
    "99000001": (ContatoEscola.Situacao.ATUALIZADO, 12),
    "99000002": (ContatoEscola.Situacao.ATUALIZADO, 30),
    "99000003": (ContatoEscola.Situacao.PRECISA_ATUALIZAR, None),
    "99000004": (ContatoEscola.Situacao.ATUALIZADO, 5),
    "99000007": (ContatoEscola.Situacao.ATUALIZADO, 20),
    "99000008": (ContatoEscola.Situacao.PRECISA_ATUALIZAR, None),
    "99000009": (ContatoEscola.Situacao.ATUALIZADO, 45),
    "99000012": (ContatoEscola.Situacao.ATUALIZADO, 8),
}

# ---------------------------------------------------------------- alunos (todos inventados)

ANDAR_3 = "Internação pediátrica – 3º andar"
ANDAR_4 = "Internação pediátrica – 4º andar"
HOSPITAL_DIA = "Hospital-dia"
CASA_DE_APOIO = "Casa de apoio"
AMBULATORIO = "Ambulatório"

# Cada aluno: dados da ficha, quem cadastrou, há quantos dias, as aulas da semana (dia da semana, professor),
# os responsáveis, a situação e as autorizações. Uma autorização é uma lista de coletas, da mais antiga para
# a mais recente: (forma, há quantos dias, quem colheu[, há quantos dias foi revogada]).
ALUNOS = (
    {
        "chave": "lia", "nome": "Lia Inventada Girassol", "idade": 8, "mes": 3, "ano_escolar": "3ano",
        "escola": "99000001", "unidade": ANDAR_3, "leito": "301A", "internacao": 40, "cadastro": 35,
        "criado_por": "ana", "aulas": ((0, "ana"), (2, "diego")),
        "visao": "com_alteracao", "alfabetizacao": "em_alfabetizacao",
        "condicoes": "Usa óculos para ler (dado fictício).", "raca_cor": "parda",
        "responsaveis": (("Joana Inventada Girassol", "mae", "joana.girassol@exemplo.org"),),
        "autorizacoes": {
            Tipo.USO_DADOS: (("valida_papel", 34, "ana"),),
            Tipo.CONTATO_ESCOLA: (("valida_tablet", 34, "ana"),),
        },
    },
    {
        "chave": "davi", "nome": "Davi Fictício Cometa", "idade": 11, "mes": 7, "ano_escolar": "6ano",
        "escola": "99000002", "unidade": ANDAR_4, "leito": "412B", "internacao": 60, "cadastro": 35,
        "criado_por": "bruno", "aulas": ((1, "bruno"), (3, "elisa")), "tmo": True, "raca_cor": "branca",
        "saude": "Observação de saúde fictícia: prefere atividades curtas.",
        "responsaveis": (
            ("Pedro Fictício Cometa", "pai", "pedro.cometa@exemplo.org"),
            ("Clara Inventada Cometa", "mae", "clara.cometa@exemplo.org"),
        ),
        "autorizacoes": {
            Tipo.USO_DADOS: (("pendente_tablet", 30, "bruno"), ("valida_tablet", 28, "bruno")),
            Tipo.CONTATO_ESCOLA: (("provisoria", 3, "bruno"),),
        },
    },
    {
        # Ficha incompleta: sem data de nascimento e sem ano escolar.
        "chave": "nina", "nome": "Nina Exemplo Vagalume", "idade": None, "ano_escolar": "",
        "escola": "99000003", "unidade": HOSPITAL_DIA, "cadastro": 10, "criado_por": "ana",
        "aulas": ((1, "ana"), (4, "ana")), "alfabetizacao": "nao_avaliado",
        "responsaveis": (("Sônia Inventada Vagalume", "avo", "sonia.vagalume@exemplo.org"),),
        "autorizacoes": {
            Tipo.USO_DADOS: (("pendente", 9, "ana"),),
            Tipo.CONTATO_ESCOLA: (("pendente", 2, "ana"),),
        },
    },
    {
        "chave": "theo", "nome": "Theo Teste Pipoca", "idade": 14, "mes": 11, "ano_escolar": "9ano",
        "escola": "99000004", "unidade": CASA_DE_APOIO, "internacao": 90, "cadastro": 35, "criado_por": "carla",
        "aulas": ((0, "carla"), (3, "bruno")), "raca_cor": "preta",
        "risco": "Faltou a várias aulas seguidas (dado fictício).", "reprovacao": "ja_reprovou",
        "condicoes": "Reprovou uma vez no 7º ano (dado fictício).",
        "responsaveis": (("Marta Fictícia Pipoca", "mae", "marta.pipoca@exemplo.org"),),
        "autorizacoes": {
            Tipo.USO_DADOS: (("valida_papel", 33, "carla"),),
            Tipo.CONTATO_ESCOLA: (("recusada", 33, "carla"),),
        },
    },
    {
        # Sem matrícula em escola: a orientação acompanha até a matrícula (RF-20).
        "chave": "maya", "nome": "Maya Inventada Estrela", "idade": 7, "mes": 5, "ano_escolar": "2ano",
        "escola": None, "sem_matricula": True, "unidade": ANDAR_3, "leito": "305C", "internacao": 25,
        "cadastro": 20, "criado_por": "rita", "aulas": ((2, "ana"), (4, "diego")), "raca_cor": "indigena",
        "responsaveis": (("Lúcia Inventada Estrela", "mae", "lucia.estrela@exemplo.org"),),
        "autorizacoes": {
            Tipo.USO_DADOS: (("valida_papel", 19, "ana"),),
            Tipo.CONTATO_ESCOLA: (("provisoria", 12, "ana"),),
        },
    },
    {
        # Encerrado por alta, em tratamento de TMO: falta ver o professor domiciliar (RF-24).
        "chave": "caio", "nome": "Caio Fictício Trovão", "idade": 10, "mes": 1, "ano_escolar": "5ano",
        "escola": "99000005", "unidade": ANDAR_4, "leito": "408A", "internacao": 50, "cadastro": 35,
        "criado_por": "bruno", "aulas": ((0, "bruno"), (2, "ana")), "tmo": True, "raca_cor": "parda",
        "situacao": {
            "para": Aluno.Situacao.ENCERRADO, "dias": 5, "motivo": "Alta hospitalar (dado fictício).",
            "motivo_saida": "Alta", "por": "rita", "responsavel": "rita",
        },
        "responsaveis": (("Rosa Fictícia Trovão", "mae", "rosa.trovao@exemplo.org"),),
        "autorizacoes": {
            Tipo.USO_DADOS: (("valida_tablet", 34, "bruno"),),
            Tipo.CONTATO_ESCOLA: (("revogada", 34, "bruno", 15),),
        },
    },
    {
        "chave": "bia", "nome": "Beatriz Exemplo Arco-Íris", "nome_social": "Bia", "idade": 9, "mes": 9,
        "ano_escolar": "4ano", "escola": "99000006", "unidade": AMBULATORIO, "cadastro": 35,
        "criado_por": "diego", "aulas": ((1, "diego"), (3, "ana")), "raca_cor": "amarela",
        "situacao": {
            "para": Aluno.Situacao.PAUSA, "dias": 10, "motivo": "A família pediu uma pausa nas aulas (dado fictício).",
            "por": "marcos",
        },
        "responsaveis": (("Tânia Exemplo Arco-Íris", "tio", "tania.arcoiris@exemplo.org"),),
        "autorizacoes": {
            Tipo.USO_DADOS: (("valida_papel", 34, "diego"),),
            Tipo.CONTATO_ESCOLA: (("valida_papel", 34, "diego"),),
        },
    },
    {
        # Sem nenhuma autorização colhida: vira pendência do professor da primeira aula (RF-19).
        "chave": "enzo", "nome": "Enzo Teste Cata-Vento", "idade": 12, "mes": 2, "ano_escolar": "7ano",
        "escola": "99000008", "unidade": HOSPITAL_DIA, "cadastro": 21, "criado_por": "elisa",
        "aulas": ((0, "elisa"), (4, "carla")), "raca_cor": "nao_declarada",
        "responsaveis": (("Paulo Teste Cata-Vento", "pai", "paulo.catavento@exemplo.org"),),
        "autorizacoes": {},
    },
    {
        "chave": "luna", "nome": "Luna Fictícia Marola", "idade": 16, "mes": 6, "ano_escolar": "1em",
        "escola": "99000002", "unidade": ANDAR_4, "leito": "415C", "internacao": 30, "cadastro": 30,
        "criado_por": "carla", "aulas": ((1, "carla"), (2, "elisa")), "raca_cor": "branca",
        "responsaveis": (("Irene Fictícia Marola", "mae", "irene.marola@exemplo.org"),),
        "autorizacoes": {
            Tipo.USO_DADOS: (("valida_tablet", 29, "carla"),),
            Tipo.CONTATO_ESCOLA: (("valida_tablet", 29, "carla"),),
        },
    },
    {
        # Ficha incompleta: nenhum responsável cadastrado.
        "chave": "gael", "nome": "Gael Inventado Ventania", "idade": 6, "mes": 4, "ano_escolar": "1ano",
        "escola": "99000010", "unidade": CASA_DE_APOIO, "cadastro": 14, "criado_por": "diego",
        "aulas": ((0, "diego"), (3, "ana")), "raca_cor": "parda", "responsaveis": (),
        "autorizacoes": {Tipo.USO_DADOS: (("pendente", 13, "diego"),)},
    },
    {
        # Ficha incompleta: sem escola de origem e sem a marca de "não tem matrícula".
        "chave": "iara", "nome": "Iara Exemplo Pirilampo", "idade": 13, "mes": 8, "ano_escolar": "8ano",
        "escola": None, "unidade": ANDAR_3, "leito": "310B", "internacao": 26, "cadastro": 25,
        "criado_por": "fabio", "aulas": ((2, "bruno"), (4, "elisa")), "raca_cor": "preta",
        "responsaveis": (("Heloísa Exemplo Pirilampo", "mae", "heloisa.pirilampo@exemplo.org"),),
        "autorizacoes": {
            Tipo.USO_DADOS: (("valida_papel", 24, "bruno"),),
            Tipo.CONTATO_ESCOLA: (("pendente", 4, "bruno"),),
        },
    },
    {
        "chave": "noah", "nome": "Noah Teste Bem-te-vi", "idade": 5, "mes": 10, "ano_escolar": "infantil",
        "escola": "99000007", "unidade": AMBULATORIO, "cadastro": 28, "criado_por": "ana",
        "aulas": ((1, "ana"), (4, "diego")), "raca_cor": "branca",
        "responsaveis": (("Vera Teste Bem-te-vi", "mae", "vera.bemtevi@exemplo.org"),),
        "autorizacoes": {
            Tipo.USO_DADOS: (("valida_papel", 27, "ana"),),
            Tipo.CONTATO_ESCOLA: (("valida_papel", 27, "ana"),),
        },
    },
    {
        "chave": "zoe", "nome": "Zoe Fictícia Caramelo", "idade": 17, "mes": 12, "ano_escolar": "3em",
        "escola": "99000012", "unidade": HOSPITAL_DIA, "cadastro": 33, "criado_por": "carla",
        "aulas": ((0, "carla"), (2, "elisa")), "raca_cor": "parda",
        "responsaveis": (("Otávio Fictício Caramelo", "pai", "otavio.caramelo@exemplo.org"),),
        "autorizacoes": {
            Tipo.USO_DADOS: (("valida_tablet", 32, "elisa"),),
            Tipo.CONTATO_ESCOLA: (("valida_papel", 32, "elisa"),),
        },
    },
    {
        "chave": "ravi", "nome": "Ravi Inventado Orvalho", "idade": 10, "mes": 3, "ano_escolar": "5ano",
        "escola": "99000013", "unidade": ANDAR_4, "leito": "402A", "internacao": 35, "cadastro": 32,
        "criado_por": "bruno", "aulas": ((1, "bruno"), (3, "diego")), "raca_cor": "branca",
        "responsaveis": (("Nádia Inventada Orvalho", "mae", "nadia.orvalho@exemplo.org"),),
        "autorizacoes": {
            Tipo.USO_DADOS: (("valida_papel", 31, "bruno"),),
            Tipo.CONTATO_ESCOLA: (("valida_tablet", 31, "bruno"),),
        },
    },
    {
        # Ativo sem nenhuma aula há mais de 21 dias: entra na revisão de ativo (RF-21).
        "chave": "alice", "nome": "Alice Exemplo Ciranda", "idade": 8, "mes": 6, "ano_escolar": "3ano",
        "escola": "99000014", "unidade": AMBULATORIO, "cadastro": 30, "criado_por": "rita", "aulas": (),
        "raca_cor": "nao_declarada",
        "responsaveis": (("Glória Exemplo Ciranda", "avo", "gloria.ciranda@exemplo.org"),),
        "autorizacoes": {
            Tipo.USO_DADOS: (("valida_papel", 29, "rita"),),
            Tipo.CONTATO_ESCOLA: (("valida_papel", 29, "rita"),),
        },
    },
)

# ---------------------------------------------------------------- aulas

HORARIOS = tuple(
    datetime.time(hora, minuto)
    for hora, minuto in ((8, 30), (9, 0), (9, 30), (10, 0), (10, 30), (13, 30), (14, 0), (14, 30), (15, 0), (15, 30))
)
DURACOES = (30, 30, 30, 45, 60, 20)
# Aulas que já passaram e ficaram sem registro, por professor: viram pendência dele.
AULAS_SEM_REGISTRO = {"ana": 2, "bruno": 1, "carla": 1}
CHANCE_DE_NAO_ACONTECER = 0.08
QUANTAS_AULAS_COM_FOTO = 6

ATIVIDADES = {
    "Língua Portuguesa": (
        "Leitura de um conto curto e conversa sobre os personagens.",
        "Escrita de um bilhete para a família.",
        "Jogo de rimas com cartões.",
    ),
    "Alfabetização": (
        "Letras móveis para formar o próprio nome.",
        "Reconhecimento das vogais com desenhos.",
        "Leitura de palavras simples com figuras.",
    ),
    "Matemática": (
        "Problemas de adição com material dourado.",
        "Jogo de tabuada com dados.",
        "Frações com desenhos de pizza.",
    ),
    "Ciências": (
        "Ciclo da água desenhado em etapas.",
        "Partes da planta com a observação de uma folha.",
        "Estados físicos da água com exemplos do dia a dia.",
    ),
    "História": (
        "Linha do tempo com fatos inventados de uma família de mentira.",
        "Brincadeiras de antigamente.",
        "Leitura e conversa sobre os povos indígenas.",
    ),
    "Geografia": (
        "Mapa de um caminho inventado entre a casa e a escola.",
        "Pontos cardeais a partir da janela do quarto.",
        "Paisagens do campo e da cidade.",
    ),
    "Arte": (
        "Colagem com papéis coloridos.",
        "Desenho de observação de objetos do quarto.",
        "Pintura com aquarela.",
    ),
    "Inglês": (
        "Cores e números em inglês com música.",
        "Vocabulário da família em inglês.",
        "Cumprimentos e apresentação pessoal.",
    ),
}
PARTICIPACOES = (
    "Participou com interesse e terminou a atividade.",
    "Cansou no meio da aula; a atividade continua na próxima.",
    "Pediu para repetir o jogo; boa participação.",
    "Teve dificuldade no começo e avançou com apoio.",
    "Participou pouco hoje e preferiu ouvir a leitura.",
)
MOTIVOS_SEM_AULA = (
    "Exame no horário da aula.",
    "A criança estava dormindo.",
    "Procedimento no horário combinado.",
)

# ---------------------------------------------------------------- imagens geradas

PALETA = ((46, 125, 107), (214, 140, 69), (88, 120, 196), (196, 88, 120), (240, 200, 80), (120, 180, 90))
FUNDOS = ((250, 244, 230), (232, 244, 240), (238, 238, 250), (252, 236, 236))
TINTA = (22, 32, 29)
CINZA = (90, 90, 90)
CAMINHO_DA_FONTE = Path("static") / "fonts" / "atkinson-hyperlegible-next-latin-700-normal.woff2"


def _fonte(tamanho):
    """A fonte da própria plataforma; sem ela, a fonte do Pillow (sem acentos)."""
    try:
        return ImageFont.truetype(str(Path(settings.BASE_DIR) / CAMINHO_DA_FONTE), tamanho), True
    except OSError:
        return ImageFont.load_default(), False


def _escrever(desenho, centro_x, y, texto, tamanho, cor):
    fonte, tem_acentos = _fonte(tamanho)
    if not tem_acentos:
        texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    caixa = desenho.textbbox((0, 0), texto, font=fonte)
    desenho.text((centro_x - (caixa[2] - caixa[0]) // 2, y), texto, font=fonte, fill=cor)


def _em_bytes(imagem, formato, **opcoes):
    saida = io.BytesIO()
    imagem.save(saida, format=formato, **opcoes)
    return saida.getvalue()


def imagem_de_foto(rng, legenda):
    """Foto de atividade de mentira: formas coloridas e o aviso "Foto fictícia"."""
    largura, altura = 960, 720
    imagem = Image.new("RGB", (largura, altura), rng.choice(FUNDOS))
    desenho = ImageDraw.Draw(imagem)
    for _ in range(8):
        cor = rng.choice(PALETA)
        x, y, lado = rng.randint(-60, largura - 100), rng.randint(-60, altura - 100), rng.randint(90, 260)
        forma = rng.choice(("circulo", "retangulo", "triangulo"))
        if forma == "circulo":
            desenho.ellipse((x, y, x + lado, y + lado), fill=cor)
        elif forma == "retangulo":
            desenho.rounded_rectangle((x, y, x + lado, y + lado * 2 // 3), radius=24, fill=cor)
        else:
            desenho.polygon([(x, y + lado), (x + lado // 2, y), (x + lado, y + lado)], fill=cor)
    desenho.rounded_rectangle((150, 280, largura - 150, 440), radius=28, fill=(255, 255, 255), outline=TINTA, width=4)
    _escrever(desenho, largura // 2, 298, "Foto fictícia", 64, TINTA)
    _escrever(desenho, largura // 2, 384, legenda, 30, CINZA)
    return _em_bytes(imagem, "JPEG", quality=80)


def imagem_de_documento(titulo, formato="JPEG"):
    """Folha de papel de mentira, escrita "Documento fictício de teste", em JPEG ou PDF."""
    largura, altura = 680, 880
    imagem = Image.new("RGB", (largura, altura), (255, 255, 255))
    desenho = ImageDraw.Draw(imagem)
    desenho.rectangle((24, 24, largura - 24, altura - 24), outline=TINTA, width=3)
    _escrever(desenho, largura // 2, 70, "Documento fictício de teste", 40, TINTA)
    _escrever(desenho, largura // 2, 130, titulo, 24, CINZA)
    y = 200
    for linha in range(14):
        comprimento = 500 if linha % 4 != 3 else 300
        desenho.rounded_rectangle((90, y, 90 + comprimento, y + 12), radius=6, fill=(215, 215, 215))
        y += 34
    pontos = [(380 + x, 740 + int(16 * math.sin(x / 13))) for x in range(0, 220, 4)]
    desenho.line(pontos, fill=(40, 60, 140), width=4)
    desenho.line((360, 780, 620, 780), fill=TINTA, width=2)
    _escrever(desenho, 490, 790, "Assinatura fictícia", 20, CINZA)
    if formato == "PDF":
        return _em_bytes(imagem, "PDF", resolution=100.0)
    return _em_bytes(imagem, "JPEG", quality=85)


def imagem_de_assinatura(rng):
    """Rabisco de mentira, como o quadro de assinatura do tablet grava (PNG)."""
    largura, altura = 600, 200
    imagem = Image.new("RGBA", (largura, altura), (255, 255, 255, 0))
    desenho = ImageDraw.Draw(imagem)
    fase, amplitude = rng.uniform(0, math.pi), rng.randint(18, 34)
    pontos = [
        (40 + x, 90 + int(amplitude * math.sin(x / 17 + fase) * math.cos(x / 41)))
        for x in range(0, 520, 3)
    ]
    desenho.line(pontos, fill=(*TINTA, 255), width=5, joint="curve")
    _escrever(desenho, largura // 2, 160, "assinatura fictícia", 20, (*CINZA, 255))
    return _em_bytes(imagem, "PNG")


def conversa_de_whatsapp(momento):
    """Conversa exportada de mentira, para o sim provisório por WhatsApp."""
    quando = timezone.localtime(momento).strftime("%d/%m/%Y %H:%M")
    return (
        "Conversa fictícia de teste: não é uma conversa real.\n"
        f"[{quando}] Professora fictícia: Podemos falar com a escola sobre as aulas no hospital?\n"
        f"[{quando}] Responsável fictício: Sim, autorizo o contato com a escola.\n"
    ).encode()


def sha256(dados):
    return hashlib.sha256(dados).hexdigest()


# ---------------------------------------------------------------- comando


@dataclass
class PlanoDeAula:
    aluno: Aluno
    professor: object
    chave: str
    dia: datetime.date
    primeira: bool = False
    situacao: str = Aula.Situacao.MARCADA
    hora: datetime.time | None = None


def _campos(modelo):
    """Campos que vão para a trilha: os de GRUPOS_DE_CAMPOS ou, sem eles, os editáveis do modelo."""
    campos = [nome for nomes in getattr(modelo, "GRUPOS_DE_CAMPOS", {}).values() for nome in nomes]
    if campos:
        return campos
    base = {"id", "servico", "criado_em", "atualizado_em", "criado_por", "atualizado_por", "versao"}
    return [
        campo.name for campo in [*modelo._meta.fields, *modelo._meta.many_to_many]
        if campo.editable and campo.name not in base
    ]


def _mudancas_do_papel(papel):
    rotulos = dict(NIVEIS)
    nomes_das_acoes = dict(ACOES)
    mudancas = {
        f"acesso_{codigo}": {
            "rotulo": NOMES_DE_GRUPO[codigo], "grupo": None, "de": "", "para": rotulos[papel.acessos[codigo]],
        }
        for codigo in CODIGOS_DE_GRUPO
    }
    mudancas["acoes"] = {
        "rotulo": "ações liberadas", "grupo": None, "de": "",
        "para": ", ".join(nomes_das_acoes[acao] for acao in papel.acoes) or "Nenhuma",
    }
    mudancas["pode_configurar"] = {
        "rotulo": "pode configurar o serviço", "grupo": None, "de": "",
        "para": "Sim" if papel.pode_configurar else "Não",
    }
    return mudancas


def _alfabetizacao_pela_idade(idade):
    if idade is None:
        return Aluno.Alfabetizacao.NAO_AVALIADO
    if idade < 6:
        return Aluno.Alfabetizacao.NAO_SE_APLICA
    if idade < 8:
        return Aluno.Alfabetizacao.EM_ALFABETIZACAO
    return Aluno.Alfabetizacao.ALFABETIZADO


class Command(BaseCommand):
    help = (
        f'Cria o serviço "{NOME_DO_SERVICO}" com papéis, pessoas, escolas, alunos, autorizações, aulas, '
        "reuniões e documentos inventados. Só roda no ambiente de teste."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--recriar", action="store_true",
            help="Apaga os dados do serviço de teste (a trilha fica) e cria tudo de novo.",
        )
        parser.add_argument(
            "--senha",
            help="Senha forte igual para todas as pessoas criadas. Sem ela, cada pessoa recebe uma senha "
                 "aleatória, mostrada uma única vez no fim.",
        )

    # ------------------------------------------------------------ entrada

    def handle(self, *args, **opcoes):
        if not getattr(settings, "AMBIENTE_DE_TESTE", False):
            raise CommandError(
                "Este comando só roda no ambiente de teste (ENTRELACO_AMBIENTE_DE_TESTE=1). Ele cria pessoas e "
                "alunos inventados, que não podem se misturar com dados de verdade."
            )
        senha = opcoes.get("senha")
        if senha is not None:
            try:
                validate_password(senha)
            except ValidationError as erro:
                raise CommandError(
                    "A senha de --senha não serve: " + " ".join(erro.messages) + " Escolha uma senha mais longa."
                ) from erro

        existente = Servico.objects.filter(slug=SLUG_DO_SERVICO).first()
        existente = existente or Servico.objects.filter(nome=NOME_DO_SERVICO).first()
        if existente is not None and not opcoes["recriar"]:
            self.stdout.write(
                f'O serviço "{existente.nome}" já existe, e nada foi criado de novo. '
                "Para apagar os dados dele e criar tudo outra vez, use --recriar."
            )
            return

        self.hoje = timezone.localdate()
        self.agora = timezone.now()
        self.rng = random.Random(SEMENTE)
        self.arquivos_novos = []
        try:
            with transaction.atomic():
                if existente is not None:
                    self.servico = self._apagar_dados_do_servico(existente)
                else:
                    self.servico = Servico.objects.create(nome=NOME_DO_SERVICO, slug=SLUG_DO_SERVICO)
                    self._trilha(
                        Acao.CRIOU, self.servico, detalhe="criou o serviço de teste",
                        mudancas=self._mudancas_de_criacao(
                            self.servico, ["nome", "minutos_por_aula", "prazo_revisao_ativo_dias"]
                        ),
                    )
                senhas = self._criar_tudo(senha)
        except BaseException:
            # O banco volta atrás sozinho; os arquivos gravados no disco, não.
            self._apagar_arquivos(self.arquivos_novos)
            raise
        self._mostrar_resumo(senhas, senha_unica=senha is not None, recriado=existente is not None)

    def _criar_tudo(self, senha):
        self._criar_escolas()
        self._criar_papeis()
        senhas = self._criar_pessoas(senha)
        self._criar_componentes()
        self._criar_perfis()
        self._criar_termos()
        self._criar_contatos()
        self._criar_alunos()
        self._criar_aulas()
        self._criar_reunioes()
        self._criar_documentos()
        return senhas

    # ------------------------------------------------------------ ajudas

    def _dias_atras(self, dias):
        return self.hoje - datetime.timedelta(days=dias)

    def _dia_util(self, deslocamento):
        """Dia de semana mais perto de hoje + deslocamento, sem sair do lado (passado ou futuro)."""
        dia = self.hoje + datetime.timedelta(days=deslocamento)
        passo = -UM_DIA if deslocamento < 0 else UM_DIA
        while dia.weekday() >= 5:
            dia += passo
        return dia

    def _momento(self, dia, hora=9, minuto=0):
        momento = timezone.make_aware(datetime.datetime.combine(dia, datetime.time(hora, minuto)))
        return min(momento, self.agora).replace(microsecond=0)

    def _datar(self, obj, momento):
        """Põe a data de criação no passado, para as pendências e a ordem de atendimento fazerem sentido."""
        type(obj).objects.filter(pk=obj.pk).update(criado_em=momento, atualizado_em=momento)
        obj.criado_em = obj.atualizado_em = momento

    def _novo(self, modelo, autor, **campos):
        return modelo.objects.create(servico=self.servico, criado_por=autor, atualizado_por=autor, **campos)

    def _salvar_arquivo(self, campo, nome, dados):
        campo.save(nome, ContentFile(dados), save=False)
        self.arquivos_novos.append(campo.name)

    @staticmethod
    def _mudancas_de_criacao(obj, campos=None):
        campos = campos or _campos(type(obj))
        return auditoria.comparar(type(obj), {}, auditoria.fotografar(obj, campos))

    def _trilha(self, acao, obj, autor=None, *, detalhe="", mudancas=None, motivo="", aluno=None):
        """Grava na trilha, como as telas fazem, com a marca da carga de dados fictícios."""
        if mudancas is None:
            mudancas = self._mudancas_de_criacao(obj) if acao == Acao.CRIOU else {}
        auditoria.registrar(
            None, acao, obj, usuario=autor, servico=self.servico, mudancas=mudancas, motivo=motivo,
            descricao=f"{DESCRICAO_DA_CARGA}: {detalhe}" if detalhe else DESCRICAO_DA_CARGA, aluno=aluno,
        )

    def _senha_aleatoria(self, usuario):
        alfabeto = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        while True:
            senha = "-".join("".join(secrets.choice(alfabeto) for _ in range(5)) for _ in range(4))
            try:
                validate_password(senha, usuario)
            except ValidationError:
                continue
            return senha

    @staticmethod
    def _apagar_arquivos(nomes):
        for nome in nomes:
            try:
                default_storage.delete(nome)
            except OSError:
                pass

    # ------------------------------------------------------------ --recriar

    def _apagar_dados_do_servico(self, servico):
        """Apaga tudo o que é do serviço de teste. A trilha fica: ela nunca é apagada (SEG-03)."""
        modelos = [modelo for modelo in apps.get_models() if issubclass(modelo, ModeloDoServico)]
        arquivos = []
        for modelo in modelos:
            for campo in modelo._meta.fields:
                if isinstance(campo, FileField):
                    nomes = modelo.objects.filter(servico=servico).values_list(campo.name, flat=True)
                    arquivos.extend(nome for nome in nomes if nome)
        # Apaga em rodadas: o que está preso por PROTECT sai depois de quem o prende.
        restantes = modelos
        for _ in range(len(modelos)):
            presos = []
            for modelo in restantes:
                try:
                    with transaction.atomic():
                        modelo.objects.filter(servico=servico).delete()
                except (ProtectedError, RestrictedError):
                    presos.append(modelo)
            if not presos:
                break
            restantes = presos
        else:
            nomes = ", ".join(modelo._meta.verbose_name_plural for modelo in restantes)
            raise CommandError(f"Não foi possível apagar os dados do serviço de teste: {nomes}.")

        Usuario = get_user_model()
        ids = list(Vinculo.objects.filter(servico=servico).values_list("usuario_id", flat=True))
        Vinculo.objects.filter(servico=servico).delete()
        Papel.objects.filter(servico=servico).delete()
        # Só some quem é da carga (e-mail @exemplo.org) e não tem vínculo com outro serviço.
        sozinhos = Usuario.objects.filter(
            pk__in=ids, is_superuser=False, is_staff=False, email__iendswith=DOMINIO_DOS_EMAILS, vinculos__isnull=True,
        )
        for usuario in sozinhos:
            try:
                with transaction.atomic():
                    usuario.delete()
            except (ProtectedError, RestrictedError):
                pass

        servico.nome = NOME_DO_SERVICO
        servico.slug = SLUG_DO_SERVICO
        servico.ativo = True
        servico.minutos_por_aula = 30
        servico.bncc_ativa = False
        servico.prazo_revisao_ativo_dias = 21
        servico.motivos_saida = motivos_de_saida_padrao()
        servico.save()
        self.servico = servico
        self._trilha(
            Acao.EXCLUIU, servico,
            detalhe="apagou os dados do serviço de teste para criar de novo (--recriar)",
        )
        transaction.on_commit(lambda: self._apagar_arquivos(arquivos))
        return servico

    # ------------------------------------------------------------ cadastros do serviço

    def _criar_escolas(self):
        """Base comum de escolas: atualiza ou cria as escolas inventadas (códigos INEP começando por 99)."""
        self.escolas, self.ddd = {}, {}
        for numero, (codigo, nome, rede, municipio, ddd) in enumerate(ESCOLAS, start=1):
            dados = {
                "nome": nome, "rede": rede, "municipio": municipio, "uf": "SP",
                "endereco": f"Rua Fictícia das Escolas, {numero * 100}", "bairro": "Bairro Inventado",
                "telefone": f"({ddd}) 0000-{numero:04d}", "fonte": FONTE_DAS_ESCOLAS,
                "funcionamento": (
                    Escola.Funcionamento.PARALISADA if codigo in ESCOLAS_PARALISADAS
                    else Escola.Funcionamento.EM_ATIVIDADE
                ),
            }
            escola, criada = Escola.objects.update_or_create(codigo_inep=codigo, defaults=dados)
            if criada:
                # A base de escolas é comum a todos os serviços: o evento não fica em nenhum deles.
                auditoria.registrar(
                    None, Acao.CRIOU, escola, servico=None,
                    mudancas=self._mudancas_de_criacao(escola, ["codigo_inep", "nome", "municipio", "uf"]),
                    descricao=f"{DESCRICAO_DA_CARGA}: escola da base de teste",
                )
            self.escolas[codigo] = escola
            self.ddd[codigo] = ddd

    def _criar_papeis(self):
        self.papeis = {}
        for definicao in PAPEIS:
            acessos = {grupo: NENHUM for grupo in CODIGOS_DE_GRUPO}
            acessos.update({grupo: VER for grupo in definicao.ver})
            acessos.update({grupo: EDITAR for grupo in definicao.editar})
            papel = Papel.objects.create(
                servico=self.servico, nome=definicao.nome, descricao=definicao.descricao, acessos=acessos,
                acoes=list(definicao.acoes), pode_configurar=definicao.configurar,
            )
            self._trilha(Acao.CRIOU, papel, detalhe=f"criou o papel {papel.nome}", mudancas={})
            self._trilha(
                Acao.LIBEROU_PERMISSAO, papel, detalhe=f"permissões do papel {papel.nome}",
                mudancas=_mudancas_do_papel(papel),
            )
            self.papeis[definicao.chave] = papel

    def _criar_pessoas(self, senha):
        Usuario = get_user_model()
        self.pessoas = {}
        senhas = []
        for pessoa in PESSOAS:
            papel = self.papeis[pessoa.papel]
            usuario = Usuario.objects.filter(email__iexact=pessoa.email).first()
            nova = usuario is None
            if nova:
                # Quem configura começa sem a verificação em duas etapas e ativa no primeiro login (SEG-07).
                usuario = Usuario(email=pessoa.email, totp_ativo=False, totp_segredo="")
            usuario.nome = pessoa.nome
            usuario.is_active = True
            senha_da_pessoa = senha or self._senha_aleatoria(usuario)
            usuario.set_password(senha_da_pessoa)
            usuario.save()
            if nova:
                self._trilha(
                    Acao.CRIOU, usuario, detalhe="cadastrou a pessoa",
                    mudancas=self._mudancas_de_criacao(usuario, ["nome", "email"]),
                )
            vinculo = Vinculo.objects.create(usuario=usuario, servico=self.servico, papel=papel)
            self._trilha(
                Acao.CRIOU, vinculo, detalhe=f"deu a {usuario.nome} o papel {papel.nome}",
                mudancas=self._mudancas_de_criacao(vinculo, ["papel"]),
            )
            self.pessoas[pessoa.chave] = usuario
            senhas.append((pessoa.email, papel.nome, senha_da_pessoa))
        return senhas

    def _criar_componentes(self):
        autor = self.pessoas["helena"]
        self.componentes = {}
        for nome in COMPONENTES:
            componente = self._novo(ComponenteCurricular, autor, nome=nome)
            self._trilha(Acao.CRIOU, componente, autor, detalhe="componente curricular")
            self.componentes[nome] = componente

    def _criar_perfis(self):
        autor = self.pessoas["helena"]
        for pessoa in PESSOAS:
            if not pessoa.componentes:
                continue
            perfil = self._novo(
                PerfilProfessor, autor, usuario=self.pessoas[pessoa.chave], observacoes="Perfil fictício de teste.",
                **{etapa: True for etapa in pessoa.etapas},
            )
            perfil.componentes.set([self.componentes[nome] for nome in pessoa.componentes])
            self._trilha(Acao.CRIOU, perfil, autor, detalhe="perfil do professor")

    def _criar_termos(self):
        autor = self.pessoas["helena"]
        self.termos = {}
        for tipo, (titulo, corpo) in TERMOS.items():
            termo = self._novo(
                Termo, autor, tipo=tipo, versao_do_termo=1, titulo=titulo,
                texto=f"{TEXTO_PROVISORIO}\n\n{corpo}", vigente=True,
            )
            self._datar(termo, self._momento(self._dias_atras(40)))
            self._trilha(Acao.CRIOU, termo, autor, detalhe="termo provisório, até o texto do advogado")
            self.termos[tipo] = termo

    def _criar_contatos(self):
        autor = self.pessoas["fabio"]
        for codigo, (situacao, dias) in CONTATOS.items():
            numero = int(codigo[-2:])
            contato = self._novo(
                ContatoEscola, autor, escola=self.escolas[codigo],
                email=f"secretaria.escola{numero:02d}{DOMINIO_DOS_EMAILS}",
                telefone=f"({self.ddd[codigo]}) 0000-{numero + 50:04d}",
                quem_atende="Secretaria da escola (contato fictício)", observacoes="Contato fictício de teste.",
                situacao=ContatoEscola.Situacao.PRECISA_ATUALIZAR,
            )
            self._datar(contato, self._momento(self._dias_atras(60)))
            self._trilha(Acao.CRIOU, contato, autor, detalhe="contato da escola")
            if situacao != ContatoEscola.Situacao.ATUALIZADO:
                continue
            antes = auditoria.fotografar(contato, ["situacao"])
            contato.situacao = ContatoEscola.Situacao.ATUALIZADO
            contato.confirmado_em = self._dias_atras(dias)
            contato.confirmado_por = autor
            contato.versao += 1
            contato.save()
            self._trilha(
                Acao.VALIDOU, contato, autor, detalhe="confirmou o contato da escola",
                mudancas=auditoria.comparar(ContatoEscola, antes, auditoria.fotografar(contato, ["situacao"])),
            )

    # ------------------------------------------------------------ alunos

    def _criar_alunos(self):
        self.alunos = {}
        telefones = iter(range(1, 1000))
        for numero, ficha in enumerate(ALUNOS, start=1):
            autor = self.pessoas[ficha["criado_por"]]
            cadastro = self._dias_atras(ficha["cadastro"])
            idade = ficha.get("idade")
            escola = self.escolas[ficha["escola"]] if ficha.get("escola") else None
            aluno = self._novo(
                Aluno, autor,
                nome=ficha["nome"], nome_social=ficha.get("nome_social", ""),
                data_nascimento=datetime.date(self.hoje.year - idade, ficha["mes"], 15) if idade else None,
                unidade=ficha["unidade"], leito=ficha.get("leito", ""),
                data_internacao=self._dias_atras(ficha["internacao"]) if ficha.get("internacao") else None,
                situacao=Aluno.Situacao.ATIVO, situacao_desde=cadastro,
                visao=ficha.get("visao", Aluno.Condicao.SEM_ALTERACAO),
                audicao=Aluno.Condicao.SEM_ALTERACAO, fala=Aluno.Condicao.SEM_ALTERACAO,
                motricidade=Aluno.Condicao.SEM_ALTERACAO,
                alfabetizacao=ficha.get("alfabetizacao") or _alfabetizacao_pela_idade(idade),
                reprovacao=ficha.get("reprovacao", Aluno.Reprovacao.NUNCA),
                condicoes_observacoes=ficha.get("condicoes", ""),
                diagnostico=DIAGNOSTICO, tratamento=TRATAMENTO, tmo=ficha.get("tmo", False),
                raca_cor=ficha.get("raca_cor", ""), observacoes_saude=ficha.get("saude", ""),
                escola=escola, sem_matricula=ficha.get("sem_matricula", False),
                ano_escolar=ficha.get("ano_escolar", ""), turma="A" if escola else "",
                ra=f"RA-FICT-{numero:04d}" if escola else "",
                risco_evasao=bool(ficha.get("risco")), risco_evasao_motivo=ficha.get("risco", ""),
            )
            self._datar(aluno, self._momento(cadastro))
            self._trilha(Acao.CRIOU, aluno, autor, detalhe="cadastrou o aluno")

            responsaveis = []
            for nome, parentesco, email in ficha.get("responsaveis", ()):
                telefone = next(telefones)
                responsavel = self._novo(
                    Responsavel, autor, aluno=aluno, nome=nome, parentesco=parentesco, responsavel_legal=True,
                    telefone=f"(11) 90000-{telefone:04d}", tem_whatsapp=telefone % 3 != 0, email=email,
                    observacoes="Responsável fictício de teste.",
                )
                self._datar(responsavel, self._momento(cadastro, 9, 30))
                self._trilha(Acao.CRIOU, responsavel, autor, detalhe="cadastrou o responsável")
                responsaveis.append(responsavel)

            for tipo, coletas in ficha.get("autorizacoes", {}).items():
                for coleta in coletas:
                    self._criar_autorizacao(aluno, tipo, coleta, responsaveis[0] if responsaveis else None)
            if ficha.get("situacao"):
                self._mudar_situacao(aluno, ficha["situacao"])
            self.alunos[ficha["chave"]] = aluno

    def _mudar_situacao(self, aluno, dados):
        """Como a tela de situação faz: guarda a mudança, atualiza o aluno e grava na trilha (RF-11, RF-22)."""
        autor = self.pessoas[dados["por"]]
        responsavel = self.pessoas[dados["responsavel"]] if dados.get("responsavel") else None
        data = self._dias_atras(dados["dias"])
        de, para = aluno.situacao, dados["para"]
        campos = ["situacao", "situacao_desde"]
        antes = auditoria.fotografar(aluno, campos)
        mudanca = self._novo(
            MudancaDeSituacao, autor, aluno=aluno, de=de, para=para, data=data, motivo=dados["motivo"],
            motivo_saida=dados.get("motivo_saida", ""), responsavel=responsavel,
        )
        self._datar(mudanca, self._momento(data, 16))
        aluno.situacao, aluno.situacao_desde = para, data
        aluno.versao += 1
        aluno.atualizado_por = autor
        aluno.save(update_fields=["situacao", "situacao_desde", "versao", "atualizado_por", "atualizado_em"])
        mudancas = auditoria.comparar(Aluno, antes, auditoria.fotografar(aluno, campos))
        if para == Aluno.Situacao.ENCERRADO:
            mudancas["motivo_saida"] = {
                "rotulo": "motivo de saída", "grupo": "identificacao", "de": "", "para": dados["motivo_saida"],
            }
            mudancas["responsavel_saida"] = {
                "rotulo": "responsável pela saída", "grupo": "identificacao", "de": "", "para": str(responsavel),
            }
        self._trilha(
            Acao.MUDOU_SITUACAO, aluno, autor, mudancas=mudancas, motivo=dados["motivo"],
            detalhe=f"situação {Aluno.Situacao(de).label} → {Aluno.Situacao(para).label}",
        )

    def _criar_autorizacao(self, aluno, tipo, coleta, responsavel):
        """Uma coleta de autorização, com a prova de cada forma (LGPD-03) e a trilha."""
        forma, dias, chave = coleta[:3]
        colhedor = self.pessoas[chave]
        momento = self._momento(self._dias_atras(dias), 10, 30)
        termo = self.termos[tipo]
        autorizacao = Autorizacao(
            servico=self.servico, aluno=aluno, tipo=tipo, termo=termo, colhida_por=colhedor,
            criado_por=colhedor, atualizado_por=colhedor,
        )
        acao = Acao.ASSINOU
        if forma in ("pendente", "pendente_tablet"):
            autorizacao.situacao = Autorizacao.Situacao.PENDENTE
            acao = Acao.CRIOU
            if forma == "pendente_tablet":
                autorizacao.forma = Autorizacao.Forma.TABLET
                detalhe = "começou a assinatura no tablet, que não foi concluída"
            else:
                detalhe = "registrou a autorização como pendente: a família vai decidir depois"
        else:
            autorizacao.responsavel = responsavel
            autorizacao.responsavel_nome = responsavel.nome if responsavel else "Responsável fictício"
            autorizacao.responsavel_documento = f"Documento fictício {aluno.pk:04d}"
            autorizacao.colhida_em = momento
            if forma == "valida_tablet":
                assinatura = imagem_de_assinatura(self.rng)
                autorizacao.forma = Autorizacao.Forma.TABLET
                autorizacao.situacao = Autorizacao.Situacao.VALIDA
                autorizacao.aparelho = "Tablet fictício de teste"
                autorizacao.impressao_digital = impressao_digital_do_tablet(
                    texto_do_termo=termo.texto, versao_do_termo=termo.versao_do_termo,
                    nome=autorizacao.responsavel_nome, documento=autorizacao.responsavel_documento,
                    decisao=DECISAO_AUTORIZO, colhida_em=momento, assinatura=assinatura,
                )
                self._salvar_arquivo(autorizacao.assinatura, "assinatura.png", assinatura)
                detalhe = "família assinou no tablet: autorizou"
            elif forma == "provisoria":
                conversa = conversa_de_whatsapp(momento)
                autorizacao.forma = Autorizacao.Forma.WHATSAPP
                autorizacao.situacao = Autorizacao.Situacao.PROVISORIA
                autorizacao.impressao_digital = sha256(conversa)
                self._salvar_arquivo(autorizacao.arquivo, "conversa-whatsapp.txt", conversa)
                detalhe = "registrou o sim provisório por WhatsApp"
            else:  # papel: válida, recusada ou válida que depois é revogada
                autorizou = forma != "recusada"
                papel = imagem_de_documento(f"{Tipo(tipo).label} · {aluno.nome_curto}")
                autorizacao.forma = Autorizacao.Forma.PAPEL
                autorizacao.situacao = Autorizacao.Situacao.VALIDA if autorizou else Autorizacao.Situacao.RECUSADA
                autorizacao.impressao_digital = sha256(papel)
                self._salvar_arquivo(autorizacao.arquivo, "papel-assinado.jpg", papel)
                detalhe = "registrou o papel assinado: " + ("autorizou" if autorizou else "não autorizou")
        autorizacao.save()
        self._datar(autorizacao, momento)
        self._trilha(acao, autorizacao, colhedor, detalhe=detalhe)
        if forma == "revogada":
            self._revogar(autorizacao, colhedor, self._momento(self._dias_atras(coleta[3]), 11))
        return autorizacao

    def _revogar(self, autorizacao, autor, momento):
        campos = ["situacao", "revogada_em", "revogacao_motivo"]
        antes = auditoria.fotografar(autorizacao, campos)
        autorizacao.situacao = Autorizacao.Situacao.REVOGADA
        autorizacao.revogada_em = momento
        autorizacao.revogacao_motivo = "A família pediu a revogação por telefone (dado fictício)."
        autorizacao.versao += 1
        autorizacao.atualizado_por = autor
        autorizacao.save()
        self._trilha(
            Acao.ALTEROU, autorizacao, autor, detalhe="registrou a revogação pedida pela família",
            mudancas=auditoria.comparar(Autorizacao, antes, auditoria.fotografar(autorizacao, campos)),
            motivo=autorizacao.revogacao_motivo,
        )

    # ------------------------------------------------------------ aulas

    def _planejar_aulas(self):
        """As aulas da semana de cada aluno, das últimas 4 semanas às próximas 2, só em dias de semana."""
        inicio = self.hoje - datetime.timedelta(weeks=SEMANAS_PARA_TRAS)
        fim = self.hoje + datetime.timedelta(weeks=SEMANAS_PARA_FRENTE)
        planos = []
        for ficha in ALUNOS:
            aluno = self.alunos[ficha["chave"]]
            dia = max(inicio, self._dias_atras(ficha["cadastro"]) + UM_DIA)
            # Em pausa ou encerrado: as aulas param no dia da mudança.
            ultimo = self._dias_atras(ficha["situacao"]["dias"]) - UM_DIA if ficha.get("situacao") else fim
            while dia <= ultimo:
                for dia_da_semana, chave in ficha.get("aulas", ()):
                    if dia.weekday() == dia_da_semana:
                        planos.append(PlanoDeAula(aluno=aluno, professor=self.pessoas[chave], chave=chave, dia=dia))
                dia += UM_DIA
        planos.sort(key=lambda plano: (plano.dia, plano.aluno.pk))

        vistos = set()
        uma_semana_atras = self._dias_atras(7)
        for plano in planos:
            plano.primeira = plano.aluno.pk not in vistos
            vistos.add(plano.aluno.pk)
            if plano.dia >= self.hoje:
                plano.situacao = Aula.Situacao.MARCADA
            elif (not plano.primeira and plano.dia < uma_semana_atras
                  and self.rng.random() < CHANCE_DE_NAO_ACONTECER):
                plano.situacao = Aula.Situacao.NAO_REALIZADA
            else:
                plano.situacao = Aula.Situacao.REGISTRADA
        # Algumas aulas dos últimos dias ficam sem registro: viram pendência do professor.
        dez_dias_atras = self._dias_atras(10)
        for chave, quantas in AULAS_SEM_REGISTRO.items():
            candidatas = [
                plano for plano in reversed(planos)
                if plano.chave == chave and plano.situacao == Aula.Situacao.REGISTRADA and not plano.primeira
                and dez_dias_atras <= plano.dia < self.hoje
            ]
            for plano in candidatas[:quantas]:
                plano.situacao = Aula.Situacao.MARCADA
        # Um horário por professor e dia, sem choque.
        ocupados = set()
        for plano in planos:
            livres = [hora for hora in HORARIOS if (plano.chave, plano.dia, hora) not in ocupados]
            plano.hora = self.rng.choice(livres or HORARIOS)
            ocupados.add((plano.chave, plano.dia, plano.hora))
        return planos

    def _criar_aulas(self):
        registradas = []
        for plano in self._planejar_aulas():
            professor = plano.professor
            duracao = self.rng.choice(DURACOES)
            aula = Aula(
                servico=self.servico, criado_por=professor, atualizado_por=professor, aluno=plano.aluno,
                professor=professor, data=plano.dia, hora_inicio=plano.hora, duracao_minutos=duracao,
                situacao=plano.situacao,
            )
            do_professor = PESSOAS_POR_CHAVE[plano.chave].componentes
            componentes = []
            if plano.situacao != Aula.Situacao.NAO_REALIZADA:
                componentes = self.rng.sample(do_professor, k=self.rng.randint(1, len(do_professor)))
            inicio = datetime.datetime.combine(plano.dia, plano.hora)
            if plano.situacao == Aula.Situacao.REGISTRADA:
                fim = inicio + datetime.timedelta(minutes=duracao)
                aula.conteudo = " ".join(self.rng.choice(ATIVIDADES[nome]) for nome in componentes)
                aula.participacao = self.rng.choice(PARTICIPACOES)
                aula.registrada_em = self._momento(plano.dia, fim.hour, fim.minute)
                aula.registrada_por = professor
                criada_em, detalhe = aula.registrada_em, "aula registrada"
            else:
                criada_em = self._momento(plano.dia - datetime.timedelta(days=3), 17)
                detalhe = "aula marcada"
                if plano.situacao == Aula.Situacao.NAO_REALIZADA:
                    aula.motivo_nao_realizada = self.rng.choice(MOTIVOS_SEM_AULA)
                    detalhe = "aula que não aconteceu"
            aula.save()
            aula.componentes.set([self.componentes[nome] for nome in componentes])
            self._datar(aula, criada_em)
            self._trilha(Acao.CRIOU, aula, professor, detalhe=detalhe)
            if plano.situacao == Aula.Situacao.REGISTRADA:
                registradas.append((aula, componentes))

        sorteadas = self.rng.sample(registradas, k=min(QUANTAS_AULAS_COM_FOTO, len(registradas)))
        for indice, (aula, componentes) in enumerate(sorteadas):
            for _ in range(2 if indice < 2 else 1):
                legenda = f"Atividade de {componentes[0]}"
                foto = FotoDaAula(
                    servico=self.servico, criado_por=aula.professor, atualizado_por=aula.professor, aula=aula,
                    legenda=f"{legenda} (foto fictícia)",
                )
                self._salvar_arquivo(foto.arquivo, "foto.jpg", imagem_de_foto(self.rng, legenda))
                foto.save()
                self._datar(foto, aula.registrada_em)
                self._trilha(Acao.CRIOU, foto, aula.professor, detalhe="foto da aula", aluno=aula.aluno)

    # ------------------------------------------------------------ reuniões e documentos

    def _criar_reunioes(self):
        equipe = [self.pessoas[chave] for chave in ("helena", "marcos", "rita", "ana", "bruno", "carla", "diego",
                                                     "elisa")]
        semanal = self._criar_reuniao(
            self.pessoas["marcos"], tipo=Reuniao.Tipo.SEMANAL, titulo="Reunião semanal da equipe",
            data=self._dia_util(-7), participantes=equipe, local="Sala da equipe (fictícia)",
            pauta="1. Alunos novos da semana.\n2. Encaminhamentos pendentes.\n3. Avisos gerais.",
            ata=("Reunião fictícia de teste. A equipe conversou sobre os alunos novos e combinou os "
                 "encaminhamentos registrados abaixo."),
            situacao=Reuniao.Situacao.REALIZADA,
        )
        self._citar(
            semanal, "davi", grupo="sensivel", responsavel="bruno", prazo=3,
            texto="Dado de saúde fictício: a equipe médica (inventada) pediu aulas mais curtas por alguns dias.",
            encaminhamento="Combinar aulas de 20 minutos com a família.",
        )
        self._citar(
            semanal, "theo", grupo="escolar", responsavel="rita", prazo=-2,
            texto="Faltou a várias aulas seguidas (dado fictício).",
            encaminhamento="Ligar para a família e conversar sobre o risco de evasão.",
        )
        multidisciplinar = self._criar_reuniao(
            self.pessoas["rita"], tipo=Reuniao.Tipo.MULTIDISCIPLINAR, titulo="Reunião multidisciplinar",
            data=self._dia_util(-14), participantes=[self.pessoas[c] for c in ("marcos", "rita", "ana", "diego")],
            local="Auditório do hospital (fictício)",
            pauta="1. Acompanhamento dos alunos internados.\n2. Alunos sem matrícula.",
            ata=("Reunião fictícia de teste com a equipe multidisciplinar (inventada). Ficaram combinados os "
                 "encaminhamentos abaixo."),
            situacao=Reuniao.Situacao.REALIZADA,
        )
        self._citar(
            multidisciplinar, "lia", grupo="atas", responsavel="ana", prazo=-10, concluida=True,
            texto="Avançou bem na leitura de palavras simples (dado fictício).",
            encaminhamento="Enviar à escola as atividades de leitura da semana.",
        )
        self._citar(
            multidisciplinar, "maya", grupo="escolar", responsavel="rita", prazo=7,
            texto="Continua sem matrícula em escola (dado fictício).",
            encaminhamento="Acompanhar o pedido de matrícula com a secretaria de educação.",
        )
        self._criar_reuniao(
            self.pessoas["marcos"], tipo=Reuniao.Tipo.SEMANAL, titulo="Reunião semanal da equipe",
            data=self._dia_util(7), participantes=equipe, local="Sala da equipe (fictícia)",
            pauta="1. Alunos novos da semana.\n2. Revisão dos alunos sem aula.\n3. Avisos gerais.",
            ata="", situacao=Reuniao.Situacao.MARCADA,
        )

    def _criar_reuniao(self, autor, *, participantes, **campos):
        reuniao = self._novo(Reuniao, autor, hora_inicio=datetime.time(14, 0), duracao_minutos=60, **campos)
        reuniao.participantes.set(participantes)
        self._datar(reuniao, self._momento(min(reuniao.data, self.hoje) - datetime.timedelta(days=5), 11))
        self._trilha(Acao.CRIOU, reuniao, autor, detalhe="reunião")
        return reuniao

    def _citar(self, reuniao, chave_do_aluno, *, grupo, responsavel, prazo, concluida=False, **campos):
        autor = reuniao.criado_por
        citacao = self._novo(
            CitacaoDeAluno, autor, reuniao=reuniao, aluno=self.alunos[chave_do_aluno], grupo_de_dado=grupo,
            responsavel=self.pessoas[responsavel], prazo=self.hoje + datetime.timedelta(days=prazo),
            concluida=concluida, **campos,
        )
        self._datar(citacao, self._momento(reuniao.data, 15))
        mudancas = self._mudancas_de_criacao(citacao)
        if grupo != "atas":
            # Citação de saúde ou da vida escolar: o que foi dito é desse tipo de dado também na trilha (RF-07).
            mudancas = {nome: {**mudanca, "grupo": grupo} for nome, mudanca in mudancas.items()}
        self._trilha(Acao.CRIOU, citacao, autor, detalhe="citação em reunião", mudancas=mudancas)

    def _criar_documentos(self):
        documentos = (
            ("lia", "fabio", Documento.Tipo.FICHA_PAPEL, "Ficha de cadastro em papel (fictícia)", 35, "JPEG"),
            ("davi", "bruno", Documento.Tipo.RELATORIO, "Relatório fictício de acompanhamento", 20, "PDF"),
        )
        for chave_do_aluno, chave_do_autor, tipo, titulo, dias, formato in documentos:
            autor = self.pessoas[chave_do_autor]
            dados = imagem_de_documento(titulo, formato=formato)
            documento = Documento(
                servico=self.servico, criado_por=autor, atualizado_por=autor, aluno=self.alunos[chave_do_aluno],
                tipo=tipo, titulo=titulo, data_documento=self._dias_atras(dias),
                observacoes="Documento fictício de teste, gerado pela carga de dados.",
                tamanho=len(dados), impressao_digital=sha256(dados),
            )
            extensao = "pdf" if formato == "PDF" else "jpg"
            self._salvar_arquivo(documento.arquivo, f"documento.{extensao}", dados)
            documento.save()
            self._datar(documento, self._momento(self._dias_atras(dias - 1), 15))
            self._trilha(Acao.CRIOU, documento, autor, detalhe="documento digitalizado")

    # ------------------------------------------------------------ resumo

    def _mostrar_resumo(self, senhas, *, senha_unica, recriado):
        servico = self.servico

        def contar(modelo, **filtros):
            return modelo.objects.filter(servico=servico, **filtros).count()

        aulas = contar(Aula)
        registradas = contar(Aula, situacao=Aula.Situacao.REGISTRADA)
        verbo = "recriado" if recriado else "criado"
        linhas = [
            f'Serviço "{servico.nome}" {verbo}, só com dados inventados:',
            f"  {Papel.objects.filter(servico=servico).count()} papéis, {contar(ComponenteCurricular)} componentes "
            f"curriculares e {contar(Termo)} termos provisórios;",
            f"  {len(ESCOLAS)} escolas inventadas na base e {contar(ContatoEscola)} contatos do serviço;",
            f"  {len(senhas)} pessoas, {contar(Aluno)} alunos e {contar(Responsavel)} responsáveis;",
            f"  {contar(Autorizacao)} autorizações, {aulas} aulas ({registradas} registradas) e "
            f"{contar(FotoDaAula)} fotos de aula;",
            f"  {contar(Reuniao)} reuniões, {contar(CitacaoDeAluno)} citações e {contar(Documento)} documentos.",
            "",
        ]
        self.stdout.write(self.style.SUCCESS(linhas[0]))
        self.stdout.write("\n".join(linhas[1:]))

        largura_email = max(len(email) for email, _, _ in senhas)
        largura_papel = max(len(papel) for _, papel, _ in senhas)
        if senha_unica:
            self.stdout.write("Pessoas para entrar (todas com a senha passada em --senha):")
            self.stdout.write(f"  {'E-mail'.ljust(largura_email)}  Papel")
            for email, papel, _ in senhas:
                self.stdout.write(f"  {email.ljust(largura_email)}  {papel}")
        else:
            self.stdout.write("Pessoas para entrar. Guarde as senhas agora: elas não aparecem de novo.")
            self.stdout.write(f"  {'E-mail'.ljust(largura_email)}  {'Papel'.ljust(largura_papel)}  Senha")
            for email, papel, senha in senhas:
                self.stdout.write(f"  {email.ljust(largura_email)}  {papel.ljust(largura_papel)}  {senha}")
        self.stdout.write(
            "\nQuem tem o papel Supervisão ativa a verificação em duas etapas no primeiro login, "
            "com um aplicativo autenticador no celular."
        )

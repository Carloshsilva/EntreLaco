"""Regras das autorizações da família (RF-25 a RF-29, RF-64, LGPD-03, LGPD-04).

- Cada aluno tem duas autorizações separadas: uso dos dados e contato com a escola (RF-25).
- Cada coleta é um registro novo; a situação atual de um tipo é a da coleta mais
  recente daquele aluno (`autorizacao_atual`). A anterior continua guardada como prova.
- O contato com a escola só sai com a autorização de contato atual válida ou
  provisória (RF-27, RF-28): use `libera_contato_com_a_escola(aluno)` para um aluno, ou
  `alunos_com_contato_liberado(queryset)` para uma lista (o painel da escola).
- A prova de cada coleta (LGPD-03) inclui a impressão digital SHA-256; esta é
  recalculada no comprovante por `conferir_impressao_digital`.

Os textos definitivos dos termos e a lista final do que se guarda como prova de
cada forma esperam o advogado (LGPD-02, LGPD-03); o sim provisório por WhatsApp
vale até a resposta dele (LGPD-05).
"""
import base64
import binascii
import datetime
import hashlib
import io

from django.core.exceptions import ValidationError
from django.db.models import Exists, F, OuterRef, Subquery
from django.utils import timezone

from core.arquivos import validar_documento, validar_tamanho

from .models import Autorizacao, Termo, Tipo, autorizacao_atual

Situacao = Autorizacao.Situacao
Forma = Autorizacao.Forma

GRUPO = "autorizacoes"

SITUACOES_QUE_LIBERAM_CONTATO = (Situacao.VALIDA, Situacao.PROVISORIA)
SITUACOES_QUE_PEDEM_COLETA = (Situacao.PENDENTE, Situacao.RECUSADA, Situacao.REVOGADA)
SITUACOES_QUE_SE_REVOGAM = (Situacao.VALIDA, Situacao.PROVISORIA)
SITUACOES_QUE_VIRAM_PENDENCIA = (Situacao.PENDENTE, Situacao.PROVISORIA)

# Pendente e provisória viram pendência de quem colheu, com este prazo (RF-64).
PRAZO_DA_PENDENCIA_DIAS = 7

# Selo de cada situação: a palavra sempre aparece; a cor só reforça.
CLASSES_DO_SELO = {
    Situacao.VALIDA: "el-badge-success",
    Situacao.PROVISORIA: "el-badge-fita",
    Situacao.PENDENTE: "el-badge-fita",
    Situacao.RECUSADA: "el-badge-danger",
    Situacao.REVOGADA: "el-badge-danger",
}
TEXTO_SEM_COLETA = "Ainda não colhida"

# Decisão da família no tablet; entra na impressão digital.
DECISAO_AUTORIZO = "autorizo"
DECISAO_NAO_AUTORIZO = "nao_autorizo"

# Formas que a pessoa escolhe na tela de colher. "pendente" não é forma de coleta:
# registra que a família vai decidir depois.
PENDENTE = "pendente"
FORMAS_DE_COLETA = [Forma.TABLET, Forma.PAPEL, Forma.WHATSAPP, PENDENTE]


# ---------------------------------------------------------------- contato com a escola (RF-28)

def libera_contato_com_a_escola(aluno):
    """Diz se algo pode ser enviado à escola sobre este aluno (RF-27, RF-28, RF-29).

    True só quando a autorização de contato com a escola *atual* (a coleta mais
    recente) está válida ou provisória (sim por WhatsApp). Sem coleta, pendente,
    recusada ou revogada, devolve False: não sai carta, link, lembrete nem resumo,
    e o aluno não aparece no painel da escola.
    """
    atual = autorizacao_atual(aluno, Tipo.CONTATO_ESCOLA)
    return atual is not None and atual.situacao in SITUACOES_QUE_LIBERAM_CONTATO


def _situacao_atual_do_aluno(tipo):
    return Subquery(
        Autorizacao.objects.filter(aluno=OuterRef("pk"), tipo=tipo).order_by("-criado_em", "-id").values("situacao")[:1]
    )


def alunos_com_contato_liberado(alunos):
    """Filtra um queryset de alunos: só os com contato liberado (RF-28), numa consulta só.

    Para o painel da escola e os envios, que tratam muitos alunos de uma vez.
    """
    return alunos.annotate(situacao_do_contato=_situacao_atual_do_aluno(Tipo.CONTATO_ESCOLA)).filter(
        situacao_do_contato__in=SITUACOES_QUE_LIBERAM_CONTATO
    )


# ---------------------------------------------------------------- coletas atuais

def atuais_do_servico(servico):
    """A coleta atual (a mais recente) de cada aluno e tipo do serviço, numa consulta."""
    mais_recente = Subquery(
        Autorizacao.objects.filter(aluno=OuterRef("aluno"), tipo=OuterRef("tipo"))
        .order_by("-criado_em", "-id").values("id")[:1]
    )
    return Autorizacao.objects.filter(servico=servico).annotate(atual_id=mais_recente).filter(id=F("atual_id"))


def coletas_do_aluno(servico, aluno):
    """Todas as coletas do aluno, da mais recente para a mais antiga, agrupadas por tipo."""
    coletas = list(
        Autorizacao.objects.filter(servico=servico, aluno=aluno)
        .select_related("colhida_por").order_by("-criado_em", "-id")
    )
    return {codigo: [c for c in coletas if c.tipo == codigo] for codigo in Tipo.values}


def com_tem_coleta(alunos):
    """Anota `tem_<tipo>` em cada aluno: se já existe alguma coleta daquele tipo."""
    return alunos.annotate(**{
        f"tem_{codigo}": Exists(Autorizacao.objects.filter(aluno=OuterRef("pk"), tipo=codigo))
        for codigo in Tipo.values
    })


# ---------------------------------------------------------------- termos

def termo_vigente(servico, tipo):
    return Termo.objects.filter(servico=servico, tipo=tipo, vigente=True).order_by("-versao_do_termo").first()


def termo_usado(termo):
    """Termo com alguma autorização (até pendente) não se edita: só ganha nova versão."""
    return termo.autorizacoes.exists()


# ---------------------------------------------------------------- o que se pode fazer

def pode_colher(atual):
    """Colher de novo: sem coleta, ou a atual pendente, provisória (o sim definitivo), recusada ou revogada."""
    return atual is None or atual.situacao != Situacao.VALIDA


def formas_permitidas(atual):
    """Formas que a tela de colher oferece.

    Com o sim provisório por WhatsApp já registrado, o que falta é o sim definitivo:
    só tablet ou papel (RF-27).
    """
    if atual is not None and atual.situacao == Situacao.PROVISORIA:
        return [Forma.TABLET, Forma.PAPEL]
    return list(FORMAS_DE_COLETA)


def pode_revogar(autorizacao, atual):
    return (
        autorizacao is not None and atual is not None and autorizacao.pk == atual.pk
        and autorizacao.situacao in SITUACOES_QUE_SE_REVOGAM
    )


def assinavel_no_tablet(autorizacao):
    """Só a autorização pendente de forma tablet, com termo, espera a assinatura da família."""
    return (
        autorizacao.situacao == Situacao.PENDENTE and autorizacao.forma == Forma.TABLET
        and autorizacao.termo_id is not None
    )


def primeiro_nome(aluno):
    """O único dado do aluno que aparece no modo assinatura (SEG-08)."""
    partes = (aluno.nome_social or aluno.nome or "").split()
    return partes[0] if partes else ""


def tipo_em_minusculas(codigo):
    rotulo = Tipo(codigo).label
    return rotulo[:1].lower() + rotulo[1:]


# ---------------------------------------------------------------- prova (LGPD-03)

SEPARADOR = b"\x1f"


def momento_iso(momento):
    """Data e hora em ISO 8601, em UTC e sem microssegundos, para a impressão digital."""
    return momento.astimezone(datetime.UTC).replace(microsecond=0).isoformat()


def agora_sem_microssegundos():
    return timezone.now().replace(microsecond=0)


def impressao_digital_do_tablet(*, texto_do_termo, versao_do_termo, nome, documento, decisao, colhida_em,
                                assinatura=b""):
    """SHA-256 da assinatura no tablet (LGPD-03).

    Entram, nesta ordem, cada um seguido do caractere separador 0x1F: o texto do
    termo, a versão do termo, o nome e o documento de quem assinou, a decisão
    ("autorizo" ou "nao_autorizo") e o momento da coleta (ISO 8601, UTC, sem
    microssegundos); por fim, os bytes da imagem PNG da assinatura (vazio quando o
    responsável autorizou em voz alta, sem desenhar). Qualquer mudança em um desses
    dados muda a impressão digital.
    """
    resumo = hashlib.sha256()
    for parte in (texto_do_termo, str(versao_do_termo), nome, documento, decisao, momento_iso(colhida_em)):
        resumo.update((parte or "").encode("utf-8"))
        resumo.update(SEPARADOR)
    resumo.update(assinatura or b"")
    return resumo.hexdigest()


def resumo_do_conteudo(dados):
    return hashlib.sha256(dados).hexdigest()


def _ler(campo_arquivo):
    with campo_arquivo.open("rb") as aberto:
        return aberto.read()


def conferir_impressao_digital(autorizacao):
    """Recalcula a impressão digital e compara com a guardada.

    Devolve True (confere), False (não confere: algo mudou ou o arquivo sumiu) ou
    None (não há o que conferir, como numa autorização pendente).
    """
    if not autorizacao.impressao_digital:
        return None
    try:
        if autorizacao.forma == Forma.TABLET:
            if autorizacao.termo is None or autorizacao.colhida_em is None:
                return False
            assinatura = _ler(autorizacao.assinatura) if autorizacao.assinatura else b""
            decisao = DECISAO_NAO_AUTORIZO if autorizacao.situacao == Situacao.RECUSADA else DECISAO_AUTORIZO
            calculada = impressao_digital_do_tablet(
                texto_do_termo=autorizacao.termo.texto, versao_do_termo=autorizacao.termo.versao_do_termo,
                nome=autorizacao.responsavel_nome, documento=autorizacao.responsavel_documento,
                decisao=decisao, colhida_em=autorizacao.colhida_em, assinatura=assinatura,
            )
        elif autorizacao.arquivo:
            calculada = resumo_do_conteudo(_ler(autorizacao.arquivo))
        else:
            return False
    except (FileNotFoundError, OSError, ValueError):
        return False
    return calculada == autorizacao.impressao_digital


# ---------------------------------------------------------------- assinatura desenhada (SEG-08)

LIMITE_DA_ASSINATURA = 1024 * 1024  # 1 MB
MAIOR_LADO_DA_ASSINATURA = 6000  # px; um tablet com tela densa fica bem abaixo disso
CABECALHO_PNG = b"\x89PNG\r\n\x1a\n"
PREFIXO_DATA_URL = "data:image/png;base64,"
ERRO_DA_ASSINATURA = (
    "A assinatura não chegou inteira. Toque em Limpar, assine de novo no quadro e envie outra vez."
)


def ler_assinatura_png(texto):
    """Confere a assinatura desenhada no quadro e devolve os bytes do PNG.

    Aceita o que o quadro grava (data URL "data:image/png;base64,...") ou só o base64.
    Recusa o que não for base64, não começar com a assinatura de PNG, passar de 1 MB
    ou não abrir no Pillow.
    """
    texto = (texto or "").strip()
    if texto.startswith("data:"):
        if not texto.startswith(PREFIXO_DATA_URL):
            raise ValidationError(ERRO_DA_ASSINATURA, code="assinatura_invalida")
        texto = texto[len(PREFIXO_DATA_URL):]
    if not texto:
        raise ValidationError(ERRO_DA_ASSINATURA, code="assinatura_invalida")
    if len(texto) > (LIMITE_DA_ASSINATURA * 4) // 3 + 4:
        raise ValidationError(
            "A imagem da assinatura ficou grande demais. Toque em Limpar e assine de novo.", code="assinatura_grande"
        )
    try:
        dados = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError) as erro:
        raise ValidationError(ERRO_DA_ASSINATURA, code="assinatura_invalida") from erro
    if len(dados) > LIMITE_DA_ASSINATURA:
        raise ValidationError(
            "A imagem da assinatura ficou grande demais. Toque em Limpar e assine de novo.", code="assinatura_grande"
        )
    if not dados.startswith(CABECALHO_PNG):
        raise ValidationError(ERRO_DA_ASSINATURA, code="assinatura_invalida")
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(dados)) as imagem:
            if imagem.format != "PNG" or max(imagem.size) > MAIOR_LADO_DA_ASSINATURA:
                raise ValidationError(ERRO_DA_ASSINATURA, code="assinatura_invalida")
            imagem.verify()
        with Image.open(io.BytesIO(dados)) as imagem:
            imagem.load()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as erro:
        raise ValidationError(ERRO_DA_ASSINATURA, code="assinatura_invalida") from erro
    return dados


# ---------------------------------------------------------------- conversa do WhatsApp

ERRO_DA_CONVERSA = (
    "Envie a conversa exportada do WhatsApp em texto (.txt), em PDF ou uma foto da tela. "
    "Se o WhatsApp gerou um arquivo .zip, exporte de novo escolhendo “sem mídia”."
)


def validar_conversa(arquivo):
    """Para a conversa do sim por WhatsApp: texto (.txt), PDF ou foto, até o tamanho máximo.

    O tipo é conferido pelo conteúdo: o .txt precisa ser texto de verdade (UTF-8, sem
    bytes nulos); foto e PDF passam por `validar_documento`, que limpa os metadados da foto.
    """
    validar_tamanho(arquivo)
    nome = (getattr(arquivo, "name", "") or "").lower()
    if nome.endswith(".txt"):
        arquivo.seek(0)
        conteudo = arquivo.read()
        arquivo.seek(0)
        if not conteudo or b"\x00" in conteudo:
            raise ValidationError(ERRO_DA_CONVERSA, code="conversa_invalida")
        try:
            conteudo.decode("utf-8-sig")
        except UnicodeDecodeError as erro:
            raise ValidationError(ERRO_DA_CONVERSA, code="conversa_invalida") from erro
        return arquivo
    try:
        return validar_documento(arquivo)
    except ValidationError as erro:
        raise ValidationError(ERRO_DA_CONVERSA, code="conversa_invalida") from erro

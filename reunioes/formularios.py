"""Formulários das reuniões e das citações de alunos (RF-17).

Os formulários são montados por `core.formularios.formulario_para` (só os campos que o
papel edita); as bases daqui acrescentam o filtro por serviço nos campos de escolha
(SEG-05), o título sugerido pelo tipo e as regras de cada cadastro.
"""
import json

from django import forms
from django.utils import timezone

from alunos.models import Aluno
from core.formularios import ModeloFormularioBase
from core.permissoes import NOMES_DE_GRUPO

from .consultas import GRUPO, acesso_de, grupos_visiveis, pessoas_para_escolher
from .models import GRUPOS_DE_CITACAO, Reuniao

SUGESTOES_DE_TITULO = {
    Reuniao.Tipo.SEMANAL: "Reunião semanal da equipe",
    Reuniao.Tipo.MULTIDISCIPLINAR: "Reunião multidisciplinar",
    Reuniao.Tipo.CUIDADOS_PALIATIVOS: "Reunião de cuidados paliativos",
    Reuniao.Tipo.TMO: "Reunião do TMO",
    Reuniao.Tipo.OUTRA: "Reunião",
}

DURACAO_MINIMA, DURACAO_MAXIMA = 5, 720

ESCOLHA_PESSOA_INVALIDA = "Escolha uma pessoa da lista da equipe."
ESCOLHA_PESSOAS_INVALIDA = "Escolha pessoas da lista da equipe."


def titulo_sugerido(tipo):
    return SUGESTOES_DE_TITULO.get(tipo, "Reunião")


def _servico_do_formulario(form):
    """O serviço vem da view; no quadro de conflito (RNF-04), vem do próprio registro."""
    if form.servico is not None:
        return form.servico
    if form.instance.servico_id:
        return form.instance.servico
    return None


def _nome_da_pessoa(pessoa):
    return pessoa.nome or pessoa.email


def com_contexto(form_class, request):
    """Prende o serviço e o acesso da pessoa ao formulário.

    Assim o formulário filtra os campos de escolha mesmo quando é criado sem os
    argumentos da view (o quadro de conflito do núcleo cria o formulário sozinho).
    """
    return type(form_class.__name__, (form_class,), {"servico": request.servico, "acesso": request.acesso})


class FormularioReuniaoBase(ModeloFormularioBase):
    servico = None
    acesso = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        servico = _servico_do_formulario(self)
        if "titulo" in self.fields:
            campo = self.fields["titulo"]
            campo.required = False
            campo.widget.attrs.pop("required", None)
            campo.help_text = "Se ficar em branco, o título é o tipo da reunião, por exemplo “Reunião semanal da equipe”."
            tipo = (self.data.get(self.add_prefix("tipo")) if self.is_bound else None) or self.initial.get("tipo") \
                or self.instance.tipo or Reuniao.Tipo.SEMANAL
            campo.widget.attrs.update({
                "placeholder": titulo_sugerido(tipo),
                "data-sugestao-de": "tipo",
                "data-sugestoes": json.dumps({str(k): v for k, v in SUGESTOES_DE_TITULO.items()}, ensure_ascii=False),
            })
        if "participantes" in self.fields:
            atuais = list(self.instance.participantes.values_list("pk", flat=True)) if self.instance.pk else []
            campo = self.fields["participantes"]
            campo.queryset = pessoas_para_escolher(servico, incluir=atuais)
            campo.label_from_instance = _nome_da_pessoa
            campo.help_text = "Quem participa vê a reunião na própria agenda."
            campo.error_messages["invalid_choice"] = ESCOLHA_PESSOAS_INVALIDA
            campo.error_messages["invalid_pk_value"] = ESCOLHA_PESSOAS_INVALIDA
        if "data" in self.fields:
            self.fields["data"].error_messages["required"] = "Falta a data da reunião. Escolha o dia."
            self.fields["data"].error_messages["invalid"] = "Data incompleta ou errada. Escolha o dia no calendário."
        if "duracao_minutos" in self.fields:
            campo = self.fields["duracao_minutos"]
            campo.help_text = "Por exemplo: 60 para uma hora."
            campo.widget.attrs.update({"min": DURACAO_MINIMA, "max": DURACAO_MAXIMA, "step": 5, "inputmode": "numeric"})
        if "local" in self.fields:
            self.fields["local"].help_text = "Por exemplo: sala da equipe, 4º andar, ou on-line."
        if "pauta" in self.fields:
            self.fields["pauta"].help_text = "Os assuntos combinados para a reunião, um por linha."
        if "ata" in self.fields:
            self.fields["ata"].help_text = (
                "O que foi conversado e decidido. Para ligar um aluno a esta reunião, use “Citar aluno” "
                "na tela da reunião: a citação aparece no perfil dele."
            )

    def clean_duracao_minutos(self):
        duracao = self.cleaned_data.get("duracao_minutos")
        if duracao is not None and not DURACAO_MINIMA <= duracao <= DURACAO_MAXIMA:
            raise forms.ValidationError(
                f"Informe a duração em minutos, entre {DURACAO_MINIMA} e {DURACAO_MAXIMA}. Por exemplo: 60."
            )
        return duracao

    def clean(self):
        dados = super().clean()
        if "titulo" in self.fields and not (dados.get("titulo") or "").strip():
            dados["titulo"] = titulo_sugerido(dados.get("tipo") or self.instance.tipo)
        situacao = dados.get("situacao")
        data = dados.get("data") or self.instance.data
        if situacao == Reuniao.Situacao.REALIZADA and data and data > timezone.localdate():
            self.add_error(
                "situacao",
                "A reunião está marcada para depois de hoje, então ainda não pode estar realizada. "
                "Confira a data ou deixe como marcada.",
            )
        return dados


def _rotulo_do_aluno(aluno):
    rotulo = aluno.nome
    if aluno.situacao != Aluno.Situacao.ATIVO:
        rotulo += f" ({aluno.get_situacao_display().lower()})"
    return rotulo


ROTULOS_DE_GRUPO_DA_CITACAO = {
    "atas": f"{NOMES_DE_GRUPO['atas']}: todos que veem as atas (padrão)",
}


class FormularioCitacaoBase(ModeloFormularioBase):
    servico = None
    acesso = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        servico = _servico_do_formulario(self)
        if "aluno" in self.fields:
            campo = self.fields["aluno"]
            alunos = Aluno.objects.filter(servico=servico) if servico is not None else Aluno.objects.none()
            campo.queryset = alunos.only("id", "nome", "nome_social", "situacao").order_by("nome")
            campo.label_from_instance = _rotulo_do_aluno
            campo.empty_label = "Escolha o aluno"
            campo.error_messages["required"] = "Escolha o aluno de quem a equipe falou."
            campo.error_messages["invalid_choice"] = "Escolha um aluno da lista do serviço."
        if "texto" in self.fields:
            self.fields["texto"].help_text = "Resuma o que a equipe falou sobre o aluno."
            self.fields["texto"].error_messages["required"] = "Escreva o que foi dito sobre o aluno na reunião."
        if "grupo_de_dado" in self.fields:
            campo = self.fields["grupo_de_dado"]
            visiveis = grupos_visiveis(self.acesso) if self.acesso is not None else [c for c, _ in GRUPOS_DE_CITACAO]
            # O padrão (atas) primeiro; depois os tipos mais restritos, na ordem da plataforma.
            ordem = sorted(GRUPOS_DE_CITACAO, key=lambda grupo: grupo[0] != GRUPO)
            campo.choices = [
                (codigo, ROTULOS_DE_GRUPO_DA_CITACAO.get(codigo, nome)) for codigo, nome in ordem if codigo in visiveis
            ]
            campo.help_text = (
                "Quem não vê o tipo escolhido não vê a citação, nem no perfil do aluno. Se a citação fala de saúde "
                "(diagnóstico, tratamento, internação), escolha Saúde e dados sensíveis."
            )
            campo.error_messages["invalid_choice"] = "Escolha um dos tipos de dado da lista."
        if "encaminhamento" in self.fields:
            self.fields["encaminhamento"].help_text = "O que ficou combinado fazer. Deixe em branco se não houve."
            self.fields["encaminhamento"].widget.attrs.setdefault("rows", 3)
        if "responsavel" in self.fields:
            campo = self.fields["responsavel"]
            campo.queryset = pessoas_para_escolher(servico, incluir=[self.instance.responsavel_id], que_veem=GRUPO)
            campo.label_from_instance = _nome_da_pessoa
            campo.empty_label = "Ninguém por enquanto"
            campo.help_text = "Quem cuida do encaminhamento. Na lista, só quem vê as atas pelo papel na equipe."
            campo.error_messages["invalid_choice"] = ESCOLHA_PESSOA_INVALIDA
        if "prazo" in self.fields:
            self.fields["prazo"].help_text = "Até quando o encaminhamento deve estar feito, se houver prazo."

    def clean(self):
        dados = super().clean()
        responsavel = dados.get("responsavel") if "responsavel" in self.fields else self.instance.responsavel
        encaminhamento = (dados.get("encaminhamento") if "encaminhamento" in self.fields
                          else self.instance.encaminhamento) or ""
        prazo = dados.get("prazo") if "prazo" in self.fields else self.instance.prazo
        grupo = dados.get("grupo_de_dado") or self.instance.grupo_de_dado
        if prazo and not responsavel and "responsavel" not in self.errors:
            self.add_error("responsavel", "Escolha quem cuida do encaminhamento, ou deixe o prazo em branco.")
        if responsavel and not encaminhamento.strip() and "encaminhamento" in self.fields:
            self.add_error(
                "encaminhamento", "Escreva o encaminhamento que fica com o responsável, ou tire o responsável."
            )
        if responsavel and grupo:
            acesso = acesso_de(responsavel, _servico_do_formulario(self))
            if not (acesso.pode_ver(GRUPO) and acesso.pode_ver(grupo)):
                self.add_error(
                    "responsavel",
                    f"{responsavel.nome_curto} não vê citações de {NOMES_DE_GRUPO[grupo]} pelo papel na equipe. "
                    "Escolha outra pessoa ou outro tipo de dado.",
                )
        return dados

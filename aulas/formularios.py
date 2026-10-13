"""Formulários do módulo de aulas.

Os formulários de aula são montados por `formulario_da_aula`, que parte de
`core.formularios.formulario_para` (só os campos que o papel pode editar) e
amarra o serviço, o acesso e a pessoa logada na própria classe. Assim a tela de
conflito do núcleo (RNF-04), que cria o formulário de novo sem argumentos
extras, continua filtrando as opções pelo serviço (SEG-05).
"""
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from core.arquivos import validar_foto
from core.formularios import DATA, HORA, FormularioBase, ModeloFormularioBase, formulario_para

from . import regras
from .models import Aula, HabilidadeBNCC

MAXIMO_DE_FOTOS_POR_ENVIO = 10
MINUTOS_MAXIMOS = 480
TIPOS_DE_FOTO = "image/jpeg,image/png,image/webp"

CAMPOS_DE_MARCAR = ["aluno", "professor", "data", "hora_inicio", "duracao_minutos"]
CAMPOS_DO_REGISTRO = CAMPOS_DE_MARCAR + ["componentes", "conteudo", "participacao", "habilidades"]
CAMPOS_DA_NAO_REALIZADA = CAMPOS_DE_MARCAR + ["motivo_nao_realizada"]

WIDGETS_DA_AULA = {
    "data": DATA,
    "hora_inicio": HORA,
    "componentes": forms.CheckboxSelectMultiple,
    "habilidades": forms.CheckboxSelectMultiple,
    "conteudo": forms.Textarea(attrs={"rows": 4}),
    "participacao": forms.Textarea(attrs={"rows": 3}),
    "duracao_minutos": forms.NumberInput(attrs={"inputmode": "numeric", "min": 1, "max": MINUTOS_MAXIMOS, "step": 5}),
}


# ---------------------------------------------------------------- várias fotos de uma vez

class VariasFotosInput(forms.FileInput):
    """Campo de arquivo que aceita várias fotos de uma vez (atributo multiple)."""

    allow_multiple_selected = True

    def __init__(self, attrs=None):
        padrao = {"multiple": True, "accept": TIPOS_DE_FOTO, "data-fotos": str(MAXIMO_DE_FOTOS_POR_ENVIO)}
        padrao.update(attrs or {})
        super().__init__(padrao)


class CampoDeFotos(forms.FileField):
    """Recebe até 10 fotos; cada uma passa por `validar_foto`, que tira o EXIF e reduz o tamanho."""

    widget = VariasFotosInput

    def __init__(self, *args, maximo=MAXIMO_DE_FOTOS_POR_ENVIO, **kwargs):
        self.maximo = maximo
        kwargs.setdefault("error_messages", {
            "required": "Escolha pelo menos uma foto para enviar.",
            "empty": "Uma das fotos veio vazia. Escolha a foto de novo.",
        })
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        arquivos = [a for a in (data if isinstance(data, (list, tuple)) else [data]) if a]
        if not arquivos:
            if self.required:
                raise ValidationError(self.error_messages["required"], code="required")
            return []
        if len(arquivos) > self.maximo:
            raise ValidationError(
                f"Você escolheu {len(arquivos)} fotos. Envie até {self.maximo} por vez; "
                "as outras podem ir depois, em Adicionar fotos.",
                code="muitas_fotos",
            )
        limpas, erros = [], []
        for arquivo in arquivos:
            try:
                limpas.append(validar_foto(super().clean(arquivo, initial)))
            except ValidationError as erro:
                erros.append(f"{arquivo.name}: {' '.join(erro.messages)}")
        if erros:
            raise ValidationError(erros)
        return limpas


# ---------------------------------------------------------------- aula

class AulaFormBase(ModeloFormularioBase):
    """Base dos formulários de aula: opções só do serviço, rótulos e mensagens no tom da plataforma."""

    servico = None
    acesso = None
    usuario = None
    exigir_data_passada = False  # registrar: a aula já aconteceu

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instancia = self.instance if self.instance.pk else None
        if "aluno" in self.fields:
            campo = self.fields["aluno"]
            campo.queryset = regras.alunos_que_recebem_aula(self.servico, instancia.aluno_id if instancia else None)
            campo.label_from_instance = regras.rotulo_do_aluno
            campo.empty_label = "Escolha o aluno"
            campo.help_text = "Alunos ativos e em pausa do serviço."
            campo.error_messages.update({
                "required": "Falta o aluno. Escolha o aluno na lista.",
                "invalid_choice": "Esse aluno não está na lista do serviço. Escolha um aluno da lista.",
            })
        if "professor" in self.fields:
            campo = self.fields["professor"]
            campo.queryset = regras.pessoas_do_servico(self.servico, instancia.professor_id if instancia else None)
            campo.label_from_instance = self._rotulo_da_pessoa
            campo.empty_label = None
            campo.help_text = "Quem deu ou vai dar a aula."
            campo.error_messages.update({
                "required": "Falta quem dá a aula. Escolha uma pessoa da equipe.",
                "invalid_choice": "Essa pessoa não está na equipe do serviço. Escolha alguém da lista.",
            })
        if "data" in self.fields:
            self.fields["data"].error_messages.update({
                "required": "Falta a data da aula. Preencha com o dia do atendimento.",
                "invalid": "Data em formato errado. Use o calendário ou escreva como 13/10/2026.",
            })
        if "hora_inicio" in self.fields:
            self.fields["hora_inicio"].help_text = "Hora em que o atendimento começou ou vai começar."
            self.fields["hora_inicio"].error_messages["invalid"] = "Horário em formato errado. Escreva como 14:30."
        if "duracao_minutos" in self.fields:
            campo = self.fields["duracao_minutos"]
            campo.help_text = (
                f"Cada {regras.minutos_por_aula(self.servico)} minutos contam 1 aula na regra do serviço."
            )
            campo.error_messages.update({
                "required": "Falta quanto tempo durou o atendimento. Preencha em minutos, por exemplo 30.",
                "invalid": "Escreva os minutos só com números, por exemplo 30.",
            })
        if "componentes" in self.fields:
            campo = self.fields["componentes"]
            atuais = list(instancia.componentes.values_list("pk", flat=True)) if instancia else []
            campo.queryset = campo.queryset.model.objects.filter(servico=self.servico).filter(
                Q(ativo=True) | Q(pk__in=atuais)
            ).order_by("nome")
            if not campo.queryset.exists():
                campo.help_text = (
                    "Nenhum componente curricular cadastrado ainda. Quem configura o serviço cadastra em "
                    "Configuração, Componentes curriculares."
                )
        if "habilidades" in self.fields:
            campo = self.fields["habilidades"]
            atuais = list(instancia.habilidades.values_list("pk", flat=True)) if instancia else []
            campo.queryset = HabilidadeBNCC.objects.filter(servico=self.servico).filter(
                Q(ativa=True) | Q(pk__in=atuais)
            ).order_by("codigo")
            campo.label_from_instance = self._rotulo_da_habilidade
            campo.help_text = "Itens da lista da BNCC do serviço trabalhados nesta aula."
        if "motivo_nao_realizada" in self.fields:
            campo = self.fields["motivo_nao_realizada"]
            campo.required = True
            campo.widget.attrs["required"] = True
            campo.error_messages["required"] = (
                "Conte por que a aula não aconteceu, por exemplo “exame no horário” ou “criança dormindo”."
            )

    @staticmethod
    def _rotulo_da_pessoa(pessoa):
        return pessoa.nome or pessoa.email

    @staticmethod
    def _rotulo_da_habilidade(habilidade):
        eixo = f" ({habilidade.eixo})" if habilidade.eixo else ""
        return f"{habilidade.codigo}{eixo}: {habilidade.descricao}"

    def clean_duracao_minutos(self):
        minutos = self.cleaned_data.get("duracao_minutos")
        if minutos is not None and minutos < 1:
            raise ValidationError("Os minutos precisam ser maiores que zero. Preencha quanto tempo durou, por exemplo 30.")
        if minutos is not None and minutos > MINUTOS_MAXIMOS:
            raise ValidationError(
                f"{minutos} minutos passam de 8 horas. Confira o número: um atendimento de 1 hora é 60."
            )
        return minutos

    def clean_data(self):
        data = self.cleaned_data.get("data")
        if data and self.exigir_data_passada and data > regras.hoje():
            raise ValidationError(
                "A data está no futuro. Para combinar uma aula que ainda vai acontecer, use Marcar aula."
            )
        return data


class RegistroDeAulaForm(AulaFormBase):
    """Registrar aula (RF-15): no leito, com o tablet numa mão.

    Aceita o nome de um aluno ainda não cadastrado (RF-19) e várias fotos de uma vez.
    """

    exigir_data_passada = True
    permitir_aluno_novo = True

    aluno_novo = forms.CharField(
        label="Aluno ainda não cadastrado", max_length=150, required=False,
        help_text="Se o aluno ainda não tem cadastro, escreva o nome completo aqui em vez de escolher na lista. "
                  "A plataforma cadastra só com o nome, e completar a ficha vira pendência para quem deu a aula.",
        widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "words"}),
    )
    fotos = CampoDeFotos(
        label="Fotos das atividades", required=False,
        help_text=f"Pode escolher várias de uma vez, até {MAXIMO_DE_FOTOS_POR_ENVIO}. JPG, PNG ou WEBP. "
                  "A plataforma tira a localização e os dados do aparelho de cada foto.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pode_criar_aluno = (
            self.permitir_aluno_novo and not self.instance.pk and self.acesso is not None
            and self.acesso.pode_editar("identificacao") and "aluno" in self.fields
        )
        if not pode_criar_aluno:
            self.fields.pop("aluno_novo", None)
        elif "aluno" in self.fields:
            # Um dos dois basta: o aluno da lista ou o nome do aluno novo.
            self.fields["aluno"].required = False
            self.fields["aluno"].widget.attrs.pop("required", None)
            self.fields["aluno"].help_text = (
                "Alunos ativos e em pausa do serviço. Se o aluno não está na lista, use o campo de baixo."
            )

    def clean_aluno_novo(self):
        return " ".join((self.cleaned_data.get("aluno_novo") or "").split())

    def clean(self):
        dados = super().clean()
        if "aluno_novo" in self.fields and "aluno" in self.fields and "aluno" not in self.errors:
            aluno, novo = dados.get("aluno"), dados.get("aluno_novo")
            if aluno and novo:
                self.add_error(
                    "aluno_novo",
                    "Você escolheu um aluno na lista e também escreveu um nome novo. "
                    "Deixe só um: apague o nome novo ou volte a lista para “Escolha o aluno”.",
                )
            elif not aluno and not novo:
                self.add_error(
                    "aluno",
                    "Falta o aluno. Escolha na lista ou, se ele ainda não tem cadastro, "
                    "escreva o nome em Aluno ainda não cadastrado.",
                )
        return dados


class FotosForm(FormularioBase):
    """Adicionar fotos a uma aula já registrada."""

    fotos = CampoDeFotos(
        label="Fotos das atividades",
        help_text=f"Pode escolher várias de uma vez, até {MAXIMO_DE_FOTOS_POR_ENVIO}. JPG, PNG ou WEBP. "
                  "A plataforma tira a localização e os dados do aparelho de cada foto.",
    )
    legenda = forms.CharField(
        label="Legenda", max_length=200, required=False,
        help_text="Opcional. Vale para todas as fotos deste envio, por exemplo “Cartaz das vogais”.",
    )


def formulario_da_aula(request, campos, *, base=AulaFormBase, edicao=False, **atributos):
    """Formulário de aula só com os campos que o papel pode editar, amarrado ao serviço da pessoa.

    Sem a ação ver_tarefas_de_todos, o campo de professor não entra: a aula fica em nome de quem salva.
    Com a lista da BNCC desligada no serviço, o campo de habilidades não entra (RF-16).
    """
    campos = list(campos)
    if not regras.pode_escolher_professor(request.acesso):
        campos = [c for c in campos if c != "professor"]
    if not request.servico.bncc_ativa:
        campos = [c for c in campos if c != "habilidades"]
    classe = formulario_para(Aula, request.acesso, base=base, campos=campos, edicao=edicao, widgets=WIDGETS_DA_AULA)
    return type(classe.__name__, (classe,), {
        "servico": request.servico, "acesso": request.acesso, "usuario": request.user, **atributos,
    })


# ---------------------------------------------------------------- BNCC (RF-16)

class HabilidadeFormBase(ModeloFormularioBase):
    servico = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "codigo" in self.fields:
            self.fields["codigo"].help_text = "Como na BNCC, por exemplo EF01LP01."
            self.fields["codigo"].error_messages["required"] = "Falta o código. Escreva como na BNCC, por exemplo EF01LP01."
        if "eixo" in self.fields:
            self.fields["eixo"].help_text = "Opcional. Por exemplo: Leitura, Oralidade, Números."
        if "descricao" in self.fields:
            self.fields["descricao"].error_messages["required"] = "Falta a descrição. Copie o texto da habilidade."
            self.fields["descricao"].widget.attrs["rows"] = 3
        if "ativa" in self.fields:
            self.fields["ativa"].help_text = "Só as habilidades ativas aparecem no registro de aula."

    def clean_codigo(self):
        codigo = "".join((self.cleaned_data.get("codigo") or "").split()).upper()
        repetida = HabilidadeBNCC.objects.filter(servico=self.servico, codigo__iexact=codigo)
        if self.instance.pk:
            repetida = repetida.exclude(pk=self.instance.pk)
        if codigo and repetida.exists():
            raise ValidationError(
                f"O código {codigo} já está na lista do serviço. Edite a habilidade que já existe ou confira o código."
            )
        return codigo


def formulario_da_habilidade(request, *, edicao=False):
    classe = formulario_para(
        HabilidadeBNCC, request.acesso, base=HabilidadeFormBase, campos=["codigo", "eixo", "descricao", "ativa"],
        edicao=edicao,
    )
    return type(classe.__name__, (classe,), {"servico": request.servico})

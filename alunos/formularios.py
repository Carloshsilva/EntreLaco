"""Formulários do módulo alunos.

- `FormularioAlunoBase`: base da ficha (cadastrar e editar). Os campos vêm de
  `formulario_para`, conforme o papel (RF-07); só o nome é obrigatório (RF-19).
- `FormularioResponsavelBase`: base do responsável (família).
- `FormularioMudancaDeSituacao`: nova situação, data e motivo (RF-11), e, no
  encerramento, motivo de saída e responsável pela saída (RF-22).
- `FormularioDomiciliar`: o que se decidiu sobre o professor domiciliar (RF-24).
"""
from django import forms
from django.utils import timezone

from core.formularios import DATA, FormularioBase, ModeloFormularioBase

from .consultas import pessoas_do_servico
from .models import Aluno, Responsavel

Situacao = Aluno.Situacao

# Campos de escolha com valor padrão ("Ainda não avaliado", "Não informado"): já vêm marcados e não são obrigatórios.
ESCOLHAS_COM_PADRAO = ["visao", "audicao", "fala", "motricidade", "alfabetizacao", "reprovacao"]

WIDGETS_DO_ALUNO = {
    "data_nascimento": DATA,
    "data_internacao": DATA,
    "nome": forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false"}),
    "nome_social": forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false"}),
    "leito": forms.TextInput(attrs={"autocomplete": "off"}),
    "condicoes_observacoes": forms.Textarea(attrs={"rows": 3}),
    "diagnostico": forms.Textarea(attrs={"rows": 3}),
    "observacoes_saude": forms.Textarea(attrs={"rows": 3}),
}

AJUDAS_DO_ALUNO = {
    "nome": "Como está na certidão ou no documento da criança.",
    "nome_social": "Se a criança prefere outro nome, ele aparece nas listas no lugar do nome completo.",
    "leito": "Por exemplo: 12B.",
    "ra": "Está no boletim ou na declaração de matrícula.",
    "data_internacao": "Atualize a cada nova internação. Conta na ordem de atendimento.",
    "tmo": "Na saída por alta, a equipe vê se a criança precisa de professor domiciliar.",
    "sem_matricula": "Marque se a criança não está matriculada: a orientação pedagógica acompanha até a matrícula.",
    "risco_evasao": "Marque quando a criança corre risco de deixar os estudos. Conta na ordem de atendimento.",
    "risco_evasao_motivo": "Por exemplo: faltou muito antes da internação, a família pensa em tirar da escola.",
}


class FormularioAlunoBase(ModeloFormularioBase):
    """Ficha do aluno. Só o nome é obrigatório: o professor pode cadastrar o mínimo e completar depois (RF-19)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = timezone.localdate().isoformat()
        for nome, ajuda in AJUDAS_DO_ALUNO.items():
            if nome in self.fields:
                self.fields[nome].help_text = ajuda
        if "nome" in self.fields:
            self.fields["nome"].error_messages["required"] = (
                "Falta o nome do aluno. Digite o nome completo; o resto da ficha pode ser completado depois."
            )
        for nome in ESCOLHAS_COM_PADRAO:
            if nome in self.fields:
                self.fields[nome].required = False
                self.fields[nome].widget.attrs.pop("required", None)
        for nome in ("data_nascimento", "data_internacao"):
            if nome in self.fields:
                self.fields[nome].widget.attrs["max"] = hoje
        if "ano_escolar" in self.fields:
            self.fields["ano_escolar"].choices = [("", "Escolha o ano escolar")] + list(Aluno.AnoEscolar.choices)
        if "raca_cor" in self.fields:
            self.fields["raca_cor"].choices = [("", "Não informada")] + list(Aluno.RacaCor.choices)
        if "escola" in self.fields:
            # Busca na base comum de escolas enquanto digita (escolas:buscar); a base pode ter milhares.
            from escolas.formularios import usar_campo_escola

            usar_campo_escola(self, "escola")

    def clean_nome(self):
        return " ".join((self.cleaned_data.get("nome") or "").split())

    def clean_nome_social(self):
        return " ".join((self.cleaned_data.get("nome_social") or "").split())

    def _data_ate_hoje(self, nome, mensagem):
        data = self.cleaned_data.get(nome)
        if data and data > timezone.localdate():
            raise forms.ValidationError(mensagem)
        return data

    def clean_data_nascimento(self):
        return self._data_ate_hoje(
            "data_nascimento", "A data de nascimento não pode ser depois de hoje. Confira o dia, o mês e o ano."
        )

    def clean_data_internacao(self):
        return self._data_ate_hoje(
            "data_internacao", "A data de internação não pode ser depois de hoje. Use a data em que a criança foi internada."
        )

    def clean(self):
        dados = super().clean()
        for nome in ESCOLHAS_COM_PADRAO:
            if nome in self.fields and not dados.get(nome):
                dados[nome] = Aluno._meta.get_field(nome).get_default()
        return dados


class FormularioResponsavelBase(ModeloFormularioBase):
    """Responsável pela criança. Os campos vêm de `formulario_para` (tipo de dado família)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "nome" in self.fields:
            self.fields["nome"].widget.attrs.update({"autocomplete": "off", "spellcheck": "false"})
            self.fields["nome"].error_messages["required"] = "Falta o nome do responsável. Digite o nome completo."
        if "parentesco" in self.fields:
            self.fields["parentesco"].choices = [("", "Escolha o parentesco")] + list(Responsavel.Parentesco.choices)
            self.fields["parentesco"].error_messages["required"] = (
                "Escolha o parentesco. Se não estiver na lista, escolha Outro e explique nas observações."
            )
        if "telefone" in self.fields:
            self.fields["telefone"].widget.input_type = "tel"
            self.fields["telefone"].widget.attrs.update({"inputmode": "tel", "autocomplete": "off"})
            self.fields["telefone"].help_text = "Com DDD, por exemplo (11) 93333-4444."
        if "email" in self.fields:
            self.fields["email"].widget.attrs.update({"autocomplete": "off", "inputmode": "email"})
            self.fields["email"].error_messages["invalid"] = (
                "Confira o e-mail: ele precisa ter @ e o endereço completo, por exemplo familia@exemplo.org."
            )

    def clean_nome(self):
        return " ".join((self.cleaned_data.get("nome") or "").split())

    def clean_telefone(self):
        from escolas.formularios import normalizar_telefone

        return normalizar_telefone(self.cleaned_data.get("telefone"))


class FormularioMudancaDeSituacao(FormularioBase):
    """Mudar a situação do aluno (RF-11, RF-21, RF-22).

    O motivo é sempre obrigatório, inclusive na volta a ativo. Encerrar pede
    também o motivo de saída (da lista do serviço) e o responsável pela saída.
    Com o aluno ativo, "Continua ativo" registra a revisão sem mudar a situação.
    """

    para = forms.ChoiceField(
        label="Nova situação", widget=forms.RadioSelect,
        error_messages={"required": "Escolha a nova situação do aluno.",
                        "invalid_choice": "Escolha uma das situações da lista."},
    )
    data = forms.DateField(
        label="A partir de", widget=DATA,
        help_text="O dia em que a mudança vale. Para encerrar, é a data da saída.",
        error_messages={"required": "Falta a data. Use o dia em que a mudança vale, por exemplo hoje.",
                        "invalid": "Confira a data: use o dia, o mês e o ano."},
    )
    motivo = forms.CharField(
        label="Motivo da mudança", max_length=1000, widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Fica no histórico do aluno, com o seu nome e a data.",
        error_messages={"required": "Conte o motivo da mudança, por exemplo “alta hospitalar” ou “voltou para a "
                                    "internação”. O motivo fica no histórico do aluno."},
    )
    motivo_saida = forms.ChoiceField(
        label="Motivo de saída", required=False, widget=forms.RadioSelect,
        error_messages={"invalid_choice": "Escolha um dos motivos de saída da lista."},
    )
    responsavel = forms.ModelChoiceField(
        label="Responsável pela saída", required=False, queryset=None,
        empty_label="Escolha a pessoa",
        help_text="Quem cuida da saída: avisa a escola e, na alta do TMO, vê se precisa de professor domiciliar.",
        error_messages={"invalid_choice": "Escolha uma pessoa da equipe do serviço."},
    )
    # A situação que a pessoa viu ao abrir o formulário: se outra pessoa mudou no meio, nada é salvo (RNF-04).
    situacao_vista = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, aluno, servico, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.aluno = aluno
        atual = aluno.situacao
        opcoes = []
        if atual == Situacao.ATIVO:
            opcoes.append((Situacao.ATIVO, "Continua ativo"))
        else:
            opcoes.append((Situacao.ATIVO, "Ativo, volta aos atendimentos"))
        if atual != Situacao.PAUSA:
            opcoes.append((Situacao.PAUSA, "Em pausa"))
        if atual != Situacao.ENCERRADO:
            opcoes.append((Situacao.ENCERRADO, "Encerrado, saiu do serviço"))
        self.fields["para"].choices = opcoes
        if atual == Situacao.ATIVO:
            self.fields["para"].help_text = (
                "Escolha “Continua ativo” para registrar a revisão sem mudar a situação."
            )
        self.fields["data"].initial = timezone.localdate()
        self.fields["data"].widget.attrs["max"] = timezone.localdate().isoformat()
        self.fields["motivo_saida"].choices = [(m, m) for m in (servico.motivos_saida or [])]
        self.fields["responsavel"].queryset = pessoas_do_servico(servico)
        if usuario is not None:
            self.fields["responsavel"].initial = usuario.pk
        self.fields["situacao_vista"].initial = atual

    def clean_data(self):
        data = self.cleaned_data.get("data")
        if data and data > timezone.localdate():
            raise forms.ValidationError("A data não pode ser depois de hoje. Use o dia em que a mudança aconteceu.")
        return data

    def clean_motivo(self):
        motivo = (self.cleaned_data.get("motivo") or "").strip()
        if not motivo:
            raise forms.ValidationError(self.fields["motivo"].error_messages["required"])
        return motivo

    def clean(self):
        dados = super().clean()
        if dados.get("para") == Situacao.ENCERRADO:
            if not dados.get("motivo_saida") and "motivo_saida" not in self.errors:
                self.add_error("motivo_saida", "Escolha o motivo de saída para encerrar o aluno.")
            if not dados.get("responsavel") and "responsavel" not in self.errors:
                self.add_error("responsavel", "Escolha a pessoa responsável pela saída para encerrar o aluno.")
        else:
            dados["motivo_saida"] = ""
            dados["responsavel"] = None
        return dados

    @property
    def e_revisao(self):
        """Continua ativo: registra a revisão sem mudar a situação."""
        return self.cleaned_data.get("para") == self.aluno.situacao


class FormularioDomiciliar(FormularioBase):
    """O que se decidiu sobre o professor domiciliar na alta do TMO (RF-24)."""

    observacao = forms.CharField(
        label="O que foi decidido sobre o professor domiciliar", max_length=1000,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Por exemplo: “a família pediu; encaminhado à secretaria de educação em 10/10” ou “não precisa: volta à escola”.",
        error_messages={"required": "Conte o que foi decidido, por exemplo “não precisa: volta à escola”. "
                                    "Fica no histórico do aluno."},
    )

    def clean_observacao(self):
        texto = (self.cleaned_data.get("observacao") or "").strip()
        if not texto:
            raise forms.ValidationError(self.fields["observacao"].error_messages["required"])
        return texto

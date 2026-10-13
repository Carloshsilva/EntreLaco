"""Formulários das escolas e o campo de escola com busca para outros módulos.

- `FormularioEscola`: cadastrar uma escola que ainda não está na base comum (RF-13).
- `FormularioContatoBase`: base do formulário do contato do serviço (RF-14); os
  campos vêm de `formulario_para`, conforme o papel.
- `CampoEscola`: campo de escolha de escola com busca, para outros formulários
  (por exemplo, a escola de origem na ficha do aluno).
"""
import re
from urllib.parse import urlencode

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.html import format_html

from core.formularios import CLASSE_CONTROLE, ModeloFormularioBase

from .consultas import texto_da_escola
from .models import ContatoEscola, Escola

UFS = [
    ("AC", "Acre (AC)"), ("AL", "Alagoas (AL)"), ("AP", "Amapá (AP)"), ("AM", "Amazonas (AM)"),
    ("BA", "Bahia (BA)"), ("CE", "Ceará (CE)"), ("DF", "Distrito Federal (DF)"), ("ES", "Espírito Santo (ES)"),
    ("GO", "Goiás (GO)"), ("MA", "Maranhão (MA)"), ("MT", "Mato Grosso (MT)"), ("MS", "Mato Grosso do Sul (MS)"),
    ("MG", "Minas Gerais (MG)"), ("PA", "Pará (PA)"), ("PB", "Paraíba (PB)"), ("PR", "Paraná (PR)"),
    ("PE", "Pernambuco (PE)"), ("PI", "Piauí (PI)"), ("RJ", "Rio de Janeiro (RJ)"),
    ("RN", "Rio Grande do Norte (RN)"), ("RS", "Rio Grande do Sul (RS)"), ("RO", "Rondônia (RO)"),
    ("RR", "Roraima (RR)"), ("SC", "Santa Catarina (SC)"), ("SP", "São Paulo (SP)"), ("SE", "Sergipe (SE)"),
    ("TO", "Tocantins (TO)"),
]

ERRO_TELEFONE = "Digite o telefone com DDD, por exemplo (11) 3333-4444."


def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def normalizar_telefone(texto):
    """Confere o DDD e escreve no formato (11) 3333-4444 ou (11) 93333-4444. Vazio continua vazio.

    Com ramal ou outro formato longo, o texto fica como a pessoa escreveu.
    """
    texto = " ".join((texto or "").split())
    if not texto:
        return ""
    digitos = so_digitos(texto)
    if len(digitos) < 10:
        raise ValidationError(ERRO_TELEFONE)
    if digitos.startswith("0800") and len(digitos) == 11:
        return f"0800 {digitos[4:7]} {digitos[7:]}"
    if digitos.startswith("0") and len(digitos) in (11, 12):
        digitos = digitos[1:]  # com o 0 do DDD discado: 011 3333-4444
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    return texto


# ---------------------------------------------------------------- cadastrar escola

class FormularioEscola(ModeloFormularioBase):
    """Escola que não está na base: entra na base comum, com a fonte do serviço que cadastrou."""

    # Aceita o código com espaços ou pontos ("1234 5678"); a limpeza deixa só os 8 números.
    codigo_inep = forms.CharField(
        label="Código INEP", max_length=12,
        help_text="8 números. Está no Catálogo de Escolas do INEP ou em documentos da escola.",
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off"}),
        error_messages={"required": "Falta o código INEP. Ele tem 8 números e está no Catálogo de Escolas do INEP."},
    )
    rede = forms.ChoiceField(
        label="Rede", choices=[("", "Escolha a rede")] + list(Escola.Rede.choices),
        error_messages={"required": "Escolha a rede da escola: municipal, estadual, federal ou privada."},
    )
    uf = forms.ChoiceField(
        label="UF", choices=[("", "Escolha a UF")] + UFS,
        error_messages={"required": "Escolha a UF onde fica a escola."},
    )

    class Meta:
        model = Escola
        fields = ["codigo_inep", "nome", "rede", "endereco", "bairro", "municipio", "uf", "cep", "telefone"]
        labels = {
            "nome": "Nome da escola",
            "endereco": "Endereço",
            "municipio": "Município",
            "cep": "CEP",
            "telefone": "Telefone da escola",
        }
        help_texts = {
            "nome": "Como aparece nos documentos da escola, por exemplo: Escola Municipal Inventada.",
            "endereco": "Rua e número.",
            "telefone": "Com DDD. É o telefone público; o contato de quem atende fica no contato do serviço.",
        }
        error_messages = {
            "nome": {"required": "Falta o nome da escola. Digite como aparece nos documentos dela."},
            "municipio": {"required": "Falta o município onde fica a escola."},
        }
        widgets = {
            "nome": forms.TextInput(attrs={"autocomplete": "off"}),
            "endereco": forms.TextInput(attrs={"autocomplete": "off"}),
            "bairro": forms.TextInput(attrs={"autocomplete": "off"}),
            "municipio": forms.TextInput(attrs={"autocomplete": "off"}),
            "cep": forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "maxlength": 9}),
            "telefone": forms.TextInput(attrs={"type": "tel", "inputmode": "tel", "autocomplete": "off"}),
        }

    def clean_codigo_inep(self):
        codigo = so_digitos(self.cleaned_data.get("codigo_inep"))
        if len(codigo) != 8:
            raise ValidationError(
                "O código INEP tem 8 números. Confira no Catálogo de Escolas do INEP ou nos documentos da escola."
            )
        if Escola.objects.filter(codigo_inep=codigo).exists():
            raise ValidationError(
                "Já existe uma escola com este código INEP na base. Busque pelo código na lista de escolas e use a que já está lá."
            )
        return codigo

    def clean_nome(self):
        return " ".join((self.cleaned_data.get("nome") or "").split())

    def clean_municipio(self):
        return " ".join((self.cleaned_data.get("municipio") or "").split())

    def clean_cep(self):
        cep = so_digitos(self.cleaned_data.get("cep"))
        if not cep:
            return ""
        if len(cep) != 8:
            raise ValidationError("O CEP tem 8 números, por exemplo 01234-567. Confira ou deixe em branco.")
        return f"{cep[:5]}-{cep[5:]}"

    def clean_telefone(self):
        return normalizar_telefone(self.cleaned_data.get("telefone"))


# ---------------------------------------------------------------- contato do serviço

class FormularioContatoBase(ModeloFormularioBase):
    """Base do formulário do contato (os campos vêm de `formulario_para`, conforme o papel)."""

    ROTULOS = {
        "email": ("E-mail da escola", "O e-mail que a escola usa para falar com o serviço."),
        "telefone": ("Telefone para contato", "Com DDD. Pode ser o da secretaria ou o direto de quem atende."),
        "observacoes": ("Observações", "Por exemplo: melhor horário para ligar, ramal, outra pessoa que também atende."),
        "situacao": (
            "Situação do contato",
            "Marque Atualizado só depois de conferir os dados com a escola: a confirmação fica com o seu nome e a data de hoje.",
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome, (rotulo, ajuda) in self.ROTULOS.items():
            if nome in self.fields:
                self.fields[nome].label = rotulo
                self.fields[nome].help_text = ajuda
        if "email" in self.fields:
            self.fields["email"].widget.attrs.update({"autocomplete": "off", "inputmode": "email"})
            self.fields["email"].error_messages["invalid"] = (
                "Confira o e-mail: ele precisa ter @ e o endereço completo, por exemplo secretaria@exemplo.org."
            )
        if "telefone" in self.fields:
            self.fields["telefone"].widget.input_type = "tel"
            self.fields["telefone"].widget.attrs.update({"inputmode": "tel", "autocomplete": "off"})
        if "quem_atende" in self.fields:
            self.fields["quem_atende"].label = "Quem atende"
            self.fields["quem_atende"].widget.attrs.update({"autocomplete": "off"})

    def clean_telefone(self):
        return normalizar_telefone(self.cleaned_data.get("telefone"))

    def clean(self):
        dados = super().clean()
        if dados.get("situacao") == ContatoEscola.Situacao.ATUALIZADO:
            email = dados.get("email", getattr(self.instance, "email", ""))
            telefone = dados.get("telefone", getattr(self.instance, "telefone", ""))
            if not email and not telefone and "email" not in self.errors and "telefone" not in self.errors:
                self.add_error(
                    "email" if "email" in self.fields else "situacao",
                    "Para marcar o contato como atualizado, preencha o e-mail ou o telefone da escola. "
                    "Sem eles, deixe como precisa atualizar.",
                )
        return dados


# ---------------------------------------------------------------- campo de escola com busca

class EntradaDeEscola(forms.TextInput):
    """Caixa de texto com sugestões (datalist) que a busca do HTMX preenche enquanto a pessoa digita.

    Sem JavaScript, a pessoa digita o código INEP de 8 números e o campo encontra a escola.
    """

    def __init__(self, attrs=None):
        padrao = {"autocomplete": "off", "spellcheck": "false", "class": CLASSE_CONTROLE}
        padrao.update(attrs or {})
        super().__init__(padrao)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = dict(attrs or {})
        identificador = attrs.get("id") or self.attrs.get("id") or f"id_{name}"
        attrs["id"] = identificador
        lista = f"{identificador}_opcoes"
        url = f"{reverse('escolas:buscar')}?{urlencode({'formato': 'datalist', 'campo': name})}"
        attrs.update({
            "list": lista,
            "hx-get": url,
            "hx-trigger": "input changed delay:300ms",
            "hx-target": f"#{lista}",
            "hx-swap": "innerHTML",
            "hx-sync": "this:replace",
            "hx-push-url": "false",
        })
        campo = super().render(name, value, attrs, renderer)
        return format_html('{}<datalist id="{}"></datalist>', campo, lista)


class CampoEscola(forms.ModelChoiceField):
    """Escolha de uma escola da base comum, com busca por nome, município ou código INEP.

    Uso num formulário de outro módulo (por exemplo, a escola de origem do aluno)::

        from escolas.formularios import usar_campo_escola

        class FormularioDoAluno(ModeloFormularioBase):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                usar_campo_escola(self, "escola")

    `usar_campo_escola` troca o campo só se ele existir (o papel pode não editar a vida
    escolar e, então, o campo nem está no formulário) e mantém rótulo, ajuda e obrigatoriedade.
    Não declare `escola = CampoEscola()` direto na classe de um formulário montado por
    `formulario_para`: campo declarado entra mesmo quando o papel não pode editá-lo.

    Como funciona:
    - o widget é uma caixa de texto com `<datalist>`; enquanto a pessoa digita, o HTMX
      pede `escolas:buscar?formato=datalist&campo=<nome>` e troca as sugestões;
    - cada sugestão é "12345678 · Nome (Município/UF)"; o campo lê o código INEP do
      começo do texto e acha a escola. Sem JavaScript, basta digitar o código INEP;
    - também aceita o número interno (pk) da escola, que é o que a tela de conflito
      de edição devolve no botão "Usar o valor salvo";
    - a escola que não está na base é cadastrada em `escolas:nova` (só quem edita
      contatos das escolas).

    A base é comum a todos os serviços (SEG-05): o campo não precisa filtrar por serviço.
    Para um `<select>` simples com busca, use `escolas:buscar?q=...`, que devolve
    `<option value="<pk>">` (veja `escolas.views.buscar`).
    """

    widget = EntradaDeEscola
    default_error_messages = {
        "invalid_choice": (
            "Não encontramos essa escola. Digite o nome ou o código INEP de 8 números e escolha uma das sugestões. "
            "Se ela não está na base, peça para o apoio administrativo cadastrar a escola."
        ),
    }

    def __init__(self, queryset=None, **kwargs):
        kwargs.setdefault("label", "Escola de origem")
        kwargs.setdefault("help_text", "Digite o nome, o município ou o código INEP e escolha a escola na lista.")
        super().__init__(queryset=queryset if queryset is not None else Escola.objects.all(), **kwargs)

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        if self.required:
            attrs["required"] = True
        return attrs

    def label_from_instance(self, obj):
        return texto_da_escola(obj)

    def prepare_value(self, value):
        if isinstance(value, Escola):
            return texto_da_escola(value)
        if isinstance(value, int) and not isinstance(value, bool):
            escola = self.queryset.filter(pk=value).first()
            return texto_da_escola(escola) if escola else ""
        return value  # texto que a pessoa digitou volta como estava

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, Escola):
            return value
        texto = str(value).strip()
        if not texto:
            return None
        escola = None
        codigo = re.match(r"(\d{8})(?!\d)", texto)
        if codigo:
            escola = self.queryset.filter(codigo_inep=codigo.group(1)).first()
        if escola is None and texto.isdigit():
            escola = self.queryset.filter(pk=int(texto)).first()
        if escola is None:
            raise ValidationError(self.error_messages["invalid_choice"], code="invalid_choice")
        return escola

    def has_changed(self, initial, data):
        if self.disabled:
            return False
        try:
            nova = self.to_python(data)
        except ValidationError:
            return True
        inicial = initial.pk if isinstance(initial, Escola) else initial
        return str(inicial or "") != str(nova.pk if nova else "")


def usar_campo_escola(form, nome="escola", **kwargs):
    """Troca o campo `nome` do formulário por um CampoEscola, se o campo existir. Devolve o campo ou None."""
    atual = form.fields.get(nome)
    if atual is None:
        return None
    kwargs.setdefault("required", atual.required)
    kwargs.setdefault("label", atual.label)
    if atual.help_text:
        kwargs.setdefault("help_text", atual.help_text)
    novo = CampoEscola(**kwargs)
    form.fields[nome] = novo
    return novo

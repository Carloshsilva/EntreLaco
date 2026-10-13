"""Bases de formulário da EntreLaço."""
from django import forms
from django.forms import modelform_factory

from .permissoes import EDITAR, campos_permitidos

CLASSE_CONTROLE = "el-control"


class FormularioBase(forms.Form):
    """Aplica as classes do design system e os atributos de acessibilidade."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        preparar_campos(self)


class ModeloFormularioBase(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        preparar_campos(self)


def preparar_campos(form):
    for campo in form.fields.values():
        widget = campo.widget
        if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect, forms.CheckboxSelectMultiple)):
            classe = "el-check"
        elif isinstance(widget, forms.ClearableFileInput) or isinstance(widget, forms.FileInput):
            classe = "el-control el-control-file"
        elif isinstance(widget, forms.Textarea):
            classe = "el-control el-control-area"
            widget.attrs.setdefault("rows", 4)
        else:
            classe = CLASSE_CONTROLE
        widget.attrs["class"] = (widget.attrs.get("class", "") + " " + classe).strip()
        if isinstance(widget, forms.DateInput):
            widget.input_type = "date"
            widget.format = "%Y-%m-%d"
        if isinstance(widget, forms.TimeInput):
            widget.input_type = "time"
            widget.format = "%H:%M"
        if campo.required:
            widget.attrs["required"] = True


class MotivoDaAlteracaoMixin(forms.Form):
    """Editar um dado já salvo pede o motivo (SEG-03). Cada formulário pode trocar `exemplo_do_motivo`."""

    exemplo_do_motivo = "a família corrigiu o telefone"

    motivo_alteracao = forms.CharField(
        label="Por que você está alterando?",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        motivo = self.fields.get("motivo_alteracao")
        if motivo is not None:
            exemplo = self.exemplo_do_motivo
            motivo.help_text = f"Fica registrado na trilha de auditoria. Exemplo: “{exemplo}”."
            motivo.error_messages["required"] = (
                f"Conte por que você está alterando, por exemplo “{exemplo}”. O motivo fica na trilha de auditoria."
            )


def formulario_para(modelo, acesso, *, base=ModeloFormularioBase, campos=None, edicao=False, widgets=None):
    """Cria um ModelForm só com os campos que a pessoa pode editar (RF-07).

    `campos` restringe e ordena; sem ele, vale a ordem de GRUPOS_DE_CAMPOS.
    Em edição, o formulário ganha o campo obrigatório de motivo.
    """
    permitidos = [
        nome for nome in campos_permitidos(modelo, acesso, EDITAR, campos)
        if modelo._meta.get_field(nome).editable
    ]
    if edicao:
        base = type(f"{base.__name__}ComMotivo", (base, MotivoDaAlteracaoMixin), {})
    return modelform_factory(modelo, form=base, fields=permitidos, widgets=widgets or {})


DATA = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
HORA = forms.TimeInput(format="%H:%M", attrs={"type": "time"})

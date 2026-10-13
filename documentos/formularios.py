"""Formulário dos documentos digitalizados (RF-12).

O arquivo passa por `core.arquivos.validar_documento`: aceita foto (JPG, PNG ou WEBP,
regravada sem os metadados EXIF) ou PDF, conferidos pelo conteúdo e não pela extensão.
"""
import json

from django import forms
from django.utils import timezone

from core.arquivos import validar_documento
from core.formularios import ModeloFormularioBase

from .models import Documento

TIPOS_ACEITOS = "image/*,application/pdf"


def titulo_sugerido(tipo, data=None):
    titulo = Documento.Tipo(tipo).label if tipo in Documento.Tipo.values else "Documento"
    if data:
        titulo += f" de {data:%d/%m/%Y}"
    return titulo


class FormularioDocumentoBase(ModeloFormularioBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "titulo" in self.fields:
            campo = self.fields["titulo"]
            campo.required = False
            campo.widget.attrs.pop("required", None)
            campo.help_text = "Se ficar em branco, o título é o tipo do documento, por exemplo “Ficha de papel assinada”."
            tipo = self.initial.get("tipo") or self.instance.tipo or Documento.Tipo.FICHA_PAPEL
            campo.widget.attrs.update({
                "placeholder": titulo_sugerido(tipo),
                "data-sugestao-de": "tipo",
                "data-sugestoes": json.dumps({tipo.value: tipo.label for tipo in Documento.Tipo}, ensure_ascii=False),
            })
        if "arquivo" in self.fields:
            campo = self.fields["arquivo"]
            campo.label = "Foto ou PDF"
            campo.help_text = (
                "Foto (JPG, PNG ou WEBP) ou PDF, até 10 MB. No celular ou no tablet, você pode tirar a foto na hora. "
                "A foto é guardada sem os dados escondidos do aparelho, como o local."
            )
            campo.error_messages.update({
                "required": "Escolha a foto ou o PDF do documento.",
                "empty": "O arquivo escolhido está vazio. Escolha outro arquivo.",
                "invalid": "Não foi possível ler o arquivo. Escolha a foto ou o PDF de novo.",
            })
        if "data_documento" in self.fields:
            self.fields["data_documento"].help_text = "Quando o papel foi preenchido ou assinado, se souber."
        if "observacoes" in self.fields:
            self.fields["observacoes"].help_text = "Por exemplo: o original em papel está na pasta do aluno, na secretaria."

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get("arquivo")
        if arquivo and "arquivo" in self.files:
            return validar_documento(arquivo)
        return arquivo

    def clean_data_documento(self):
        data = self.cleaned_data.get("data_documento")
        if data and data > timezone.localdate():
            raise forms.ValidationError("A data do documento está depois de hoje. Confira o dia ou deixe em branco.")
        return data

    def clean(self):
        dados = super().clean()
        if "titulo" in self.fields and not (dados.get("titulo") or "").strip():
            tipo = dados.get("tipo") or self.instance.tipo
            dados["titulo"] = titulo_sugerido(tipo, dados.get("data_documento"))
        return dados

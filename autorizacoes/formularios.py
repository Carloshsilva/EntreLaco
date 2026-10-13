"""Formulários das autorizações e dos termos.

Os formulários de coleta não salvam sozinhos: a view decide a situação, a forma e a
prova de cada coleta e grava tudo na mesma transação da trilha de auditoria.
"""
from django import forms

from core.arquivos import validar_documento
from core.formularios import ModeloFormularioBase, MotivoDaAlteracaoMixin, preparar_campos

from . import regras
from .models import Termo

OUTRA_PESSOA = "outra"


def rotulo_do_responsavel(responsavel):
    rotulo = str(responsavel)
    return f"{rotulo} · responsável legal" if responsavel.responsavel_legal else rotulo


class FormularioDeColeta(forms.Form):
    """Quem autorizou: um responsável do aluno (escolhido na lista) ou o nome digitado.

    `responsaveis` já vem filtrado pelo serviço e pelo aluno. Sem nenhum responsável
    na lista (ou quando a pessoa não vê a família), só o nome digitado aparece.
    """

    quem = forms.ChoiceField(label="Quem autorizou", widget=forms.RadioSelect, required=False)
    nome = forms.CharField(
        label="Nome de quem autorizou", max_length=150, required=False,
        help_text="Preencha se a pessoa não está na lista.",
    )
    documento = forms.CharField(
        label="Documento de quem autorizou", max_length=40, required=False,
        help_text="RG ou CPF, como a pessoa informar. Opcional.",
    )

    rotulo_quem = "Quem autorizou"
    rotulo_nome = "Nome de quem autorizou"
    erro_sem_quem = (
        "Escolha quem autorizou. Se a pessoa não está na lista, escolha “Outra pessoa” e digite o nome."
    )
    erro_sem_nome = "Falta o nome de quem autorizou. Digite o nome completo da pessoa."

    def __init__(self, *args, responsaveis=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.responsaveis = {str(r.pk): r for r in responsaveis}
        self.responsavel = None
        if self.responsaveis:
            self.fields["quem"].label = self.rotulo_quem
            self.fields["quem"].required = True
            self.fields["quem"].choices = [(pk, rotulo_do_responsavel(r)) for pk, r in self.responsaveis.items()] + [
                (OUTRA_PESSOA, "Outra pessoa (digite o nome abaixo)")
            ]
            self.fields["quem"].error_messages["required"] = self.erro_sem_quem
            self.fields["nome"].label = self.rotulo_nome
        else:
            del self.fields["quem"]
            self.fields["nome"].label = self.rotulo_nome
            self.fields["nome"].required = True
            self.fields["nome"].help_text = ""
            self.fields["nome"].error_messages["required"] = self.erro_sem_nome
        self.ajustar_campos()
        preparar_campos(self)

    def ajustar_campos(self):
        """Gancho para cada forma mudar rótulos e campos antes das classes serem aplicadas."""

    def clean(self):
        dados = super().clean()
        quem = dados.get("quem")
        if quem and quem != OUTRA_PESSOA:
            self.responsavel = self.responsaveis.get(quem)
            dados["nome"] = self.responsavel.nome
        elif "quem" in self.fields and quem == OUTRA_PESSOA and not (dados.get("nome") or "").strip():
            self.add_error("nome", self.erro_sem_nome)
        return dados


class FormularioPapel(FormularioDeColeta):
    """Papel assinado e fotografado: decisão e a foto do papel (obrigatória)."""

    decisao = forms.ChoiceField(
        label="O que a família decidiu",
        widget=forms.RadioSelect,
        choices=[("autorizou", "Autorizou"), ("nao_autorizou", "Não autorizou")],
        error_messages={"required": "Marque se a família autorizou ou não autorizou, como está no papel."},
    )
    arquivo = forms.FileField(
        label="Foto do papel assinado",
        help_text="Fotografe o termo inteiro, com a assinatura legível. Aceita foto (JPG, PNG ou WEBP) ou PDF, até 10 MB.",
        widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp,application/pdf"}),
        error_messages={"required": "Falta a foto do papel assinado. Fotografe o papel e envie a foto."},
    )
    observacoes = forms.CharField(
        label="Observações", required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_arquivo(self):
        return validar_documento(self.cleaned_data["arquivo"])

    @property
    def autorizou(self):
        return self.cleaned_data.get("decisao") == "autorizou"


class FormularioWhatsapp(FormularioDeColeta):
    """Sim por WhatsApp: a conversa exportada (obrigatória) e uma observação. É provisório (RF-27)."""

    arquivo = forms.FileField(
        label="Conversa exportada do WhatsApp",
        help_text=(
            "No WhatsApp de trabalho, abra a conversa, toque em Mais › Exportar conversa › Sem mídia e envie o "
            "arquivo .txt. Também aceita PDF ou foto da tela, até 10 MB."
        ),
        widget=forms.FileInput(attrs={"accept": ".txt,text/plain,application/pdf,image/jpeg,image/png,image/webp"}),
        error_messages={"required": "Falta a conversa do WhatsApp. Exporte a conversa e envie o arquivo."},
    )
    observacoes = forms.CharField(
        label="Observação", required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Por exemplo: a mãe respondeu “sim, autorizo” às 14h, do número cadastrado.",
    )

    def ajustar_campos(self):
        del self.fields["documento"]

    def clean_arquivo(self):
        return regras.validar_conversa(self.cleaned_data["arquivo"])


class FormularioPendente(forms.Form):
    """A família vai decidir depois: vira pendência de quem registrou (RF-64)."""

    observacoes = forms.CharField(
        label="O que a família disse", required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Opcional. Por exemplo: a mãe quer conversar com o pai antes de decidir.",
    )

    def __init__(self, *args, responsaveis=(), **kwargs):
        super().__init__(*args, **kwargs)
        preparar_campos(self)


class FormularioAssinatura(FormularioDeColeta):
    """O que a família preenche no modo assinatura (SEG-08).

    A assinatura com o dedo é obrigatória para autorizar, a não ser que a pessoa da
    equipe confirme que o responsável não consegue assinar e autorizou em voz alta.
    """

    rotulo_quem = "Quem está assinando"
    rotulo_nome = "Nome completo de quem está assinando"
    erro_sem_quem = "Escolha o seu nome na lista. Se não estiver, escolha “Outra pessoa” e digite o seu nome."
    erro_sem_nome = "Falta o nome de quem está assinando. Digite o seu nome completo."

    decisao = forms.ChoiceField(
        label="Você autoriza?",
        widget=forms.RadioSelect,
        choices=[(regras.DECISAO_AUTORIZO, "Autorizo"), (regras.DECISAO_NAO_AUTORIZO, "Não autorizo")],
        error_messages={"required": "Escolha uma resposta: Autorizo ou Não autorizo."},
    )
    assinatura_dados = forms.CharField(required=False, widget=forms.HiddenInput)
    sem_assinatura_com_o_dedo = forms.BooleanField(
        label=(
            "O responsável não consegue assinar com o dedo; confirmo que ele autorizou em voz alta na minha frente"
        ),
        required=False,
        help_text="Para a pessoa da equipe marcar. Dispensa o desenho e fica registrado na autorização.",
    )

    def ajustar_campos(self):
        self.fields["documento"].label = "Documento (RG ou CPF)"
        self.fields["documento"].help_text = "Opcional."
        if "quem" in self.fields:
            self.fields["nome"].help_text = "Preencha se o seu nome não está na lista."

    def clean(self):
        dados = super().clean()
        self.assinatura_png = b""
        texto = (dados.get("assinatura_dados") or "").strip()
        if texto:
            try:
                self.assinatura_png = regras.ler_assinatura_png(texto)
            except forms.ValidationError as erro:
                self.add_error("assinatura_dados", erro)
                return dados
        autoriza = dados.get("decisao") == regras.DECISAO_AUTORIZO
        if autoriza and not self.assinatura_png and not dados.get("sem_assinatura_com_o_dedo"):
            self.add_error(
                "assinatura_dados",
                "Falta a assinatura. Assine com o dedo dentro do quadro. Se não conseguir, peça à pessoa da equipe "
                "para marcar a caixa abaixo do quadro.",
            )
        return dados

    @property
    def autoriza(self):
        return self.cleaned_data.get("decisao") == regras.DECISAO_AUTORIZO


class FormularioRevogacao(forms.Form):
    """Revogação a pedido da família (RF-29, LGPD-04)."""

    revogacao_motivo = forms.CharField(
        label="Como a família pediu a revogação",
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Quem pediu, quando e por onde. Por exemplo: a mãe pediu por telefone hoje, às 10h.",
        error_messages={"required": "Conte como a família pediu a revogação: quem pediu, quando e por onde."},
    )
    confirmar = forms.BooleanField(
        label="Confirmo que a família pediu para revogar esta autorização",
        error_messages={"required": "Marque a confirmação para registrar a revogação."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        preparar_campos(self)


# ---------------------------------------------------------------- termos

class FormularioTermo(ModeloFormularioBase):
    """Nova versão de um termo. O texto definitivo é do advogado (LGPD-02)."""

    class Meta:
        model = Termo
        fields = ["tipo", "titulo", "texto"]
        labels = {"tipo": "Tipo de autorização", "titulo": "Título", "texto": "Texto do termo"}
        help_texts = {
            "titulo": "Aparece no alto da tela de assinatura. Por exemplo: Autorização para uso dos dados.",
            "texto": (
                "Cole aqui o texto escrito ou revisado pelo advogado. Enquanto ele não chega, use um texto "
                "provisório e diga isso no próprio texto."
            ),
        }
        widgets = {"tipo": forms.RadioSelect, "texto": forms.Textarea(attrs={"rows": 14})}
        error_messages = {
            "tipo": {"required": "Escolha o tipo de autorização deste termo."},
            "titulo": {"required": "Falta o título do termo. Ele aparece no alto da tela de assinatura."},
            "texto": {"required": "Falta o texto do termo. Cole o texto que a família vai ler."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "tipo" in self.fields:
            self.fields["tipo"].choices = [c for c in self.fields["tipo"].choices if c[0]]


class FormularioTermoEdicao(FormularioTermo, MotivoDaAlteracaoMixin):
    """Corrigir um termo que ainda não foi usado em nenhuma autorização."""

    exemplo_do_motivo = "corrigi um erro de digitação"

    class Meta(FormularioTermo.Meta):
        fields = ["titulo", "texto"]

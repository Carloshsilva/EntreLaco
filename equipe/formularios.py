"""Formulários da equipe: pessoas, perfil de professor, papéis, componentes e configuração do serviço.

Os formulários de pessoa, papel e configuração mexem em cadastros do núcleo que não herdam
ModeloDoServico (Usuario, Vinculo, Papel, Servico). Por isso não usam `formulario_para` e
dizem, cada um, como ler os valores salvos e os enviados no mesmo formato legível da trilha
(`valores_legiveis`), para registrar o antes e o depois e para detectar conflito de edição.
"""
import re

from django import forms
from django.db.models import Q

from core.formularios import FormularioBase, ModeloFormularioBase, MotivoDaAlteracaoMixin, preparar_campos
from core.models import Papel, Vinculo
from core.permissoes import ACOES, CODIGOS_DE_ACAO, GRUPOS_DE_DADOS, NENHUM, NIVEIS, nivel_valido

from .models import ComponenteCurricular, PerfilProfessor

NOMES_DOS_NIVEIS = dict(NIVEIS)
NOMES_DAS_ACOES = dict(ACOES)
LIMITE_DE_MOTIVOS = 30
TAMANHO_DO_MOTIVO = 80


class TelefoneInput(forms.TextInput):
    input_type = "tel"


# Grupos de opções cujo `id_for_label` aponta para a primeira opção, para o link do resumo de
# erros (core/_erros_do_formulario.html) levar ao grupo em vez de "#". O nome da classe é o
# mesmo do Django de propósito: `widget_type` continua "radioselect"/"checkboxselectmultiple",
# e core/_campo.html segue desenhando o grupo com fieldset e legend.
class RadioSelect(forms.RadioSelect):
    def id_for_label(self, id_, index=None):
        return super().id_for_label(id_, "0" if index is None else index)


class CheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    def id_for_label(self, id_, index=None):
        return super().id_for_label(id_, "0" if index is None else index)


class CampoPapel(forms.ModelChoiceField):
    """Escolha de papel mostrando só o nome (o __str__ do papel repete o serviço)."""

    def label_from_instance(self, papel):
        return papel.nome


def papeis_que_pode_dar(servico, acesso):
    """Papéis do serviço que a pessoa logada pode dar a alguém.

    Papel que configura o serviço só é dado por quem também configura: quem só cuida da
    equipe não consegue, assim, dar a alguém mais permissão do que tem (RF-03, RF-04).
    """
    papeis = Papel.objects.filter(servico=servico).order_by("nome")
    if not acesso.configurar:
        papeis = papeis.exclude(pode_configurar=True)
    return papeis


def limpar_whatsapp(valor):
    valor = " ".join((valor or "").split())
    if not valor:
        return ""
    digitos = re.sub(r"\D", "", valor)
    if not re.fullmatch(r"[\d\s()+\-.]+", valor) or not 10 <= len(digitos) <= 13:
        raise forms.ValidationError(
            "Digite o WhatsApp com DDD, usando números, espaços, parênteses ou traço. Exemplo: (11) 98765-4321."
        )
    return valor


AJUDA_WHATSAPP = "Com DDD. Fica guardado para quando o envio por WhatsApp chegar; nesta versão, nada é enviado por ele."
ERROS_DO_NOME = {"required": "Falta o nome. Digite o nome completo da pessoa."}
ERROS_DO_PAPEL = {
    "required": "Falta o papel. Escolha o que a pessoa vai fazer no serviço.",
    "invalid_choice": "Esse papel não está disponível para você dar. Escolha um papel da lista.",
}


# ---------------------------------------------------------------- pessoas

class PessoaNovaForm(FormularioBase):
    email = forms.EmailField(
        label="E-mail de acesso", max_length=254,
        help_text="A pessoa entra na EntreLaço com este e-mail e recebe nele o link para criar a senha.",
        error_messages={
            "required": "Falta o e-mail. Digite o e-mail que a pessoa vai usar para entrar.",
            "invalid": "Confira o e-mail: ele precisa ter @ e um domínio, como nome@exemplo.org.",
        },
        widget=forms.EmailInput(attrs={"autocomplete": "off"}),
    )
    nome = forms.CharField(label="Nome completo", max_length=150, error_messages=ERROS_DO_NOME)
    whatsapp_trabalho = forms.CharField(
        label="WhatsApp de trabalho", max_length=20, required=False, help_text=AJUDA_WHATSAPP,
        widget=TelefoneInput(attrs={"autocomplete": "off"}),
    )
    papel = CampoPapel(
        label="Papel no serviço", queryset=Papel.objects.none(), empty_label="Escolha o papel",
        help_text="O papel define o que a pessoa vê e edita.", error_messages=ERROS_DO_PAPEL,
    )

    def __init__(self, *args, servico, acesso, **kwargs):
        super().__init__(*args, **kwargs)
        self.servico = servico
        self.fields["papel"].queryset = papeis_que_pode_dar(servico, acesso)
        if not acesso.configurar:
            self.fields["papel"].help_text += " Papéis que configuram o serviço só podem ser dados por quem configura."

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        vinculo = Vinculo.objects.filter(servico=self.servico, usuario__email__iexact=email).first()
        if vinculo is not None and vinculo.ativo:
            raise forms.ValidationError(
                "Essa pessoa já está na equipe. Procure o nome dela na lista para mudar os dados ou o papel."
            )
        if vinculo is not None:
            raise forms.ValidationError(
                "Essa pessoa já fez parte da equipe e está com o acesso desativado. "
                "Procure o nome dela na lista, com a situação “Desativadas”, e reative o acesso."
            )
        return email

    def clean_nome(self):
        return " ".join(self.cleaned_data["nome"].split())

    def clean_whatsapp_trabalho(self):
        return limpar_whatsapp(self.cleaned_data.get("whatsapp_trabalho"))


class PessoaEditarForm(FormularioBase, MotivoDaAlteracaoMixin):
    field_order = ["nome", "whatsapp_trabalho", "papel", "motivo_alteracao"]

    nome = forms.CharField(label="Nome completo", max_length=150, error_messages=ERROS_DO_NOME)
    whatsapp_trabalho = forms.CharField(
        label="WhatsApp de trabalho", max_length=20, required=False, help_text=AJUDA_WHATSAPP,
        widget=TelefoneInput(attrs={"autocomplete": "off"}),
    )
    papel = CampoPapel(
        label="Papel no serviço", queryset=Papel.objects.none(), empty_label="Escolha o papel",
        help_text="O papel define o que a pessoa vê e edita.", error_messages=ERROS_DO_PAPEL,
    )

    def __init__(self, *args, servico, acesso, a_si_mesmo=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["papel"].queryset = papeis_que_pode_dar(servico, acesso)
        if a_si_mesmo:
            # Ninguém muda o próprio papel: nem para ganhar permissão, nem para perder o acesso sem querer.
            self.fields["papel"].disabled = True
            self.fields["papel"].help_text = "Você não muda o próprio papel. Se precisar, peça a outra pessoa que cuida da equipe."
            self.fields["papel"].queryset = Papel.objects.filter(servico=servico)
        elif not acesso.configurar:
            self.fields["papel"].help_text += " Papéis que configuram o serviço só podem ser dados por quem configura."

    def clean_nome(self):
        return " ".join(self.cleaned_data["nome"].split())

    def clean_whatsapp_trabalho(self):
        return limpar_whatsapp(self.cleaned_data.get("whatsapp_trabalho"))

    @staticmethod
    def valores_salvos(vinculo):
        return {
            "nome": vinculo.usuario.nome,
            "whatsapp_trabalho": vinculo.usuario.whatsapp_trabalho,
            "papel": vinculo.papel.nome,
        }

    @staticmethod
    def valores_brutos(vinculo):
        return {
            "nome": vinculo.usuario.nome,
            "whatsapp_trabalho": vinculo.usuario.whatsapp_trabalho,
            "papel": vinculo.papel_id,
        }

    def valores_legiveis(self):
        dados = self.cleaned_data
        return {"nome": dados["nome"], "whatsapp_trabalho": dados["whatsapp_trabalho"], "papel": dados["papel"].nome}


class DesativarForm(FormularioBase):
    motivo = forms.CharField(
        label="Por que você está desativando o acesso?", max_length=500,
        help_text="Fica registrado na trilha de auditoria. Exemplo: “saiu do serviço no fim do mês”.",
        error_messages={"required": "Falta o motivo. Escreva em poucas palavras por que o acesso vai ser desativado."},
        widget=forms.Textarea(attrs={"rows": 2}),
    )


# ---------------------------------------------------------------- perfil de professor

class PerfilProfessorForm(ModeloFormularioBase):
    servico = None  # definido pela view (formulario_do_professor)

    class Meta:
        model = PerfilProfessor
        fields = ["componentes", "educacao_infantil", "anos_iniciais", "anos_finais", "ensino_medio", "eja", "observacoes"]
        widgets = {"componentes": CheckboxSelectMultiple}
        help_texts = {
            "componentes": "Marque os componentes curriculares que a pessoa ensina.",
            "observacoes": "Exemplo: dias e turnos em que atende, formação, línguas que fala.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        filtro = Q(ativo=True)
        if self.instance.pk:
            # Componente desativado depois continua marcado em quem já o tinha.
            filtro |= Q(pk__in=self.instance.componentes.values("pk"))
        campo = self.fields["componentes"]
        campo.queryset = ComponenteCurricular.objects.filter(servico=self.servico).filter(filtro).order_by("nome")
        if not campo.queryset.exists():
            campo.help_text = (
                "Nenhum componente curricular cadastrado ainda. Quem configura o serviço cadastra em "
                "Configuração, Componentes curriculares."
            )


def formulario_do_professor(servico, edicao=False):
    bases = (PerfilProfessorForm, MotivoDaAlteracaoMixin) if edicao else (PerfilProfessorForm,)
    return type("PerfilProfessorDoServico", bases, {"servico": servico})


# ---------------------------------------------------------------- componentes curriculares

class ComponenteForm(ModeloFormularioBase):
    servico = None  # definido pela view (formulario_de_componente)

    class Meta:
        model = ComponenteCurricular
        fields = ["nome", "ativo"]
        labels = {"nome": "Nome do componente", "ativo": "Ativo"}
        help_texts = {
            "nome": "Exemplo: Matemática, Língua Portuguesa, Arte.",
            "ativo": "Componente inativo não aparece para escolher em perfis e aulas novas; o que já foi registrado continua.",
        }
        error_messages = {"nome": {"required": "Falta o nome do componente."}}

    def clean_nome(self):
        nome = " ".join(self.cleaned_data["nome"].split())
        repetidos = ComponenteCurricular.objects.filter(servico=self.servico, nome__iexact=nome)
        if self.instance.pk:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise forms.ValidationError("Já existe um componente com esse nome. Use outro nome ou edite o que já existe.")
        return nome


def formulario_de_componente(servico, edicao=False):
    bases = (ComponenteForm, MotivoDaAlteracaoMixin) if edicao else (ComponenteForm,)
    return type("ComponenteDoServico", bases, {"servico": servico})


# ---------------------------------------------------------------- papéis

def _campo_de_acesso(nome, ajuda):
    return forms.ChoiceField(
        label=nome, help_text=ajuda, choices=NIVEIS, widget=RadioSelect,
        error_messages={"required": f"Falta escolher o acesso a “{nome}”: não vê, vê ou vê e edita."},
    )


class PapelForm(forms.Form):
    """Papel com a grade "tipo de dado × não vê / vê / vê e edita" e as ações (RF-06, RF-07).

    A permissão de configurar o serviço não está no formulário: só o administrador da
    plataforma libera (RF-03). Mesmo que o envio traga esse campo, ele é ignorado.
    """

    nome = forms.CharField(
        label="Nome do papel", max_length=80, help_text="Exemplo: Professor, Supervisão, Apoio administrativo.",
        error_messages={"required": "Falta o nome do papel."},
    )
    descricao = forms.CharField(
        label="Descrição", max_length=255, required=False,
        help_text="Uma frase sobre quem tem este papel. Aparece na lista de papéis.",
    )
    acoes = forms.MultipleChoiceField(
        label="Ações que este papel pode fazer", choices=ACOES, required=False, widget=CheckboxSelectMultiple,
    )

    def __init__(self, *args, servico, papel=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.servico = servico
        self.papel = papel
        for codigo, nome, ajuda in GRUPOS_DE_DADOS:
            self.fields[f"acesso_{codigo}"] = _campo_de_acesso(nome, ajuda)
        if papel is not None:
            self.initial.setdefault("nome", papel.nome)
            self.initial.setdefault("descricao", papel.descricao)
            self.initial.setdefault("acoes", [a for a in (papel.acoes or []) if a in CODIGOS_DE_ACAO])
        for codigo, _, _ in GRUPOS_DE_DADOS:
            nivel = nivel_valido((papel.acessos or {}).get(codigo, NENHUM)) if papel is not None else NENHUM
            self.initial.setdefault(f"acesso_{codigo}", nivel)
        self.order_fields(["nome", "descricao", *self.nomes_de_acesso(), "acoes", "motivo_alteracao"])
        preparar_campos(self)

    @staticmethod
    def nomes_de_acesso():
        return [f"acesso_{codigo}" for codigo, _, _ in GRUPOS_DE_DADOS]

    def campos_de_acesso(self):
        return [self[nome] for nome in self.nomes_de_acesso()]

    def clean_nome(self):
        nome = " ".join(self.cleaned_data["nome"].split())
        repetidos = Papel.objects.filter(servico=self.servico, nome__iexact=nome)
        if self.papel is not None:
            repetidos = repetidos.exclude(pk=self.papel.pk)
        if repetidos.exists():
            raise forms.ValidationError("Já existe um papel com esse nome neste serviço. Escolha outro nome.")
        return nome

    @staticmethod
    def _acoes_legiveis(codigos):
        nomes = [NOMES_DAS_ACOES[c] for c in CODIGOS_DE_ACAO if c in codigos]
        return "; ".join(nomes) if nomes else "Nenhuma"

    @classmethod
    def valores_salvos(cls, papel):
        valores = {"nome": papel.nome, "descricao": papel.descricao}
        for codigo, _, _ in GRUPOS_DE_DADOS:
            valores[f"acesso_{codigo}"] = NOMES_DOS_NIVEIS[nivel_valido((papel.acessos or {}).get(codigo, NENHUM))]
        valores["acoes"] = cls._acoes_legiveis(papel.acoes or [])
        return valores

    @staticmethod
    def valores_brutos(papel):
        valores = {"nome": papel.nome, "descricao": papel.descricao}
        for codigo, _, _ in GRUPOS_DE_DADOS:
            valores[f"acesso_{codigo}"] = nivel_valido((papel.acessos or {}).get(codigo, NENHUM))
        valores["acoes"] = [a for a in CODIGOS_DE_ACAO if a in (papel.acoes or [])]
        return valores

    def valores_legiveis(self):
        dados = self.cleaned_data
        valores = {"nome": dados["nome"], "descricao": dados["descricao"]}
        for codigo, _, _ in GRUPOS_DE_DADOS:
            valores[f"acesso_{codigo}"] = NOMES_DOS_NIVEIS[dados[f"acesso_{codigo}"]]
        valores["acoes"] = self._acoes_legiveis(dados["acoes"])
        return valores

    def aplicar(self, papel):
        """Passa o que foi enviado para o papel. `pode_configurar` nunca muda aqui."""
        dados = self.cleaned_data
        papel.servico = self.servico
        papel.nome = dados["nome"]
        papel.descricao = dados["descricao"]
        papel.acessos = {codigo: dados[f"acesso_{codigo}"] for codigo, _, _ in GRUPOS_DE_DADOS}
        papel.acoes = [a for a in CODIGOS_DE_ACAO if a in dados["acoes"]]
        return papel


class PapelEditarForm(PapelForm, MotivoDaAlteracaoMixin):
    pass


# ---------------------------------------------------------------- configuração do serviço

class ConfiguracaoForm(FormularioBase, MotivoDaAlteracaoMixin):
    """Parâmetros do serviço que existem nesta versão (RF-62)."""

    field_order = ["minutos_por_aula", "bncc_ativa", "prazo_revisao_ativo_dias", "motivos_saida", "motivo_alteracao"]

    minutos_por_aula = forms.IntegerField(
        label="Minutos de atendimento que contam 1 aula", min_value=5, max_value=240,
        help_text="Regra de equivalência. Exemplo: com 30, um atendimento de 60 minutos conta 2 aulas.",
        error_messages={
            "required": "Falta o número de minutos. Digite quantos minutos de atendimento contam 1 aula.",
            "invalid": "Digite só números. Exemplo: 30.",
            "min_value": "Use pelo menos 5 minutos.",
            "max_value": "Use no máximo 240 minutos (4 horas).",
        },
        widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
    )
    bncc_ativa = forms.BooleanField(
        label="Usar a lista da BNCC no registro de aula", required=False,
        help_text="Mostra os eixos e as habilidades da BNCC para escolher ao registrar a aula.",
    )
    prazo_revisao_ativo_dias = forms.IntegerField(
        label="Prazo da revisão de aluno ativo, em dias", min_value=1, max_value=365,
        help_text="Aluno sem aula registrada ou marcada nesse prazo entra em revisão.",
        error_messages={
            "required": "Falta o prazo. Digite em quantos dias sem aula o aluno entra em revisão.",
            "invalid": "Digite só números. Exemplo: 21.",
            "min_value": "Use pelo menos 1 dia.",
            "max_value": "Use no máximo 365 dias.",
        },
        widget=forms.NumberInput(attrs={"inputmode": "numeric"}),
    )
    motivos_saida = forms.CharField(
        label="Motivos de saída", widget=forms.Textarea(attrs={"rows": 6}),
        help_text=(
            "Um motivo por linha. São as opções ao encerrar o atendimento de um aluno. "
            "Tirar um motivo da lista não muda as saídas já registradas."
        ),
        error_messages={"required": "Escreva ao menos um motivo de saída, um por linha."},
    )

    def clean_motivos_saida(self):
        motivos = []
        vistos = set()
        for linha in self.cleaned_data["motivos_saida"].splitlines():
            motivo = " ".join(linha.split())
            if motivo and motivo.casefold() not in vistos:
                vistos.add(motivo.casefold())
                motivos.append(motivo)
        if not motivos:
            raise forms.ValidationError("Escreva ao menos um motivo de saída, um por linha.")
        longo = next((m for m in motivos if len(m) > TAMANHO_DO_MOTIVO), None)
        if longo:
            raise forms.ValidationError(
                f"Cada motivo pode ter até {TAMANHO_DO_MOTIVO} caracteres. Encurte o motivo que começa com “{longo[:30]}”."
            )
        if len(motivos) > LIMITE_DE_MOTIVOS:
            raise forms.ValidationError(f"Use no máximo {LIMITE_DE_MOTIVOS} motivos. Junte os parecidos.")
        return motivos

    @staticmethod
    def valores_salvos(servico):
        return {
            "minutos_por_aula": str(servico.minutos_por_aula),
            "bncc_ativa": "Sim" if servico.bncc_ativa else "Não",
            "prazo_revisao_ativo_dias": str(servico.prazo_revisao_ativo_dias),
            "motivos_saida": "; ".join(servico.motivos_saida or []),
        }

    @staticmethod
    def valores_brutos(servico):
        return {
            "minutos_por_aula": servico.minutos_por_aula,
            "bncc_ativa": servico.bncc_ativa,
            "prazo_revisao_ativo_dias": servico.prazo_revisao_ativo_dias,
            "motivos_saida": "\n".join(servico.motivos_saida or []),
        }

    def valores_legiveis(self):
        dados = self.cleaned_data
        return {
            "minutos_por_aula": str(dados["minutos_por_aula"]),
            "bncc_ativa": "Sim" if dados["bncc_ativa"] else "Não",
            "prazo_revisao_ativo_dias": str(dados["prazo_revisao_ativo_dias"]),
            "motivos_saida": "; ".join(dados["motivos_saida"]),
        }

    def aplicar(self, servico):
        dados = self.cleaned_data
        servico.minutos_por_aula = dados["minutos_por_aula"]
        servico.bncc_ativa = dados["bncc_ativa"]
        servico.prazo_revisao_ativo_dias = dados["prazo_revisao_ativo_dias"]
        servico.motivos_saida = list(dados["motivos_saida"])
        return servico

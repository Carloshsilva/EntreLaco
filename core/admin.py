"""Painel da plataforma: só o administrador (superusuário) cadastra serviços,
liga módulos, cria papéis e libera a permissão de configurar (RF-01 a RF-04).

O resto do trabalho do serviço acontece nas telas da própria plataforma.
Liberar ou tirar permissões fica na trilha de auditoria (RF-03, SEG-04).
"""
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from . import auditoria
from .models import EventoAuditoria, Papel, Servico, Usuario, Vinculo
from .permissoes import ACOES, GRUPOS_DE_DADOS, NIVEIS


class SoAdministradorMixin:
    """Só o administrador da plataforma usa o painel."""

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request, *args):
        return request.user.is_active and request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser


@admin.register(Servico)
class ServicoAdmin(SoAdministradorMixin, admin.ModelAdmin):
    list_display = ["nome", "slug", "ativo", "criado_em"]
    prepopulated_fields = {"slug": ["nome"]}
    search_fields = ["nome"]


class PapelForm(forms.ModelForm):
    """Edita os acessos por tipo de dado como uma lista de escolhas, não como JSON."""

    acoes_liberadas = forms.MultipleChoiceField(
        label="Ações liberadas", choices=ACOES, required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Papel
        fields = ["servico", "nome", "descricao", "pode_configurar"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        acessos = (self.instance.acessos or {}) if self.instance.pk else {}
        for codigo, nome, ajuda in GRUPOS_DE_DADOS:
            self.fields[f"acesso_{codigo}"] = forms.ChoiceField(
                label=nome, help_text=ajuda, choices=NIVEIS, initial=acessos.get(codigo, "nenhum")
            )
        self.fields["acoes_liberadas"].initial = list(self.instance.acoes or []) if self.instance.pk else []

    def save(self, commit=True):
        papel = super().save(commit=False)
        papel.acessos = {codigo: self.cleaned_data[f"acesso_{codigo}"] for codigo, _, _ in GRUPOS_DE_DADOS}
        papel.acoes = list(self.cleaned_data["acoes_liberadas"])
        if commit:
            papel.save()
        return papel


@admin.register(Papel)
class PapelAdmin(SoAdministradorMixin, admin.ModelAdmin):
    form = PapelForm
    list_display = ["nome", "servico", "pode_configurar"]
    list_filter = ["servico", "pode_configurar"]

    def get_fieldsets(self, request, obj=None):
        grupos = [f"acesso_{codigo}" for codigo, _, _ in GRUPOS_DE_DADOS]
        return [
            (None, {"fields": ["servico", "nome", "descricao"]}),
            ("O que vê e edita, por tipo de dado", {"fields": grupos}),
            ("Ações", {"fields": ["acoes_liberadas", "pode_configurar"]}),
        ]

    def save_model(self, request, obj, form, change):
        antes = {}
        if change:
            original = Papel.objects.get(pk=obj.pk)
            antes = {"acessos": original.acessos, "acoes": sorted(original.acoes or []),
                     "pode_configurar": original.pode_configurar}
        super().save_model(request, obj, form, change)
        depois = {"acessos": obj.acessos, "acoes": sorted(obj.acoes or []), "pode_configurar": obj.pode_configurar}
        mudancas = {
            chave: {"rotulo": chave.replace("_", " "), "grupo": None, "de": str(antes.get(chave, "")),
                    "para": str(valor)}
            for chave, valor in depois.items() if antes.get(chave) != valor
        }
        if mudancas:
            auditoria.registrar(
                request, EventoAuditoria.Acao.LIBEROU_PERMISSAO, obj, mudancas=mudancas, servico=obj.servico,
                descricao=f"Permissões do papel {obj.nome} definidas pelo administrador da plataforma",
            )


@admin.register(Vinculo)
class VinculoAdmin(SoAdministradorMixin, admin.ModelAdmin):
    list_display = ["usuario", "servico", "papel", "ativo"]
    list_filter = ["servico", "papel", "ativo"]
    search_fields = ["usuario__nome", "usuario__email"]
    autocomplete_fields = ["usuario"]

    def save_model(self, request, obj, form, change):
        papel_antes = Vinculo.objects.get(pk=obj.pk).papel if change else None
        super().save_model(request, obj, form, change)
        if papel_antes != obj.papel:
            auditoria.registrar(
                request, EventoAuditoria.Acao.MUDOU_PAPEL, obj, servico=obj.servico,
                mudancas={"papel": {"rotulo": "papel", "grupo": None, "de": str(papel_antes or ""),
                                    "para": str(obj.papel)}},
                descricao=f"Papel de {obj.usuario} definido pelo administrador da plataforma",
            )


@admin.register(Usuario)
class UsuarioAdmin(SoAdministradorMixin, UserAdmin):
    ordering = ["nome"]
    list_display = ["nome", "email", "is_active", "is_superuser", "totp_ativo"]
    list_filter = ["is_active", "is_superuser", "totp_ativo"]
    search_fields = ["nome", "email"]
    readonly_fields = ["last_login", "date_joined"]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Dados", {"fields": ["nome", "whatsapp_trabalho"]}),
        ("Acesso", {"fields": ["is_active", "is_staff", "is_superuser", "totp_ativo"]}),
        ("Datas", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [(None, {"classes": ["wide"], "fields": ["email", "nome", "password1", "password2"]})]
    filter_horizontal = []

    def save_model(self, request, obj, form, change):
        # Desligar a verificação em duas etapas (troca de celular) apaga o segredo antigo.
        if change and not obj.totp_ativo:
            obj.totp_segredo = ""
        super().save_model(request, obj, form, change)


@admin.register(EventoAuditoria)
class EventoAuditoriaAdmin(SoAdministradorMixin, admin.ModelAdmin):
    """Só leitura: a trilha não se edita nem se apaga."""

    list_display = ["criado_em", "servico", "usuario_nome", "acao", "objeto_repr", "ip"]
    list_filter = ["acao", "servico"]
    search_fields = ["usuario_nome", "objeto_repr", "descricao"]
    date_hierarchy = "criado_em"

    def has_add_permission(self, request, *args):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

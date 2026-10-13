"""Telas do núcleo: entrar e sair, verificação em duas etapas, início, agenda e trilha."""
import base64
import datetime

import pyotp
import segno
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST

from . import auditoria
from .formularios import FormularioBase, preparar_campos
from .middleware import CHAVE_SERVICO, precisa_duas_etapas
from .models import EventoAuditoria, Vinculo
from .registro import eventos_da_agenda, pendencias_para

CHAVE_USUARIO_PENDENTE = "entrar_usuario_pendente"
CHAVE_SEGREDO_NOVO = "duas_etapas_segredo_novo"
NOME_DO_EMISSOR = "EntreLaço"


# ---------------------------------------------------------------- entrar e sair

class EntrarForm(FormularioBase):
    email = forms.EmailField(label="E-mail", widget=forms.EmailInput(attrs={"autocomplete": "username", "autofocus": True}))
    senha = forms.CharField(label="Senha", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class CodigoForm(FormularioBase):
    codigo = forms.CharField(
        label="Código de 6 números",
        max_length=6, min_length=6,
        help_text="Abra o aplicativo autenticador no seu celular e digite o código da EntreLaço.",
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "pattern": "[0-9]{6}"}),
    )

    def clean_codigo(self):
        codigo = self.cleaned_data["codigo"].strip().replace(" ", "")
        if not codigo.isdigit():
            raise forms.ValidationError("O código tem só números.")
        return codigo


def _ip(request):
    return auditoria._ip(request)


def _bloqueado(email, request):
    """Muitas tentativas erradas no mesmo e-mail ou do mesmo endereço bloqueiam por um tempo."""
    desde = timezone.now() - datetime.timedelta(minutes=settings.LOGIN_BLOQUEIO_MINUTOS)
    falhas = EventoAuditoria.objects.filter(acao=EventoAuditoria.Acao.FALHOU_LOGIN, criado_em__gte=desde)
    por_email = falhas.filter(objeto_repr=email).count()
    ip = _ip(request)
    por_ip = falhas.filter(ip=ip).count() if ip else 0
    return por_email >= settings.LOGIN_TENTATIVAS or por_ip >= settings.LOGIN_TENTATIVAS * 3


def _registrar_falha(request, email, motivo):
    usuario = get_user_model().objects.filter(email__iexact=email).first()
    EventoAuditoria.objects.create(
        usuario=usuario,
        usuario_nome=usuario.nome if usuario else "",
        acao=EventoAuditoria.Acao.FALHOU_LOGIN,
        modelo="core.Usuario",
        objeto_id=str(usuario.pk) if usuario else "",
        objeto_repr=email,
        descricao=motivo,
        ip=_ip(request),
    )


def _destino(request):
    proximo = request.POST.get("next") or request.GET.get("next") or ""
    if proximo and url_has_allowed_host_and_scheme(proximo, allowed_hosts={request.get_host()},
                                                   require_https=request.is_secure()):
        return proximo
    return reverse(settings.LOGIN_REDIRECT_URL)


def _concluir_entrada(request, usuario):
    login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
    vinculo = (
        Vinculo.objects.filter(usuario=usuario, ativo=True, servico__ativo=True)
        .select_related("servico").order_by("servico__nome").first()
    )
    auditoria.registrar(
        request, EventoAuditoria.Acao.ENTROU, usuario=usuario, descricao="Entrou na plataforma",
        servico=vinculo.servico if vinculo else None,
    )


@sensitive_post_parameters("senha")
@csrf_protect
@never_cache
def entrar(request):
    if request.user.is_authenticated:
        return redirect(_destino(request))
    form = EntrarForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        if _bloqueado(email, request):
            form.add_error(None, f"Muitas tentativas erradas. Espere {settings.LOGIN_BLOQUEIO_MINUTOS} minutos e tente de novo, ou peça para redefinir a senha.")
        else:
            usuario = authenticate(request, username=email, password=form.cleaned_data["senha"])
            if usuario is None:
                _registrar_falha(request, email, "E-mail ou senha errados")
                form.add_error(None, "E-mail ou senha não conferem. Confira e tente de novo.")
            elif usuario.totp_ativo:
                request.session[CHAVE_USUARIO_PENDENTE] = usuario.pk
                proximo = request.POST.get("next", "")
                url = reverse("entrar_codigo")
                return redirect(f"{url}?next={proximo}" if proximo else url)
            else:
                _concluir_entrada(request, usuario)
                return redirect(_destino(request))
    contexto = {"form": form, "next": request.GET.get("next", ""), "assinatura_ok": request.GET.get("assinatura") == "ok"}
    return render(request, "core/entrar.html", contexto)


@csrf_protect
@never_cache
def entrar_codigo(request):
    usuario_id = request.session.get(CHAVE_USUARIO_PENDENTE)
    usuario = get_user_model().objects.filter(pk=usuario_id, is_active=True).first() if usuario_id else None
    if usuario is None or not usuario.totp_ativo:
        return redirect("entrar")
    form = CodigoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _bloqueado(usuario.email, request):
            form.add_error(None, f"Muitas tentativas erradas. Espere {settings.LOGIN_BLOQUEIO_MINUTOS} minutos e tente de novo.")
        elif pyotp.TOTP(usuario.totp_segredo).verify(form.cleaned_data["codigo"], valid_window=1):
            del request.session[CHAVE_USUARIO_PENDENTE]
            _concluir_entrada(request, usuario)
            return redirect(_destino(request))
        else:
            _registrar_falha(request, usuario.email, "Código de verificação errado")
            form.add_error("codigo", "Código errado ou vencido. Digite o código que aparece agora no aplicativo.")
    return render(request, "core/entrar_codigo.html", {"form": form, "next": request.GET.get("next", "")})


@require_POST
def sair(request):
    if request.user.is_authenticated:
        auditoria.registrar(request, EventoAuditoria.Acao.SAIU, usuario=request.user, descricao="Saiu da plataforma")
    logout(request)
    messages.info(request, "Você saiu. Até a próxima.")
    return redirect("entrar")


# ---------------------------------------------------------------- conta

@login_required
@never_cache
def minha_conta(request):
    vinculos = Vinculo.objects.filter(usuario=request.user, ativo=True).select_related("servico", "papel")
    return render(request, "core/minha_conta.html", {
        "vinculos": vinculos,
        "precisa_duas_etapas": precisa_duas_etapas(request.user),
    })


class TrocarSenhaForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Senha atual"
        self.fields["new_password1"].label = "Nova senha"
        self.fields["new_password2"].label = "Repita a nova senha"
        self.fields["new_password1"].help_text = "Pelo menos 10 caracteres, sem ser só números nem parecida com seu nome ou e-mail."
        preparar_campos(self)


@sensitive_post_parameters()
@login_required
@never_cache
def trocar_senha(request):
    form = TrocarSenhaForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        update_session_auth_hash(request, usuario)
        auditoria.registrar(request, EventoAuditoria.Acao.OUTRO, usuario=usuario, descricao="Trocou a própria senha")
        messages.success(request, "Senha trocada.")
        return redirect("minha_conta")
    return render(request, "core/trocar_senha.html", {"form": form})


def _qr_em_data_uri(texto):
    qr = segno.make(texto, error="m")
    svg = qr.svg_inline(scale=5, dark="#16201D", light="#FFFFFF", border=2)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


@login_required
@never_cache
def duas_etapas(request):
    """Ativar a verificação em duas etapas com um aplicativo autenticador (SEG-07)."""
    usuario = request.user
    if usuario.totp_ativo:
        return render(request, "core/duas_etapas.html", {"ativa": True})
    segredo = request.session.get(CHAVE_SEGREDO_NOVO)
    if not segredo:
        segredo = pyotp.random_base32()
        request.session[CHAVE_SEGREDO_NOVO] = segredo
    form = CodigoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if pyotp.TOTP(segredo).verify(form.cleaned_data["codigo"], valid_window=1):
            usuario.totp_segredo = segredo
            usuario.totp_ativo = True
            usuario.save(update_fields=["totp_segredo", "totp_ativo"])
            del request.session[CHAVE_SEGREDO_NOVO]
            auditoria.registrar(request, EventoAuditoria.Acao.OUTRO, usuario=usuario,
                                descricao="Ativou a verificação em duas etapas")
            messages.success(request, "Verificação em duas etapas ativada. A partir de agora, a plataforma pede o código ao entrar.")
            return redirect("inicio")
        form.add_error("codigo", "O código não confere. Confira se o relógio do celular está certo e digite o código que aparece agora.")
    uri = pyotp.TOTP(segredo).provisioning_uri(name=usuario.email, issuer_name=NOME_DO_EMISSOR)
    return render(request, "core/duas_etapas.html", {
        "ativa": False,
        "form": form,
        "qr": _qr_em_data_uri(uri),
        "segredo": " ".join(segredo[i:i + 4] for i in range(0, len(segredo), 4)),
        "obrigatoria": precisa_duas_etapas(usuario),
    })


class PedirLinkDeSenhaForm(PasswordResetForm):
    """Também atende quem foi cadastrado e ainda não criou a senha (o primeiro link pode ter vencido)."""

    def get_users(self, email):
        usuarios = get_user_model()._default_manager.filter(
            email__iexact=email, is_active=True, vinculos__ativo=True, vinculos__servico__ativo=True,
        ).distinct()
        return (u for u in usuarios if _iequal(u.email, email))


def _iequal(a, b):
    return (a or "").casefold() == (b or "").casefold()


class RedefinirSenhaView(auth_views.PasswordResetView):
    form_class = PedirLinkDeSenhaForm
    template_name = "core/senha/pedir.html"
    email_template_name = "core/senha/email.txt"
    subject_template_name = "core/senha/assunto.txt"
    success_url = reverse_lazy("senha_pedido_enviado")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["email"].label = "Seu e-mail de acesso"
        preparar_campos(form)
        return form


class DefinirSenhaView(auth_views.PasswordResetConfirmView):
    template_name = "core/senha/definir.html"
    success_url = reverse_lazy("senha_definida")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        if form is not None:
            form.fields["new_password1"].label = "Nova senha"
            form.fields["new_password2"].label = "Repita a nova senha"
            form.fields["new_password1"].help_text = "Pelo menos 10 caracteres, sem ser só números nem parecida com seu nome ou e-mail."
            preparar_campos(form)
        return form

    def form_valid(self, form):
        resposta = super().form_valid(form)
        auditoria.registrar(self.request, EventoAuditoria.Acao.OUTRO, usuario=form.user,
                            descricao="Definiu a senha pelo link enviado por e-mail")
        return resposta


# ---------------------------------------------------------------- serviço

@login_required
@require_POST
def trocar_servico(request):
    servico_id = request.POST.get("servico")
    vinculo = Vinculo.objects.filter(usuario=request.user, ativo=True, servico__ativo=True, servico_id=servico_id).first()
    if vinculo is None:
        raise PermissionDenied("Você não tem vínculo com esse serviço.")
    request.session[CHAVE_SERVICO] = vinculo.servico_id
    messages.success(request, f"Agora você está em {vinculo.servico.nome}.")
    return redirect("inicio")


# ---------------------------------------------------------------- início

@login_required
@never_cache
def inicio(request):
    """Tela inicial igual para todos: as pendências de cada um e, para quem dá aula, as aulas marcadas (RF-43)."""
    if request.servico is None:
        return render(request, "core/sem_vinculo.html", status=403)
    pode_ver_todas = request.acesso.tem("ver_tarefas_de_todos")
    todas = pode_ver_todas and request.GET.get("ver") == "todas"
    pendencias = pendencias_para(request, todas=todas)
    hoje = timezone.localdate()
    proximos = [
        evento for evento in eventos_da_agenda(request, hoje, hoje + datetime.timedelta(days=6), usuario=request.user)
        if not evento.cancelado
    ]
    return render(request, "core/inicio.html", {
        "pendencias": pendencias,
        "vencidas": sum(1 for p in pendencias if p.situacao_do_prazo == "vencida"),
        "de_hoje": sum(1 for p in pendencias if p.situacao_do_prazo == "hoje"),
        "todas": todas,
        "pode_ver_todas": pode_ver_todas,
        "eventos_de_hoje": [e for e in proximos if e.data == hoje],
        "proximos_eventos": [e for e in proximos if e.data > hoje],
        "hoje": hoje,
    })


# ---------------------------------------------------------------- agenda

NOMES_DOS_DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


@login_required
@never_cache
def agenda(request):
    """Agenda da semana: aulas e reuniões, de uma pessoa ou de todo o serviço (RF-09, RF-44)."""
    if request.servico is None:
        return render(request, "core/sem_vinculo.html", status=403)
    hoje = timezone.localdate()
    try:
        referencia = datetime.date.fromisoformat(request.GET.get("semana", ""))
    except ValueError:
        referencia = hoje
    inicio_semana = referencia - datetime.timedelta(days=referencia.weekday())
    fim_semana = inicio_semana + datetime.timedelta(days=6)

    pessoas = list(
        get_user_model().objects.filter(vinculos__servico=request.servico, vinculos__ativo=True, is_active=True)
        .order_by("nome")
    )
    escolha = request.GET.get("pessoa", "")
    if escolha == "todos":
        pessoa = None
    else:
        pessoa = next((p for p in pessoas if str(p.pk) == escolha), request.user)

    eventos = eventos_da_agenda(request, inicio_semana, fim_semana, usuario=pessoa)
    dias = []
    for deslocamento in range(7):
        dia = inicio_semana + datetime.timedelta(days=deslocamento)
        dias.append({
            "data": dia,
            "nome": NOMES_DOS_DIAS[dia.weekday()],
            "hoje": dia == hoje,
            "eventos": [e for e in eventos if e.data == dia],
        })
    return render(request, "core/agenda.html", {
        "dias": dias,
        "inicio_semana": inicio_semana,
        "fim_semana": fim_semana,
        "semana_anterior": (inicio_semana - datetime.timedelta(days=7)).isoformat(),
        "semana_seguinte": (inicio_semana + datetime.timedelta(days=7)).isoformat(),
        "esta_semana": inicio_semana <= hoje <= fim_semana,
        "pessoas": pessoas,
        "pessoa": pessoa,
        "escolha": "todos" if pessoa is None else str(pessoa.pk),
        "total": len(eventos),
    })


# ---------------------------------------------------------------- trilha de auditoria

@login_required
@never_cache
def trilha(request):
    """Trilha de auditoria do serviço (SEG-03, SEG-04), para quem tem a ação ver_trilha."""
    if request.servico is None:
        return render(request, "core/sem_vinculo.html", status=403)
    if not request.acesso.tem("ver_trilha"):
        raise PermissionDenied("Seu papel não permite ver a trilha de auditoria.")
    eventos = EventoAuditoria.objects.filter(servico=request.servico)
    pessoa = request.GET.get("pessoa", "")
    acao = request.GET.get("acao", "")
    if pessoa.isdigit():
        eventos = eventos.filter(usuario_id=int(pessoa))
    if acao in EventoAuditoria.Acao.values:
        eventos = eventos.filter(acao=acao)
    eventos = auditoria.filtrar_visiveis(eventos, request.acesso)
    pagina = Paginator(eventos, 50).get_page(request.GET.get("pagina"))
    pagina.object_list = auditoria.preparar_para_exibir(list(pagina.object_list), request.acesso)
    pessoas = get_user_model().objects.filter(vinculos__servico=request.servico).order_by("nome").distinct()
    return render(request, "core/trilha.html", {
        "pagina": pagina,
        "pessoas": pessoas,
        "acoes": EventoAuditoria.Acao.choices,
        "pessoa": pessoa,
        "acao": acao,
    })


def eventos_do_objeto(request, obj, limite=20):
    """Histórico de um registro, para mostrar na própria tela dele (SEG-03).

    Mostra a quem vê o registro; mudanças em tipos de dado que a pessoa não vê ficam de fora.
    """
    eventos = list(
        EventoAuditoria.objects.filter(servico=request.servico, modelo=obj._meta.label, objeto_id=str(obj.pk))[:limite]
    )
    return auditoria.preparar_para_exibir(eventos, request.acesso)


def eventos_do_aluno(request, aluno_id, limite=30):
    """Tudo o que aconteceu com um aluno, em qualquer cadastro ligado a ele."""
    eventos = EventoAuditoria.objects.filter(servico=request.servico, aluno_id=aluno_id)
    eventos = auditoria.filtrar_visiveis(eventos, request.acesso)
    return auditoria.preparar_para_exibir(list(eventos[:limite]), request.acesso)


# ---------------------------------------------------------------- erros

def erro_403(request, exception=None):
    return render(request, "403.html", {"motivo": str(exception) if exception else ""}, status=403)


def erro_404(request, exception=None):
    return render(request, "404.html", status=404)


def erro_500(request):
    # Sem processadores de contexto: o erro pode ter vindo do próprio banco.
    from django.http import HttpResponseServerError
    from django.template import loader

    return HttpResponseServerError(loader.get_template("500.html").render())


def redirecionar_login_do_admin(request):
    """O painel da plataforma usa o mesmo login, com verificação em duas etapas."""
    proximo = request.GET.get("next", reverse("admin:index"))
    return HttpResponseRedirect(f"{reverse('entrar')}?next={proximo}")


@login_required
def em_construcao(request, *args, **kwargs):
    """Marcador para telas ainda não feitas; cada app troca pelo seu."""
    return render(request, "core/em_construcao.html", status=200)

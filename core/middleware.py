from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from .models import Vinculo
from .permissoes import ACESSO_VAZIO, Acesso

CHAVE_SERVICO = "servico_id"
# Guarda a URL da tela de assinatura enquanto a família assina no tablet (SEG-08).
CHAVE_MODO_ASSINATURA = "modo_assinatura_url"


def _vinculo_atual(request):
    usuario = request.user
    if not usuario.is_authenticated:
        return None
    vinculos = list(
        Vinculo.objects.filter(usuario=usuario, ativo=True, servico__ativo=True)
        .select_related("servico", "papel")
        .order_by("servico__nome")
    )
    if not vinculos:
        return None
    escolhido = request.session.get(CHAVE_SERVICO)
    for vinculo in vinculos:
        if vinculo.servico_id == escolhido:
            return vinculo
    request.session[CHAVE_SERVICO] = vinculos[0].servico_id
    return vinculos[0]


class ServicoMiddleware:
    """Define request.servico, request.vinculo e request.acesso para a pessoa logada.

    Todo dado de serviço é filtrado por request.servico (SEG-05).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        vinculo = _vinculo_atual(request)
        request.vinculo = vinculo
        request.servico = vinculo.servico if vinculo else None
        request.acesso = Acesso.do_papel(vinculo.papel) if vinculo else ACESSO_VAZIO
        return self.get_response(request)


def precisa_duas_etapas(usuario):
    """Administrador da plataforma e quem configura um serviço usam verificação em duas etapas (SEG-07)."""
    if not getattr(settings, "EXIGIR_DUAS_ETAPAS", True) or not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    return Vinculo.objects.filter(usuario=usuario, ativo=True, papel__pode_configurar=True).exists()


def _e_estatico(caminho):
    return caminho.startswith("/" + settings.STATIC_URL.lstrip("/")) or caminho == "/favicon.ico"


class DuasEtapasMiddleware:
    """Quem precisa de verificação em duas etapas e ainda não ativou só vê a tela de ativação."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if usuario is not None and usuario.is_authenticated and not usuario.totp_ativo:
            permitidas = {reverse("duas_etapas"), reverse("sair")}
            if request.path not in permitidas and not _e_estatico(request.path) and precisa_duas_etapas(usuario):
                return redirect("duas_etapas")
        return self.get_response(request)


class ModoAssinaturaMiddleware:
    """No modo assinatura, o tablet só mostra o termo (SEG-08).

    Enquanto a sessão estiver nesse modo, qualquer outro endereço volta para a
    tela do termo. Ao terminar ou cancelar, a tela de assinatura encerra a
    sessão e o professor entra de novo.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        url = request.session.get(CHAVE_MODO_ASSINATURA) if hasattr(request, "session") else None
        if url and not _e_estatico(request.path) and not request.path.startswith(url):
            return redirect(url)
        return self.get_response(request)


class CabecalhosDeSegurancaMiddleware:
    """Cabeçalhos que valem para toda resposta.

    - Páginas de quem está logado não ficam no cache do navegador, para que o
      botão voltar não mostre dados de aluno depois de sair (SEG-09).
    - Política de conteúdo: só scripts, estilos e fontes do próprio site.
    """

    POLITICA = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        "font-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; "
        "base-uri 'self'; object-src 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.POLITICA)
        response.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            response["Cache-Control"] = "no-store, max-age=0"
            response["Pragma"] = "no-cache"
        return response

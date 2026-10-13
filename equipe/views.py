"""Telas da equipe: pessoas do serviço, papel, acesso, link de senha e perfil de professor.

RF-05 (cada pessoa com login próprio), RF-09 (professor), RF-48 (WhatsApp de trabalho, sem envio),
SEG-04 (papel e permissão na trilha), SEG-09 (desativar encerra as sessões).

A pessoa é um `core.Usuario`, comum a todos os serviços; o que é deste serviço é o `core.Vinculo`
(papel e se o acesso está ativo). Toda tela parte do vínculo com `request.servico`: pessoa sem
vínculo com o serviço dá 404.
"""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.functional import cached_property
from django.utils.http import urlsafe_base64_encode
from django.views import View
from django.views.generic import CreateView, FormView, TemplateView, UpdateView

from core import auditoria
from core.models import EventoAuditoria, Papel, Vinculo
from core.views_base import AcessoMixin, CriarComAuditoriaMixin, EditarComAuditoriaMixin

from .edicao import EdicaoSemVersaoMixin
from .formularios import DesativarForm, PessoaEditarForm, PessoaNovaForm, formulario_do_professor
from .models import PerfilProfessor

Usuario = get_user_model()
Acao = auditoria.Acao
logger = logging.getLogger(__name__)

# O link de senha fica na sessão só até a tela da pessoa abrir uma vez.
CHAVE_DO_LINK = "equipe_link_senha"

SITUACOES = [("ativas", "Com acesso"), ("desativadas", "Desativadas"), ("todas", "Todas")]
PESSOAS_POR_PAGINA = 50


# ---------------------------------------------------------------- regras

def pode_gerir(request, vinculo):
    """Quem cuida da equipe mexe no cadastro de outra pessoa do serviço, com dois limites:
    só quem configura mexe em quem configura (RF-03, RF-04), e ninguém do serviço mexe no
    administrador da plataforma."""
    acesso = request.acesso
    if not acesso.tem("gerir_equipe"):
        return False
    if vinculo.papel.pode_configurar and not acesso.configurar:
        return False
    if vinculo.usuario.is_superuser and not request.user.is_superuser:
        return False
    return True


def tem_outro_servico(usuario, servico):
    return Vinculo.objects.filter(usuario=usuario).exclude(servico=servico).exists()


def pode_mandar_link(request, vinculo):
    """Quem cuida da equipe manda um link de senha para outra pessoa do serviço com acesso ativo."""
    usuario = vinculo.usuario
    return (
        pode_gerir(request, vinculo)
        and usuario.pk != request.user.pk
        and vinculo.ativo
        and usuario.is_active
    )


def link_na_tela(usuario, outro_servico):
    """Se o link de senha pode aparecer na tela de quem cuida da equipe.

    Quem vê o link consegue criar a senha no lugar da pessoa e entrar como ela. Por isso o link
    só aparece na tela, para ser mandado pelo WhatsApp de trabalho, quando a pessoa ainda não
    criou a senha e é só deste serviço. Para quem já tem senha (RF-05: cada ação aponta uma
    pessoa), para quem também trabalha em outro serviço (SEG-05) e para quem acessa o painel
    da plataforma, o link vai só para o e-mail da própria pessoa.
    """
    return not (
        usuario.has_usable_password() or outro_servico or usuario.is_staff or usuario.is_superuser
    )


def por_que_so_por_email(usuario, outro_servico):
    """Frase para a tela da pessoa quando o link vai só para o e-mail dela."""
    if usuario.has_usable_password():
        return "Ela já criou a senha, então o link vai só para o e-mail dela."
    if outro_servico:
        return "Ela também trabalha em outro serviço, então o link vai só para o e-mail dela."
    return "O link vai só para o e-mail dela."


def gerar_link_de_senha(request, usuario):
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    return request.build_absolute_uri(reverse("senha_definir", kwargs={"uidb64": uid, "token": token}))


def horas_de_validade():
    return max(1, settings.PASSWORD_RESET_TIMEOUT // 3600)


def mandar_link_por_email(request, usuario, link, novo):
    """Tenta mandar o link por e-mail e diz se deu certo (nada é enviado por WhatsApp nesta versão, RF-48)."""
    contexto = {
        "pessoa": usuario,
        "quem": request.user,
        "servico": request.servico,
        "link": link,
        "novo": novo,
        "horas": horas_de_validade(),
    }
    assunto = " ".join(render_to_string("equipe/email/link_senha_assunto.txt", contexto).split())
    corpo = render_to_string("equipe/email/link_senha.txt", contexto)
    try:
        send_mail(assunto, corpo, None, [usuario.email])
    except Exception:  # noqa: BLE001 - qualquer falha do servidor de e-mail
        logger.warning("Não foi possível mandar por e-mail o link de senha da pessoa %s.", usuario.pk, exc_info=True)
        return False
    return True


def entregar_link(request, usuario, novo, na_tela):
    """Gera o link, tenta o e-mail e registra na trilha.

    Com `na_tela`, também guarda o link na sessão para a tela da pessoa mostrar uma única vez.
    """
    link = gerar_link_de_senha(request, usuario)
    enviado = mandar_link_por_email(request, usuario, link, novo)
    if na_tela:
        request.session[CHAVE_DO_LINK] = {"usuario": usuario.pk, "link": link, "email_enviado": enviado}
        descricao = "Gerou um novo link para criar a senha" if novo else "Gerou o link para criar a senha"
        descricao += " e mandou por e-mail" if enviado else "; o e-mail não foi enviado"
    elif enviado:
        descricao = "Mandou por e-mail um link para criar a senha"
    else:
        descricao = "Tentou mandar por e-mail um link para criar a senha; o e-mail não foi enviado"
    auditoria.registrar(request, Acao.OUTRO, usuario, servico=request.servico, descricao=descricao)
    return enviado


def encerrar_sessoes(usuario):
    """Apaga as sessões abertas da pessoa (SEG-09).

    Com `is_active` falso ela já não passaria do login, mas assim nada fica guardado no servidor.
    """
    if settings.SESSION_ENGINE != "django.contrib.sessions.backends.db":
        return
    for sessao in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if sessao.get_decoded().get("_auth_user_id") == str(usuario.pk):
            sessao.delete()


def eventos_da_pessoa(request, vinculo, perfil=None, limite=30):
    """Histórico da pessoa neste serviço: cadastro, papel, acesso, link de senha e perfil de professor."""
    filtro = Q(modelo=Usuario._meta.label, objeto_id=str(vinculo.usuario_id)) | Q(
        modelo=Vinculo._meta.label, objeto_id=str(vinculo.pk)
    )
    if perfil is not None:
        filtro |= Q(modelo=PerfilProfessor._meta.label, objeto_id=str(perfil.pk))
    eventos = list(EventoAuditoria.objects.filter(servico=request.servico).filter(filtro)[:limite])
    return auditoria.preparar_para_exibir(eventos, request.acesso)


# ---------------------------------------------------------------- mixins

class PessoaDoServicoMixin:
    """Carrega o vínculo da pessoa `pk` com o serviço atual; pessoa de outro serviço dá 404.

    Com `exige_gerir_pessoa`, só segue quem pode mexer no cadastro dessa pessoa (`pode_gerir`).
    Vem depois do AcessoMixin, então só roda para quem já passou pela permissão da tela.
    """

    exige_gerir_pessoa = False
    proibe_a_si_mesmo = False
    motivo_a_si_mesmo = "Você não muda o próprio acesso. Peça a outra pessoa que cuida da equipe."

    @cached_property
    def vinculo(self):
        return get_object_or_404(
            Vinculo.objects.select_related("usuario", "papel"),
            usuario_id=self.kwargs["pk"], servico=self.request.servico,
        )

    def dispatch(self, request, *args, **kwargs):
        if self.exige_gerir_pessoa and not pode_gerir(request, self.vinculo):
            raise PermissionDenied("Só quem configura o serviço mexe no cadastro desta pessoa.")
        if self.proibe_a_si_mesmo and self.vinculo.usuario_id == request.user.pk:
            raise PermissionDenied(self.motivo_a_si_mesmo)
        return super().dispatch(request, *args, **kwargs)

    def url_da_pessoa(self):
        return reverse("equipe:pessoa_detalhe", args=[self.vinculo.usuario_id])


# ---------------------------------------------------------------- lista

class PessoasView(AcessoMixin, TemplateView):
    """Pessoas com vínculo ao serviço, com busca por nome ou e-mail."""

    acao = "gerir_equipe"
    template_name = "equipe/pessoas.html"

    def get_template_names(self):
        htmx = getattr(self.request, "htmx", None)
        if htmx and not htmx.boosted and htmx.target == "resultados":
            return ["equipe/_pessoas_resultados.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        servico = self.request.servico
        busca = " ".join(self.request.GET.get("q", "").split())[:100]
        situacao = self.request.GET.get("situacao", "ativas")
        if situacao not in dict(SITUACOES):
            situacao = "ativas"
        papeis = list(Papel.objects.filter(servico=servico).order_by("nome"))
        papel = self.request.GET.get("papel", "")
        papel_escolhido = next((p for p in papeis if str(p.pk) == papel), None)

        vinculos = (
            Vinculo.objects.filter(servico=servico)
            .select_related("usuario", "papel")
            .annotate(e_professor=Exists(
                PerfilProfessor.objects.filter(servico=servico, usuario_id=OuterRef("usuario_id"))
            ))
            .order_by("usuario__nome", "usuario__email")
        )
        if busca:
            vinculos = vinculos.filter(Q(usuario__nome__icontains=busca) | Q(usuario__email__icontains=busca))
        if situacao == "ativas":
            vinculos = vinculos.filter(ativo=True, usuario__is_active=True)
        elif situacao == "desativadas":
            vinculos = vinculos.filter(Q(ativo=False) | Q(usuario__is_active=False))
        if papel_escolhido is not None:
            vinculos = vinculos.filter(papel=papel_escolhido)

        pagina = Paginator(vinculos, PESSOAS_POR_PAGINA).get_page(self.request.GET.get("pagina"))
        contexto.update({
            "pagina": pagina,
            "busca": busca,
            "situacao": situacao,
            "situacoes": SITUACOES,
            "papeis": papeis,
            "papel": str(papel_escolhido.pk) if papel_escolhido else "",
            "filtrando": bool(busca or papel_escolhido or situacao != "ativas"),
        })
        return contexto


# ---------------------------------------------------------------- cadastrar

class PessoaNovaView(AcessoMixin, FormView):
    """Cadastra uma pessoa na equipe. Se o e-mail já é de alguém (de outro serviço), só cria o vínculo."""

    acao = "gerir_equipe"
    form_class = PessoaNovaForm
    template_name = "equipe/pessoa_form.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(servico=self.request.servico, acesso=self.request.acesso)
        return kwargs

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update({
            "titulo": "Cadastrar pessoa",
            "botao": "Cadastrar pessoa",
            "cancelar": reverse("equipe:pessoas"),
            "secoes": [
                {"titulo": "Dados da pessoa", "campos": ["email", "nome", "whatsapp_trabalho"]},
                {"titulo": "O que faz no serviço", "campos": ["papel"]},
            ],
        })
        return contexto

    def form_valid(self, form):
        dados = form.cleaned_data
        servico = self.request.servico
        with transaction.atomic():
            usuario = Usuario.objects.select_for_update().filter(email__iexact=dados["email"]).first()
            nova = usuario is None
            if nova:
                # Sem senha utilizável: a pessoa cria a própria senha pelo link (RF-05).
                usuario = Usuario.objects.create_user(
                    email=dados["email"], password=None, nome=dados["nome"],
                    whatsapp_trabalho=dados["whatsapp_trabalho"],
                )
                campos = ["email", "nome", "whatsapp_trabalho"]
                auditoria.registrar(
                    self.request, Acao.CRIOU, usuario, servico=servico, descricao="Cadastrou a pessoa na equipe",
                    mudancas=auditoria.comparar(Usuario, {}, auditoria.fotografar(usuario, campos)),
                )
            reativada = not usuario.is_active
            if reativada:
                usuario.is_active = True
                usuario.save(update_fields=["is_active"])
            vinculo = Vinculo.objects.create(usuario=usuario, servico=servico, papel=dados["papel"])
            descricao = f"Entrou na equipe como {vinculo.papel.nome}"
            if not nova:
                descricao += "; a pessoa já tinha cadastro na EntreLaço"
            if reativada:
                descricao += " e o login dela foi reativado"
            auditoria.registrar(
                self.request, Acao.CRIOU, vinculo, servico=servico, descricao=descricao,
                mudancas=auditoria.comparar(Vinculo, {}, auditoria.fotografar(vinculo, ["papel"])),
            )
        if nova:
            entregar_link(self.request, usuario, novo=False, na_tela=True)
            messages.success(self.request, "Pessoa cadastrada. Mande para ela o link para criar a senha.")
        elif usuario.has_usable_password():
            messages.success(
                self.request,
                f"{usuario.nome} já tinha cadastro na EntreLaço e agora também faz parte desta equipe. "
                "Ela entra com o e-mail e a senha que já usa; o nome e o WhatsApp continuam os do cadastro dela.",
            )
        else:
            # Já tinha cadastro, mas ainda não criou a senha: o link vai só para o e-mail dela (SEG-05).
            enviado = entregar_link(self.request, usuario, novo=False, na_tela=False)
            texto = (
                f"{usuario.nome} já tinha cadastro na EntreLaço e agora também faz parte desta equipe. "
                "Ela ainda não criou a senha"
            )
            if enviado:
                messages.success(self.request, f"{texto}: o link para criar a senha foi mandado para {usuario.email}.")
            else:
                messages.warning(
                    self.request,
                    f"{texto}, e não deu para mandar o link por e-mail agora. "
                    "Use “Mandar link de senha por e-mail” daqui a pouco.",
                )
        return redirect("equipe:pessoa_detalhe", pk=usuario.pk)


# ---------------------------------------------------------------- detalhe

class PessoaDetalheView(AcessoMixin, PessoaDoServicoMixin, TemplateView):
    acao = "gerir_equipe"
    template_name = "equipe/pessoa_detalhe.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        vinculo = self.vinculo
        pessoa = vinculo.usuario
        perfil = (
            PerfilProfessor.objects.filter(servico=self.request.servico, usuario=pessoa)
            .prefetch_related("componentes").first()
        )
        link = self.request.session.get(CHAVE_DO_LINK)
        if link and link.get("usuario") == pessoa.pk:
            del self.request.session[CHAVE_DO_LINK]
        else:
            link = None
        gerir = pode_gerir(self.request, vinculo)
        ativa = vinculo.ativo and pessoa.is_active
        a_si_mesmo = pessoa.pk == self.request.user.pk
        outro_servico = tem_outro_servico(pessoa, self.request.servico)
        na_tela = link_na_tela(pessoa, outro_servico)
        contexto.update({
            "vinculo": vinculo,
            "pessoa": pessoa,
            "ativa": ativa,
            "a_si_mesmo": a_si_mesmo,
            "perfil": perfil,
            "componentes": list(perfil.componentes.all()) if perfil else [],
            "link": link,
            "horas": horas_de_validade(),
            "eventos": eventos_da_pessoa(self.request, vinculo, perfil),
            "pode_editar": gerir,
            "pode_desativar": gerir and vinculo.ativo and not a_si_mesmo,
            "pode_reativar": gerir and not ativa and not a_si_mesmo,
            "pode_gerar_link": pode_mandar_link(self.request, vinculo),
            "link_na_tela": na_tela,
            "so_por_email": "" if na_tela else por_que_so_por_email(pessoa, outro_servico),
            "tem_outro_servico": outro_servico,
            "senha_criada": pessoa.has_usable_password(),
        })
        return contexto


# ---------------------------------------------------------------- editar

class PessoaEditarView(AcessoMixin, PessoaDoServicoMixin, EdicaoSemVersaoMixin, FormView):
    """Nome, WhatsApp e papel, com motivo. Mudar o papel registra Acao.MUDOU_PAPEL (SEG-04)."""

    acao = "gerir_equipe"
    exige_gerir_pessoa = True
    form_class = PessoaEditarForm
    template_name = "equipe/pessoa_form.html"
    mensagem_sucesso = "Alterações salvas."

    @cached_property
    def compartilhada(self):
        """A pessoa também trabalha em outro serviço: nome e WhatsApp valem lá também (SEG-05)."""
        return tem_outro_servico(self.vinculo.usuario, self.request.servico)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update(
            servico=self.request.servico, acesso=self.request.acesso,
            a_si_mesmo=self.vinculo.usuario_id == self.request.user.pk,
            compartilhada=self.compartilhada,
        )
        return kwargs

    def get_initial(self):
        return self.valores_brutos(self.vinculo)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update({
            "pessoa": self.vinculo.usuario,
            "compartilhada": self.compartilhada,
            "titulo": f"Editar dados de {self.vinculo.usuario.nome}",
            "botao": "Salvar alterações",
            "cancelar": self.url_da_pessoa(),
            "secoes": [
                {"titulo": "Dados da pessoa", "campos": ["nome", "whatsapp_trabalho"]},
                {"titulo": "O que faz no serviço", "campos": ["papel"]},
            ],
        })
        return contexto

    def get_success_url(self):
        return self.url_da_pessoa()

    def objeto_atual(self):
        return self.vinculo

    def travar(self):
        Usuario.objects.select_for_update().get(pk=self.vinculo.usuario_id)
        return Vinculo.objects.select_for_update().select_related("usuario", "papel").get(pk=self.vinculo.pk)

    def valores_salvos(self, vinculo):
        return PessoaEditarForm.valores_salvos(vinculo)

    def valores_brutos(self, vinculo):
        return PessoaEditarForm.valores_brutos(vinculo)

    def ultimo_evento(self, vinculo):
        return EventoAuditoria.objects.filter(
            Q(modelo=Usuario._meta.label, objeto_id=str(vinculo.usuario_id))
            | Q(modelo=Vinculo._meta.label, objeto_id=str(vinculo.pk)),
            servico=self.request.servico, acao__in=[Acao.ALTEROU, Acao.MUDOU_PAPEL],
        ).first()

    def salvar(self, vinculo, form, mudancas):
        motivo = form.cleaned_data["motivo_alteracao"]
        usuario = vinculo.usuario
        dados_da_pessoa = {nome: m for nome, m in mudancas.items() if nome != "papel"}
        if dados_da_pessoa and not self.compartilhada:
            usuario.nome = form.cleaned_data["nome"]
            usuario.whatsapp_trabalho = form.cleaned_data["whatsapp_trabalho"]
            usuario.save(update_fields=["nome", "whatsapp_trabalho"])
            auditoria.registrar(
                self.request, Acao.ALTEROU, usuario, servico=self.request.servico,
                mudancas=dados_da_pessoa, motivo=motivo, descricao="Dados da pessoa",
            )
        if "papel" in mudancas:
            vinculo.papel = form.cleaned_data["papel"]
            vinculo.save(update_fields=["papel"])
            auditoria.registrar(
                self.request, Acao.MUDOU_PAPEL, vinculo, servico=self.request.servico,
                mudancas={"papel": mudancas["papel"]}, motivo=motivo,
                descricao=f"Papel de {usuario.nome} no serviço",
            )


# ---------------------------------------------------------------- desativar e reativar

class PessoaDesativarView(AcessoMixin, PessoaDoServicoMixin, FormView):
    """Desliga o vínculo com o serviço. Sem outro vínculo ativo, o login é desativado e as sessões
    abertas são encerradas (SEG-09). Ninguém desativa a si mesmo."""

    acao = "gerir_equipe"
    exige_gerir_pessoa = True
    proibe_a_si_mesmo = True
    form_class = DesativarForm
    template_name = "equipe/pessoa_desativar.html"

    def get(self, request, *args, **kwargs):
        if not self.vinculo.ativo:
            messages.info(request, "O acesso desta pessoa já está desativado.")
            return redirect(self.url_da_pessoa())
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not self.vinculo.ativo:
            messages.info(request, "O acesso desta pessoa já está desativado.")
            return redirect(self.url_da_pessoa())
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update({
            "pessoa": self.vinculo.usuario,
            "vinculo": self.vinculo,
            "outro_vinculo_ativo": self._outro_vinculo_ativo(),
        })
        return contexto

    def _outro_vinculo_ativo(self):
        return Vinculo.objects.filter(
            usuario_id=self.vinculo.usuario_id, ativo=True, servico__ativo=True
        ).exclude(servico=self.request.servico).exists()

    def form_valid(self, form):
        motivo = form.cleaned_data["motivo"]
        with transaction.atomic():
            vinculo = Vinculo.objects.select_for_update().select_related("usuario", "papel").get(pk=self.vinculo.pk)
            usuario = vinculo.usuario
            vinculo.ativo = False
            vinculo.save(update_fields=["ativo"])
            desligar_login = not self._outro_vinculo_ativo() and not usuario.is_superuser
            mudancas = {"ativo": {"rotulo": "acesso ao serviço", "grupo": None, "de": "Ativo", "para": "Desativado"}}
            descricao = f"Desativou o acesso de {usuario.nome} ao serviço"
            if desligar_login and usuario.is_active:
                usuario.is_active = False
                usuario.save(update_fields=["is_active"])
                mudancas["login"] = {"rotulo": "login", "grupo": None, "de": "Ativo", "para": "Desativado"}
                descricao += " e encerrou as sessões abertas"
                encerrar_sessoes(usuario)
            auditoria.registrar(
                self.request, Acao.ALTEROU, vinculo, servico=self.request.servico,
                mudancas=mudancas, motivo=motivo, descricao=descricao,
            )
        messages.success(self.request, f"Acesso de {usuario.nome} desativado.")
        return redirect(self.url_da_pessoa())


class PessoaReativarView(AcessoMixin, PessoaDoServicoMixin, View):
    acao = "gerir_equipe"
    exige_gerir_pessoa = True
    proibe_a_si_mesmo = True
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            vinculo = Vinculo.objects.select_for_update().select_related("usuario", "papel").get(pk=self.vinculo.pk)
            usuario = vinculo.usuario
            mudancas = {}
            if not vinculo.ativo:
                vinculo.ativo = True
                vinculo.save(update_fields=["ativo"])
                mudancas["ativo"] = {"rotulo": "acesso ao serviço", "grupo": None, "de": "Desativado", "para": "Ativo"}
            if not usuario.is_active:
                usuario.is_active = True
                usuario.save(update_fields=["is_active"])
                mudancas["login"] = {"rotulo": "login", "grupo": None, "de": "Desativado", "para": "Ativo"}
            if mudancas:
                auditoria.registrar(
                    request, Acao.ALTEROU, vinculo, servico=request.servico, mudancas=mudancas,
                    descricao=f"Reativou o acesso de {usuario.nome} ao serviço",
                )
        if mudancas:
            messages.success(request, f"Acesso de {usuario.nome} reativado. Ela entra com a senha que já tinha.")
        else:
            messages.info(request, "O acesso desta pessoa já estava ativo.")
        return redirect(self.url_da_pessoa())


# ---------------------------------------------------------------- link de senha

class PessoaLinkSenhaView(AcessoMixin, PessoaDoServicoMixin, View):
    """Gera um novo link para a pessoa criar a senha e tenta o e-mail.

    O link aparece uma vez na tela dela só quando `link_na_tela` deixa; senão vai só para o e-mail.
    """

    acao = "gerir_equipe"
    exige_gerir_pessoa = True
    proibe_a_si_mesmo = True
    motivo_a_si_mesmo = "Para trocar a sua senha, use Minha conta, em “Trocar senha”."
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        vinculo = self.vinculo
        usuario = vinculo.usuario
        if not pode_mandar_link(request, vinculo):
            raise PermissionDenied("Reative o acesso da pessoa antes de mandar um link de senha.")
        na_tela = link_na_tela(usuario, tem_outro_servico(usuario, request.servico))
        enviado = entregar_link(request, usuario, novo=True, na_tela=na_tela)
        if na_tela:
            messages.success(
                request,
                "Link novo gerado. Os links gerados antes continuam valendo até vencer ou até a senha ser criada.",
            )
        elif enviado:
            horas = horas_de_validade()
            messages.success(
                request,
                f"Link para criar a senha mandado para {usuario.email}. Ele vale por "
                f"{horas} hora{'s' if horas != 1 else ''} e serve uma vez só.",
            )
        else:
            messages.warning(request, "Não deu para mandar o e-mail agora. Tente de novo daqui a pouco.")
        return redirect(self.url_da_pessoa())


# ---------------------------------------------------------------- perfil de professor

class ProfessorPermissaoMixin:
    """Perfil de professor (RF-09): quem cuida da equipe, ou a própria pessoa no próprio perfil.

    Fica antes do AcessoMixin para trocar a regra da tela; o vínculo é conferido depois dele.
    """

    def tem_permissao(self, request):
        return request.acesso.tem("gerir_equipe") or request.user.pk == self.kwargs.get("pk")


class ProfessorMixin(PessoaDoServicoMixin):
    model = PerfilProfessor
    template_name = "equipe/professor_form.html"
    mensagem_sucesso = "Perfil de professor salvo."

    def get_success_url(self):
        if self.request.acesso.tem("gerir_equipe"):
            return self.url_da_pessoa()
        return reverse("minha_conta")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update({
            "pessoa": self.vinculo.usuario,
            "a_si_mesmo": self.vinculo.usuario_id == self.request.user.pk,
            "cancelar": self.get_success_url(),
            "secoes": [
                {"titulo": "O que ensina", "campos": ["componentes"]},
                {
                    "titulo": "Etapas em que dá aula",
                    "campos": ["educacao_infantil", "anos_iniciais", "anos_finais", "ensino_medio", "eja"],
                    "ajuda": "Marque todas as que valem.",
                },
                {"titulo": "Mais sobre o trabalho", "campos": ["observacoes"]},
            ],
        })
        return contexto


class ProfessorCriarView(ProfessorPermissaoMixin, AcessoMixin, ProfessorMixin, CriarComAuditoriaMixin, CreateView):
    def get_form_class(self):
        return formulario_do_professor(self.request.servico)

    def preparar_objeto(self, obj, form):
        obj.usuario = self.vinculo.usuario

    def form_valid(self, form):
        # O perfil é um por pessoa em cada serviço. Se outra pessoa o criou no meio do caminho
        # (antes da conferência ou entre ela e a gravação), nada é salvo e a tela abre o perfil dela.
        ja_existe = PerfilProfessor.objects.filter(
            servico=self.request.servico, usuario_id=self.vinculo.usuario_id
        ).exists()
        if not ja_existe:
            try:
                return super().form_valid(form)
            except IntegrityError:
                pass
        messages.info(self.request, "Outra pessoa acabou de criar este perfil. Confira os dados e salve de novo.")
        return HttpResponseRedirect(self.request.path)


class ProfessorEditarView(ProfessorPermissaoMixin, AcessoMixin, ProfessorMixin, EditarComAuditoriaMixin, UpdateView):
    def get_form_class(self):
        return formulario_do_professor(self.request.servico, edicao=True)

    def get_object(self, queryset=None):
        return get_object_or_404(PerfilProfessor, servico=self.request.servico, usuario_id=self.vinculo.usuario_id)


_criar_professor = ProfessorCriarView.as_view()
_editar_professor = ProfessorEditarView.as_view()


def professor(request, pk):
    """Cria o perfil de professor na primeira vez e edita (com motivo) depois."""
    servico = getattr(request, "servico", None)
    if servico is not None and PerfilProfessor.objects.filter(servico=servico, usuario_id=pk).exists():
        return _editar_professor(request, pk=pk)
    return _criar_professor(request, pk=pk)

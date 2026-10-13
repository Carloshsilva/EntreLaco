"""Configuração da EntreLaço.

Tudo o que muda entre ambientes vem de variáveis de ambiente (veja .env.example).
"""
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(nome, padrao=False):
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


def env_lista(nome, padrao=""):
    return [item.strip() for item in os.environ.get(nome, padrao).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
# `manage.py test` roda sem precisar de chave nem de collectstatic.
RODANDO_TESTES = len(sys.argv) > 1 and sys.argv[1] == "test"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or RODANDO_TESTES:
        SECRET_KEY = "dev-inseguro-apenas-local"
    else:
        raise RuntimeError("Defina DJANGO_SECRET_KEY fora do modo de desenvolvimento.")

ALLOWED_HOSTS = env_lista("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_lista("DJANGO_CSRF_TRUSTED_ORIGINS")

# Mostra a faixa "Ambiente de teste: use só dados inventados" em todas as telas.
AMBIENTE_DE_TESTE = env_bool("ENTRELACO_AMBIENTE_DE_TESTE", True)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django_htmx",
    "core",
    "equipe",
    "escolas",
    "alunos",
    "aulas",
    "reunioes",
    "autorizacoes",
    "documentos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "core.middleware.ServicoMiddleware",
    "core.middleware.DuasEtapasMiddleware",
    "core.middleware.ModoAssinaturaMiddleware",
    "core.middleware.CabecalhosDeSegurancaMiddleware",
]

ROOT_URLCONF = "config.urls"

PASSWORD_RESET_TIMEOUT = 60 * 60 * 24  # link de definir senha vale 24 horas

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.entrelaco",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


def banco_de_dados():
    url = os.environ.get("DATABASE_URL")
    if not url:
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    partes = urlparse(url)
    if partes.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("DATABASE_URL precisa começar com postgres://")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": partes.path.lstrip("/"),
        "USER": unquote(partes.username or ""),
        "PASSWORD": unquote(partes.password or ""),
        "HOST": partes.hostname or "",
        "PORT": str(partes.port or ""),
        "CONN_MAX_AGE": 60,
    }


DATABASES = {"default": banco_de_dados()}

AUTH_USER_MODEL = "core.Usuario"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "entrar"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "entrar"

# Sessão expira após 30 minutos sem uso (SEG-07).
SESSION_COOKIE_AGE = int(os.environ.get("ENTRELACO_SESSAO_SEGUNDOS", 30 * 60))
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not (DEBUG or RODANDO_TESTES)
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

# Arquivos enviados (fotos de aula, documentos) ficam fora da pasta pública
# e só são entregues por views que conferem a permissão de quem pede.
MEDIA_ROOT = Path(os.environ.get("ENTRELACO_PASTA_PRIVADA", BASE_DIR / "privado"))
MEDIA_URL = "/arquivos-protegidos/"  # nunca servido diretamente
ENTRELACO_TAMANHO_MAXIMO_ARQUIVO = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_BACKEND = os.environ.get("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", 587))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "EntreLaço <nao-responda@exemplo.org>")

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
# Verificação em duas etapas obrigatória para o administrador e para quem configura (SEG-07).
EXIGIR_DUAS_ETAPAS = env_bool("ENTRELACO_EXIGIR_DUAS_ETAPAS", True)
# Bloqueio de login depois de muitas tentativas erradas.
LOGIN_TENTATIVAS = int(os.environ.get("ENTRELACO_LOGIN_TENTATIVAS", 5))
LOGIN_BLOQUEIO_MINUTOS = int(os.environ.get("ENTRELACO_LOGIN_BLOQUEIO_MINUTOS", 15))

if not DEBUG and not RODANDO_TESTES:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", 60 * 60 * 24 * 30))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}

if RODANDO_TESTES:
    import warnings

    # Testes mais rápidos: o hash de senha forte não importa aqui.
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    warnings.filterwarnings("ignore", message="No directory at", module="whitenoise.base")
    MEDIA_ROOT = BASE_DIR / ".privado-testes"
    # Os 403 e 404 esperados nos testes não precisam encher a saída de traceback.
    LOGGING["loggers"] = {"django.request": {"level": "ERROR"}, "django.security": {"level": "ERROR"}}

# Imagem da EntreLaço: Django + Gunicorn, rodando com um usuário sem permissão de administrador.
# Quem usa: o serviço "web" do docker-compose.yml. Veja o README, seção "Implantar na VPS".
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENTRELACO_PASTA_PRIVADA=/dados/privado

WORKDIR /app

# Usuário sem root. O código fica com o root e só para leitura; o usuário escreve apenas na pasta privada.
RUN groupadd --system --gid 1000 entrelaco \
    && useradd --system --uid 1000 --gid entrelaco --home-dir /app --no-create-home \
       --shell /usr/sbin/nologin entrelaco

# As dependências primeiro, para o Docker reaproveitar esta camada quando só o código muda.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Arquivos estáticos no build. A chave abaixo só existe neste passo e não vai para o contêiner.
# A pasta privada nasce com o dono certo, e o volume herda isso na primeira vez que é montado.
RUN DJANGO_SECRET_KEY="so-para-o-collectstatic-do-build" python manage.py collectstatic --noinput \
    && chmod 0755 deploy/entrypoint.sh \
    && mkdir -p /dados/privado \
    && chown entrelaco:entrelaco /dados/privado \
    && chmod 0750 /dados/privado

USER entrelaco

EXPOSE 8000

# Aplica as migrações e depois sobe o Gunicorn (3 workers, timeout de 60 segundos).
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "--config", "/app/deploy/gunicorn.conf.py", "config.wsgi:application"]

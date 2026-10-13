#!/bin/sh
# Entrada do contêiner web: aplica as migrações do banco e depois roda o comando pedido
# (o Gunicorn, por padrão). Se o banco ainda estiver subindo, tenta de novo algumas vezes.
set -eu

tentativas=0
until python manage.py migrate --noinput; do
    tentativas=$((tentativas + 1))
    if [ "$tentativas" -ge 10 ]; then
        echo "As migrações falharam 10 vezes. Veja o erro acima e os registros do banco: docker compose logs db" >&2
        exit 1
    fi
    echo "O banco ainda não respondeu. Nova tentativa em 3 segundos ($tentativas de 10)." >&2
    sleep 3
done

exec "$@"

#!/usr/bin/env bash
# Cópia de segurança diária da EntreLaço (RNF-06): o banco e a pasta privada de arquivos.
#
# Roda no servidor, fora dos contêineres, pelo cron do root (linha pronta no README):
#   30 2 * * * /opt/entrelaco/deploy/backup.sh >> /var/log/entrelaco-backup.log 2>&1
#
# Grava em PASTA_COPIAS (padrão /var/backups/entrelaco), com a data e a hora no nome:
#   banco-AAAA-MM-DD_HHMM.dump        banco inteiro (pg_dump no formato do PostgreSQL, já comprimido)
#   arquivos-AAAA-MM-DD_HHMM.tar.gz   fotos, documentos e assinaturas (ENTRELACO_PASTA_PRIVADA)
# Confere se cada cópia abre e apaga as que têm mais de 30 dias. Se algo falhar e EMAIL_DE_AVISO estiver
# no .env, manda um e-mail para esse endereço pelo e-mail configurado no Django (RNF-07).
set -euo pipefail

PROJETO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJETO"

# Lê uma variável do .env sem executar o arquivo.
ler_do_env() {
    [ -f .env ] || return 0
    { grep -E "^$1=" .env || true; } | tail -n 1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//'
}

PASTA_COPIAS="${PASTA_COPIAS:-$(ler_do_env PASTA_COPIAS)}"
PASTA_COPIAS="${PASTA_COPIAS:-/var/backups/entrelaco}"
DIAS_DE_GUARDA="${DIAS_DE_GUARDA:-30}"
DATA="$(date +%Y-%m-%d_%H%M)"
BANCO="$PASTA_COPIAS/banco-$DATA.dump"
ARQUIVOS="$PASTA_COPIAS/arquivos-$DATA.tar.gz"

registrar() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

avisar_por_email() {
    destino="${EMAIL_DE_AVISO:-$(ler_do_env EMAIL_DE_AVISO)}"
    [ -n "$destino" ] || return 0
    docker compose run --rm --no-deps -T --entrypoint python \
        -e EMAIL_DE_AVISO="$destino" -e TEXTO_DO_AVISO="$1" web manage.py shell -c '
import os
from django.core.mail import send_mail
send_mail("EntreLaço: a cópia de segurança falhou", os.environ["TEXTO_DO_AVISO"], None, [os.environ["EMAIL_DE_AVISO"]])
' > /dev/null || registrar "Também não deu para mandar o aviso por e-mail para $destino."
}

ao_sair() {
    status=$?
    rm -f "$BANCO.parcial" "$ARQUIVOS.parcial"
    if [ "$status" -ne 0 ]; then
        registrar "ERRO: a cópia de segurança falhou (código $status). Veja as mensagens acima."
        avisar_por_email "A cópia de segurança de $DATA falhou no servidor $(hostname) (código $status). \
Veja o registro em /var/log/entrelaco-backup.log e rode deploy/backup.sh de novo depois de corrigir."
    fi
}
trap ao_sair EXIT

# Só o root lê as cópias: elas têm todos os dados da plataforma.
umask 077
mkdir -p "$PASTA_COPIAS"
chmod 700 "$PASTA_COPIAS"

registrar "Copiando o banco para $BANCO"
docker compose exec -T db sh -c \
    'pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom --compress=6 --no-owner' \
    > "$BANCO.parcial"
# A cópia só vale se o PostgreSQL consegue ler o índice dela.
docker compose exec -T db pg_restore --list < "$BANCO.parcial" > /dev/null
mv "$BANCO.parcial" "$BANCO"

registrar "Copiando a pasta privada de arquivos para $ARQUIVOS"
# Um contêiner de uma vez só, com o volume dos arquivos: funciona mesmo com a aplicação parada.
docker compose run --rm --no-deps -T --entrypoint tar web -czf - -C /dados/privado . > "$ARQUIVOS.parcial"
gzip -t "$ARQUIVOS.parcial"
mv "$ARQUIVOS.parcial" "$ARQUIVOS"

registrar "Apagando as cópias com mais de $DIAS_DE_GUARDA dias"
find "$PASTA_COPIAS" -maxdepth 1 -type f \( -name 'banco-*.dump' -o -name 'arquivos-*.tar.gz' \) \
    -mmin +$((DIAS_DE_GUARDA * 24 * 60)) -print -delete

registrar "Cópia concluída: banco com $(du -h "$BANCO" | cut -f1), arquivos com $(du -h "$ARQUIVOS" | cut -f1)." \
    "Há $(find "$PASTA_COPIAS" -maxdepth 1 -name 'banco-*.dump' | wc -l) cópias guardadas."

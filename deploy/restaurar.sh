#!/usr/bin/env bash
# Teste mensal de restauração (RNF-06): mostra que uma cópia de segurança devolve os dados.
#
# Restaura a cópia do banco num banco de teste separado (entrelaco_restauracao_teste), no mesmo
# PostgreSQL, sem tocar no banco em uso. Compara a quantidade de registros com o banco em uso, confere
# se o esquema bate com a versão instalada e se a cópia dos arquivos abre. No fim, apaga o banco de
# teste e anota o resultado em PASTA_COPIAS/testes-de-restauracao.log.
#
# Uso, na pasta do projeto no servidor:
#   deploy/restaurar.sh                                   usa a cópia mais recente
#   deploy/restaurar.sh /var/backups/entrelaco/banco-2026-11-01_0230.dump
#   deploy/restaurar.sh --manter                          não apaga o banco de teste no fim
set -euo pipefail

PROJETO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJETO"

ler_do_env() {
    [ -f .env ] || return 0
    { grep -E "^$1=" .env || true; } | tail -n 1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//'
}

PASTA_COPIAS="${PASTA_COPIAS:-$(ler_do_env PASTA_COPIAS)}"
PASTA_COPIAS="${PASTA_COPIAS:-/var/backups/entrelaco}"
BANCO_TESTE="entrelaco_restauracao_teste"
TABELAS="core_servico core_usuario core_eventoauditoria alunos_aluno alunos_responsavel autorizacoes_autorizacao
aulas_aula reunioes_reuniao documentos_documento escolas_escola"

manter=0
copia=""
for argumento in "$@"; do
    case "$argumento" in
        --manter) manter=1 ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
        *) copia="$argumento" ;;
    esac
done
if [ -z "$copia" ]; then
    copia="$({ find "$PASTA_COPIAS" -maxdepth 1 -name 'banco-*.dump' -type f 2>/dev/null || true; } | sort | tail -n 1)"
fi
if [ -z "$copia" ] || [ ! -f "$copia" ]; then
    echo "Não achei a cópia do banco${copia:+ $copia}. Confira a pasta $PASTA_COPIAS ou passe o arquivo." >&2
    exit 1
fi
nome_da_copia="$(basename "$copia" .dump)"
arquivos="$(dirname "$copia")/arquivos-${nome_da_copia#banco-}.tar.gz"

registrar() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
usuario="$(docker compose exec -T db printenv POSTGRES_USER | tr -d '\r')"
banco_em_uso="$(docker compose exec -T db printenv POSTGRES_DB | tr -d '\r')"

psql_em() {  # banco, consulta
    docker compose exec -T db psql -v ON_ERROR_STOP=1 --username="$usuario" --dbname="$1" -tAc "$2" | tr -d '[:space:]'
}

apagar_banco_de_teste() {
    docker compose exec -T db dropdb --username="$usuario" --if-exists "$BANCO_TESTE"
}

resultado="FALHOU"
ao_sair() {
    status=$?
    if [ "$manter" -eq 0 ]; then
        apagar_banco_de_teste || true
    fi
    mkdir -p "$PASTA_COPIAS"
    echo "$(date '+%Y-%m-%d %H:%M') $resultado $(basename "$copia")" >> "$PASTA_COPIAS/testes-de-restauracao.log"
    if [ "$status" -ne 0 ]; then
        registrar "ERRO: o teste de restauração falhou (código $status). Veja as mensagens acima."
    fi
}
trap ao_sair EXIT

registrar "Restaurando $(basename "$copia") no banco de teste $BANCO_TESTE"
apagar_banco_de_teste
docker compose exec -T db createdb --username="$usuario" "$BANCO_TESTE"
docker compose exec -T db pg_restore --username="$usuario" --dbname="$BANCO_TESTE" \
    --no-owner --no-privileges --exit-on-error < "$copia"

registrar "Registros na cópia e no banco em uso (o banco em uso pode ter mais, pelo que mudou depois da cópia):"
printf '  %-28s %10s %10s\n' "tabela" "na cópia" "em uso"
vazia=0
for tabela in $TABELAS; do
    na_copia="$(psql_em "$BANCO_TESTE" "select count(*) from $tabela")"
    em_uso="$(psql_em "$banco_em_uso" "select count(*) from $tabela")"
    printf '  %-28s %10s %10s\n' "$tabela" "$na_copia" "$em_uso"
    if [ "$tabela" = "core_usuario" ] && [ "$na_copia" -eq 0 ] && [ "$em_uso" -gt 0 ]; then
        vazia=1
    fi
done
if [ "$vazia" -eq 1 ]; then
    registrar "ERRO: a cópia não tem nenhuma pessoa cadastrada, mas o banco em uso tem."
    exit 1
fi

registrar "Conferindo se o esquema da cópia bate com a versão instalada"
# O endereço do banco de teste nasce do DATABASE_URL do contêiner: a senha não passa por aqui.
if docker compose run --rm --no-deps -T --entrypoint sh web -c \
    "DATABASE_URL=\"\${DATABASE_URL%/*}/$BANCO_TESTE\" python manage.py migrate --check" > /dev/null; then
    registrar "Esquema em dia: todas as migrações estão aplicadas na cópia."
else
    registrar "AVISO: faltam migrações na cópia. É esperado se a plataforma foi atualizada depois desta cópia."
fi

if [ -f "$arquivos" ]; then
    registrar "Conferindo a cópia dos arquivos: $(basename "$arquivos")"
    gzip -t "$arquivos"
    na_copia="$(tar -tzf "$arquivos" | grep -cv '/$' || true)"
    em_uso="$(docker compose run --rm --no-deps -T --entrypoint sh web -c 'find /dados/privado -type f | wc -l' \
        | tr -d '[:space:]')"
    registrar "Arquivos na cópia: $na_copia. Na pasta privada em uso: $em_uso."
else
    registrar "AVISO: não achei a cópia dos arquivos do mesmo horário ($(basename "$arquivos"))."
fi

resultado="OK"
if [ "$manter" -eq 1 ]; then
    registrar "Banco de teste mantido: $BANCO_TESTE. Apague depois com: docker compose exec db dropdb -U $usuario $BANCO_TESTE"
fi
registrar "Teste de restauração concluído: a cópia devolveu os dados."

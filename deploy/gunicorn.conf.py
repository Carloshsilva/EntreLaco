"""Configuração do Gunicorn, o servidor da aplicação dentro do contêiner web.

O Caddy recebe as visitas (HTTPS) e repassa para cá pela rede interna do Docker;
a porta 8000 não fica aberta para fora do servidor.
"""
import os

bind = "0.0.0.0:8000"
# 3 processos atendem com folga a Escola Móvel (até 300 alunos e 20 professores, RNF-13).
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))
# Uma tela que demora mais de 60 segundos é encerrada e aparece nos registros.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5
# Renova cada processo de tempos em tempos, para nenhum crescer demais na memória.
max_requests = 1000
max_requests_jitter = 100
worker_tmp_dir = "/dev/shm"
# Só o Caddy alcança esta porta, então o cabeçalho X-Forwarded-* dele é confiável.
forwarded_allow_ips = "*"

# Registros vão para a saída padrão: docker compose logs web (RNF-07).
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
accesslog = None  # o acesso já aparece nos registros do Caddy
capture_output = True

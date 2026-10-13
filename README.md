# EntreLaço

Plataforma web para serviços de educação hospitalar: cadastros, aulas, autorizações da família, reuniões,
documentos e pendências de cada aluno, num lugar só. Funciona no navegador do computador, do tablet e do
celular. Não precisa instalar nada.

> **Só dados inventados.** Esta primeira versão é para a equipe da Escola Móvel testar. Não cadastre nome,
> diagnóstico, telefone ou qualquer dado de criança, família ou pessoa real. Todas as telas mostram uma
> faixa avisando isso.

## O que esta versão tem

- Entrar com e-mail e senha, link para criar ou trocar a senha e verificação em duas etapas para quem
  configura o serviço.
- Equipe e papéis: cada papel diz, por tipo de dado, se a pessoa não vê, vê ou vê e edita.
- Cadastro de professores (o que ensina e em quais etapas), componentes curriculares e escolas de origem.
- Alunos com ficha, responsáveis, situação (ativo, pausa, encerrado), ordem de atendimento e professor
  domiciliar.
- Autorizações da família por tablet (assinatura na tela), papel, WhatsApp ou pendente, com comprovante.
- Aulas marcadas e registradas, com fotos, habilidades da BNCC e aula que não aconteceu.
- Reuniões com pauta, ata e alunos citados.
- Documentos do aluno.
- Início com as pendências de cada pessoa e a agenda da semana.
- Trilha de auditoria: quem fez o quê e quando, com o motivo de cada alteração.

O que fica para depois está em [docs/arquitetura.md](docs/arquitetura.md), na seção "O que fica para depois".
Os requisitos aprovados estão em [docs/requisitos.md](docs/requisitos.md).

## Rodar no seu computador

Precisa do Python 3.12 ou mais novo.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py createsuperuser
python manage.py carregar_dados_ficticios --senha "uma-senha-de-teste-longa"
python manage.py runserver
```

Abra http://127.0.0.1:8000 e entre com um dos e-mails que o último comando mostrou. Sem `DATABASE_URL`,
o banco é um arquivo SQLite (`db.sqlite3`).

O painel da plataforma (serviços, pessoas e papéis) fica em `/plataforma/`, só para o administrador.

## Rodar os testes

```bash
export DJANGO_DEBUG=1
python manage.py test
ruff check .
```

O CI (GitHub Actions) roda os mesmos testes no PostgreSQL, confere migrações e estilo e monta a imagem
Docker a cada envio.

## Colocar no ar numa VPS (Hostinger, Ubuntu)

1. **Domínio.** No painel do domínio, crie um registro A apontando para o IP da VPS. Espere ele responder
   (`ping seu-dominio`) antes do passo 5, senão o certificado HTTPS não sai.
2. **Docker.** Na VPS, como root, instale o Docker com o plugin compose:
   `curl -fsSL https://get.docker.com | sh`
3. **Código.** Copie o projeto para `/opt/entrelaco` (por exemplo, `git clone` do repositório).
4. **Configuração.** Na pasta do projeto:
   ```bash
   cp .env.example .env
   chmod 600 .env
   nano .env
   ```
   Troque o domínio, gere a chave do Django e a senha do banco com os comandos que estão no próprio
   arquivo. Deixe `ENTRELACO_AMBIENTE_DE_TESTE=1`.
5. **Subir.** `docker compose up -d --build`. Na primeira vez, o banco é criado e as migrações rodam
   sozinhas. Para acompanhar: `docker compose ps` e `docker compose logs -f web`.
6. **Administrador.** `docker compose exec web python manage.py createsuperuser`
7. **Dados fictícios.** `docker compose exec web python manage.py carregar_dados_ficticios`
   O comando cria o serviço "Escola Móvel (teste)" e mostra, uma única vez, o e-mail e a senha de cada
   pessoa inventada. Guarde essa lista num lugar seguro e entregue a cada pessoa da equipe a conta que
   ela vai usar no teste. Para começar de novo do zero: `... carregar_dados_ficticios --recriar`.
8. **Duas etapas.** No primeiro login, o administrador e quem tem o papel Supervisão ativam a verificação em
   duas etapas com um aplicativo autenticador no celular (Google Authenticator, Microsoft Authenticator ou
   parecido).

Para atualizar depois: `git pull` e `docker compose up -d --build`.

## Cópias de segurança

`deploy/backup.sh` copia o banco e a pasta de fotos e documentos para `PASTA_COPIAS` (padrão
`/var/backups/entrelaco`), fora do Docker, e apaga as cópias com mais de 30 dias. Para rodar todo dia às
2h30, abra o cron do root (`crontab -e`) e acrescente:

```
30 2 * * * /opt/entrelaco/deploy/backup.sh >> /var/log/entrelaco-backup.log 2>&1
```

Com `EMAIL_DE_AVISO=voce@seu-dominio` no `.env` e o e-mail configurado, uma falha na cópia manda um aviso.

Guarde também uma cópia fora da VPS (por exemplo, baixando a pasta de cópias uma vez por semana): se a VPS
se perder, as cópias que estão nela vão junto.

**Teste mensal de restauração.** Uma vez por mês, rode `deploy/restaurar.sh`. Ele restaura a cópia mais
recente num banco separado, compara a quantidade de registros com o banco em uso, confere se o arquivo de
fotos abre e anota o resultado em `PASTA_COPIAS/testes-de-restauracao.log`. O banco em uso não é tocado.

## Registros e erros

- `docker compose logs -f web`: a aplicação (erros aparecem aqui).
- `docker compose logs -f caddy`: cada acesso ao site.
- `docker compose logs -f db`: o banco.

Para receber um e-mail a cada erro 500, dá para acrescentar a lista `ADMINS` no `config/settings.py` com o
e-mail de quem cuida do sistema, depois de configurar o envio de e-mail no `.env`. Fica a critério de quem
coordena o projeto.

## Onde está cada coisa

- `docs/requisitos.md`: requisitos aprovados.
- `docs/arquitetura.md`: regras do código (separação entre serviços, permissões, trilha, telas acessíveis).
- `core/`: entrar, permissões, trilha, início, agenda e pontos de encaixe dos módulos.
- `escolas/`, `equipe/`, `alunos/`, `autorizacoes/`, `aulas/`, `reunioes/`, `documentos/`: os módulos.
- `deploy/`: Caddy, Gunicorn, cópias de segurança e restauração.

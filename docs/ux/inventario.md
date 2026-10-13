# Inventário de telas do protótipo

Ponto de partida: as telas que existem hoje em entrelaco.tech, agrupadas pelo menu. Cada uma ganha
um arquivo em `telas/` quando for revista. "Fica", "muda" ou "sai" se decide depois das jornadas.

| Menu | Tela | Endereço | Arquivo em `telas/` |
| --- | --- | --- | --- |
| Início | Início (pendências e agenda do dia) | `/` | [inicio.md](telas/inicio.md) |
| Alunos | Lista de alunos | `/alunos/` | |
| Alunos | Cadastrar aluno | `/alunos/novo/` | |
| Alunos | Perfil do aluno (ficha, situação, responsáveis, histórico, autorizações, aulas, documentos, citações) | `/alunos/<id>/` | |
| Alunos | Mudar situação | `/alunos/<id>/situacao/` | |
| Alunos | Responsável (novo e editar) | `/alunos/<id>/responsaveis/novo/` | |
| Ordem de atendimento | Fila de atendimento | `/alunos/fila/` | |
| Agenda | Agenda da semana | `/agenda/` | |
| Aulas | Lista de aulas | `/aulas/` | |
| Aulas | Marcar aula | `/aulas/marcar/` | |
| Aulas | Registrar aula (avulsa ou marcada) | `/aulas/registrar/` | |
| Aulas | A aula não aconteceu | `/aulas/<id>/nao-aconteceu/` | |
| Aulas | Detalhe da aula e fotos | `/aulas/<id>/` | |
| Autorizações | Colher autorização (tablet, link, papel, WhatsApp) | `/autorizacoes/aluno/<id>/<tipo>/` | |
| Autorizações | Assinar (tela da família) | `/autorizacoes/<id>/assinar/` | |
| Autorizações | Revogar | `/autorizacoes/<id>/revogar/` | |
| Documentos | Enviar e ver documento | `/documentos/aluno/<id>/novo/` | |
| Reuniões | Lista, ata e citações | `/reunioes/` | |
| Escolas | Lista, busca INEP, detalhe e contato | `/escolas/` | |
| Equipe | Pessoas, professor, desativar | `/equipe/` | |
| Configuração | Serviço, papéis, componentes, termos, BNCC | `/equipe/configuracao/` | |
| Trilha de auditoria | Trilha | `/trilha/` | |
| Conta | Entrar, código, senha, duas etapas, minha conta | `/entrar/`, `/conta/` | |

Ainda não existem no protótipo, mas estão nos requisitos: quadro de pendências em Kanban e lista
(RF-38), backlog sem dono (RF-39), lista da reunião semanal (RF-42), painel da escola (RF-35),
indicadores (RF-54), atestado (RF-56), notificações (RF-47) e pré-preenchimento por foto e áudio (RF-51).

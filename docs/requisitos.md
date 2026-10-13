# EntreLaço: requisitos da primeira versão

Oct 12, 2026 · @Carlos Henrique

## Como ler

Este documento transforma a [proposta final da EntreLaço](https://claude.ai/code/artifact/755b76d5-1b87-452c-98c5-b8a492eaa01c) em requisitos numerados, cada um com critério de aceite e origem. É a etapa 2 do plano; a tecnologia, a linguagem e a hospedagem ficam para a etapa 5, então nenhum requisito escolhe ferramenta.

- **IDs estáveis.** RF são funcionais (o que o sistema faz), RNF são não funcionais (como ele se comporta), SEG são de segurança e LGPD são de proteção de dados. Um ID nunca muda nem é reaproveitado, para que as telas e o backlog possam citá-lo.
- **Origem.** "Proposta" é a aba Proposta final, com a seção e o item. "Entrevista" é a aba Entrevista e pesquisa, com a rodada e a pergunta (por exemplo, R4 P3).
- **Situação.** Para aprovar: saiu da proposta e espera o seu ok. Aguarda resposta: o requisito existe, mas falta uma decisão sua, indicada pelo número da pergunta (P1, P2…). Aguarda advogado: depende da pesquisa jurídica.
- **Nada inferido.** O que a proposta e as suas respostas não fecham está em Perguntas para você, no fim, com opções e a minha recomendação marcada.

**Fora da primeira versão**, pela proposta: envio de notificações por WhatsApp, WhatsApp automatizado (cadastro por áudio, lembrete que vira tarefa), editor visual de fluxo, agentes de IA conversando com a plataforma e acesso da família além do link de assinatura. A implantação na Escola Móvel (piloto, papel em paralelo por pelo menos uma semana, revisão na reunião de segunda) é um plano de trabalho, não requisito do sistema; ela volta na etapa 7.

## Requisitos funcionais

São 65 requisitos em onze grupos, na ordem em que a proposta apresenta cada assunto. Com as suas respostas, nenhum depende mais de você; dois esperam o advogado.

### Plataforma e serviços

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RF-01 | O administrador da plataforma cadastra serviços de educação hospitalar, cada um cliente da plataforma. | Um serviço novo é cadastrado e começa sem nenhum dado dos outros serviços. | Proposta: Cadastros, Serviço. Entrevista: R1 P1 | Aprovado |
| RF-02 | O administrador liga e desliga módulos por serviço: agenda externa, notificações, leitura de documentos e, no futuro, WhatsApp e IA. | Um módulo desligado não aparece nem age para aquele serviço; ligá-lo não muda os dados existentes. | Proposta: Customização, Plataforma | Aprovado |
| RF-03 | O administrador libera para qualquer papel de um serviço a permissão de configurar e as demais permissões liberáveis. | Cada liberação fica na trilha de auditoria com quem liberou, para qual papel e quando. | Proposta: Segurança, Configurar o serviço. Entrevista: R2 P1 | Aprovado |
| RF-04 | Na primeira versão, só quem coordena o serviço recebe a permissão de configurar, além do administrador; na Escola Móvel, é a supervisão. | Na Escola Móvel, só a supervisão e o administrador veem a configuração; o administrador consegue liberar para outro papel depois. | Proposta: Segurança, Configurar o serviço | Aprovado |

### Equipe, papéis e permissões

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RF-05 | Cada pessoa da equipe tem cadastro e login próprios, sem conta compartilhada. | Toda ação registrada aponta uma pessoa; não existe login de uso coletivo. | Proposta: Cadastros, Equipe e papéis. Entrevista: item C | Aprovado |
| RF-06 | O serviço cadastra seus papéis e dá a cada um um conjunto de permissões. | Quem configura cria um papel, define as permissões, e quem tem esse papel vê e faz só o que ele permite. | Proposta: Segurança, Dois níveis | Aprovado |
| RF-07 | As permissões valem por tipo de dado: a mesma tela mostra ou esconde cada grupo de dados conforme o papel. | Uma pessoa sem permissão para diagnóstico, como o apoio administrativo, não vê o diagnóstico em nenhuma parte da plataforma, nem em PDF ou notificação. | Proposta: Segurança, Permissão por tipo de dado. Entrevista: R3 P1 | Aprovado |
| RF-08 | Por padrão, cada pessoa vê as próprias tarefas e quem coordena vê todas e com quem estão; ver as dos outros pode ser liberado a pessoas específicas ou a todos. | Um professor sem a permissão não vê a tarefa de outro; depois da liberação, vê. | Proposta: Segurança, Ver tarefas dos outros. Entrevista: R4 P2 | Aprovado |

### Cadastros

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RF-09 | Cadastro de professor com o que cada um ensina e o calendário dele, com as aulas marcadas. | O calendário de um professor mostra as aulas marcadas para ele. | Proposta: Cadastros, Professor. Entrevista: R6 P2 | Aprovado |
| RF-10 | Ficha do aluno com os campos que o serviço configura, partindo dos da Escola Móvel; visão, audição, fala, motricidade, alfabetização e reprovação ficam em destaque no perfil. | Os seis campos aparecem no perfil sem abrir a ficha completa. | Proposta: Cadastros, Aluno. Entrevista: item D | Aprovado |
| RF-11 | Cada aluno tem uma situação (ativo, em pausa ou encerrado), e toda mudança pede o motivo, inclusive a volta a ativo. | Não se salva mudança de situação sem motivo; o histórico mostra cada mudança com motivo, pessoa e data. | Proposta: Cadastros, Aluno; Funcionalidades, Ciclo do aluno | Aprovado |
| RF-12 | Documentos (fotos e scans, inclusive a ficha de papel assinada) ficam organizados por aluno, com quem digitalizou. | Uma foto enviada aparece no histórico de documentos do aluno com data e autor. | Proposta: Cadastros, Documento | Aprovado |
| RF-13 | Base nacional de escolas de origem, compartilhada entre serviços e pré-preenchida com dados públicos: endereço, telefone e situação de funcionamento, pelo INEP. | Uma escola é encontrada pelo nome ou pelo código INEP já com endereço e telefone. | Proposta: Cadastros, Escola de origem. Entrevista: R5 P1; Dados públicos de escolas | Aprovado |
| RF-14 | Cada serviço confirma o contato da escola (e-mail e quem atende), com a situação atualizado ou precisa atualizar. | Contato não confirmado fica como precisa atualizar e gera tarefa para o apoio administrativo. Os outros serviços não veem esse contato; comum é só a base pública. | Proposta: Cadastros, Escola de origem. Entrevista: O ciclo do aluno, Vínculo com a escola | Aprovado |
| RF-15 | Registro de aula com os campos do serviço, fotos das atividades e vínculo com a agenda. | Uma aula marcada é registrada a partir da agenda, com fotos anexadas. | Proposta: Cadastros, Aula. Entrevista: itens K e L | Aprovado |
| RF-16 | Lista opcional de eixos e habilidades da BNCC no registro de aula, mantida e ligada pelo serviço; desligada na Escola Móvel até a revisão da adaptação curricular. | Desligada, o registro não mostra o campo; ligada, a pessoa escolhe itens da lista do serviço. | Proposta: Cadastros, Aula. Entrevista: item M | Aprovado |
| RF-17 | Calendário de reuniões com ata; a ata cita alunos, cada citação vai para o perfil do aluno com data, encaminhamento e responsável, e pode virar tarefa. | O aluno citado mostra a citação no perfil; transformá-la em tarefa cria a tarefa para o responsável; quem não tem permissão para aquele tipo de dado não vê a citação. | Proposta: Cadastros, Reunião. Entrevista: item O | Aprovado |

### Ciclo do aluno

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RF-18 | A Escola Móvel vem configurada com as seis fases: entrada, vínculo com a escola, aulas, acompanhamento, relatórios à escola e saída. | A configuração tem as seis fases e as tarefas da proposta, montadas só com os recursos de customização (RF-58 a RF-63). | Proposta: Funcionalidades, Ciclo do aluno; Customização | Aprovado |
| RF-19 | O professor registra aula antes do cadastro completo, e nasce a pendência da ficha e do termo para quem deu a aula. | Salvar uma aula de aluno sem ficha completa cria a tarefa na hora para o professor da aula. | Proposta: Ciclo do aluno. Entrevista: R4 P4, item A | Aprovado |
| RF-20 | Criança sem matrícula é acompanhada até a matrícula pela orientação pedagógica, que também liga para secretarias de educação; o papel pode ser trocado, e sem dono a tarefa cai no backlog. | Marcar o aluno como sem matrícula cria a tarefa para o papel configurado; sem papel, ela vai ao backlog sem dono. | Proposta: Ciclo do aluno. Entrevista: item F | Aprovado |
| RF-21 | Ativo é quem teve aula registrada ou marcada nas últimas três semanas, prazo configurável; vencido o prazo, nasce a revisão para a orientação pedagógica, que mantém ativo, põe em pausa ou encerra. | Um aluno sem aula há três semanas e um dia gera a revisão; mudar o prazo para quatro semanas muda quando ela nasce. | Proposta: Ciclo do aluno. Entrevista: pedido 30 | Aprovado |
| RF-22 | A saída registra data, motivo e responsável; os motivos são configuráveis, partindo de alta, fim do tratamento, volta à escola, transferência e óbito. | Não se encerra aluno sem data, motivo e responsável. | Proposta: Ciclo do aluno. Entrevista: item G | Aprovado |
| RF-23 | Na saída, a escola é avisada e recebe o resumo de uma página como último relatório. | Encerrar um aluno com autorização de contato envia o aviso e o resumo à escola dele. | Proposta: Comunicação com a escola. Entrevista: item H | Aprovado |
| RF-24 | Na alta do TMO, nasce a tarefa de ver se a criança precisa de professor domiciliar. Um campo da ficha diz a unidade ou o tipo de tratamento. | A saída por alta de um aluno com TMO marcado na ficha cria essa tarefa. | Proposta: Ciclo do aluno. Resposta à P12 | Aprovado |
| RF-65 | Troca de escola: trocar a escola do aluno tira ele do painel da escola antiga e dispara carta e link para a nova; no início do ano, nasce a revisão da escola de todos os alunos ativos. | Depois da troca, o aluno some do link da escola antiga, e a nova recebe carta e link se houver autorização e contato atualizado. | Entrevista: O ciclo do aluno, Acompanhamento. Resposta à P13 | Aprovado |

### Autorizações da família

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RF-25 | Duas autorizações separadas no cadastro do aluno: uso dos dados e contato com a escola. | A família pode aceitar uma e recusar a outra, e cada uma fica registrada à parte. | Proposta: Segurança, Autorizações da família | Aprovado |
| RF-26 | Quatro formas de colher, escolhidas por quem colhe na hora: tablet no leito, link para o celular, papel assinado e fotografado, e sim por WhatsApp. | As quatro formas estão disponíveis em todo cadastro; papel e foto atendem quem não tem nada eletrônico. O link vai por e-mail pela plataforma ou é copiado pela equipe para o WhatsApp de trabalho; o sim por WhatsApp é registrado anexando a conversa. | Proposta: Autorizações da família. Entrevista: R2 P4 e P5. Respostas às P6 e P7 | Aprovado |
| RF-27 | O sim por WhatsApp é provisório: já libera o contato com a escola e gera uma pendência separada até o sim definitivo. | Com sim provisório, a carta pode sair; o sim definitivo aparece no quadro como tarefa própria de quem colheu. | Proposta: Autorizações da família. Entrevista: R3 P5 | Aguarda advogado |
| RF-28 | Sem autorização de contato, nem provisória, nada é enviado à escola. | Para esse aluno não sai carta, link, lembrete nem resumo, nem à mão, e ele não aparece no painel da escola. | Proposta: Autorizações da família | Aprovado |
| RF-29 | A família pode revogar qualquer autorização a qualquer momento, e a equipe registra a revogação. | Registrada a revogação do contato, o aluno some do painel da escola e nada mais é enviado. | Proposta: Autorizações da família | Aprovado |
| RF-64 | Cada autorização tem uma situação: pendente, provisória, válida, recusada ou revogada; pendente e provisória viram tarefa para quem colheu. | Uma autorização pendente ou provisória aparece como tarefa de quem colheu, e a tarefa fecha quando ela passa a válida ou recusada. | Entrevista: Assinatura da família. Resposta à P8 | Aprovado |

### Comunicação e painel da escola

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RF-30 | Carta e link do painel saem sozinhos quando há autorização de contato e o contato está atualizado; o serviço pode desligar o envio automático. | Ligado, a carta sai assim que as duas condições se cumprem; desligado, nasce a tarefa de revisar e enviar. | Proposta: Comunicação com a escola. Entrevista: R4 P6; O ciclo do aluno | Aprovado |
| RF-31 | O e-mail à escola sai da conta de e-mail do próprio serviço, conectada à plataforma. | A escola recebe a mensagem com o endereço do serviço como remetente. | Proposta: Comunicação com a escola. Entrevista: R5 P4 | Aprovado |
| RF-32 | Um link por escola, com todos os alunos dela que têm autorização de contato, enviado por e-mail ou WhatsApp e válido assim que chega, sem código. | O link abre o painel sem login nem código; um aluno novo autorizado da mesma escola entra no mesmo link. Por WhatsApp, a plataforma gera o link e a pessoa o manda pelo WhatsApp de trabalho dela. | Proposta: Escola e família. Entrevista: R3 P2 e P3 | Aprovado |
| RF-33 | O link é só de leitura, cada abertura fica registrada, e ele pode ser cancelado e reenviado. | O link cancelado deixa de abrir e o novo abre; o registro mostra data e hora de cada abertura. | Proposta: Escola e família | Aprovado |
| RF-34 | Painel consolidado com as escolas que abriram o link e as que não abriram; as que não abriram no prazo do serviço viram tarefa. | A escola que não abre no prazo gera a tarefa de ligar para o apoio administrativo. | Proposta: Comunicação com a escola. Entrevista: R3 P2 | Aprovado |
| RF-35 | Painel vivo da escola: sempre atualizado, substitui o relatório bimestral e mostra o que o serviço configurar, partindo da carta e do padrão atuais. | Uma aula registrada aparece na próxima abertura do painel; um campo que o serviço tira do painel some para a escola. | Proposta: Painel vivo da escola. Entrevista: R3 P4, R4 P5 | Aprovado |
| RF-36 | Quando a escola pedir papel, o painel gera um resumo de uma página em PDF, com o embasamento legal fixo. | O PDF sai com uma página e traz o embasamento legal. | Proposta: Painel vivo da escola. Entrevista: item J | Aprovado |
| RF-37 | Lembretes para a escola olhar o painel, a cada X tempo e quando houver novidade, os dois configuráveis pelo serviço. | Com lembrete a cada 30 dias, a escola recebe um a cada 30 dias; com o de novidade ligado, recebe um quando o painel muda. | Proposta: Painel vivo da escola. Entrevista: R5 P5 | Aprovado |

### Quadro de pendências

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RF-38 | Duas visões, Kanban e lista, e cada pessoa alterna. | A mesma tarefa aparece nas duas visões. | Proposta: Quadro de pendências. Entrevista: R4 P1 | Aprovado |
| RF-39 | A tarefa vai para o papel definido no fluxo; sem papel, cai num backlog sem dono, de onde alguém atribui a um papel ou a uma pessoa. | Uma regra sem papel cria a tarefa no backlog; atribuí-la tira a tarefa do backlog. | Proposta: Quadro de pendências. Entrevista: R4 P3 | Aprovado |
| RF-40 | O backlog aceita itens cadastrados à mão, que podem virar revisão do fluxo. | Um item cadastrado à mão pode ser marcado como revisão do fluxo. | Proposta: Quadro de pendências. Entrevista: R4 P3 | Aprovado |
| RF-41 | O apoio administrativo recebe os alertas do dia, com o que está mais urgente naquele dia. | Os alertas trazem o que vence hoje ou já venceu. | Proposta: Quadro de pendências. Entrevista: item B | Aprovado |
| RF-42 | Para a reunião semanal, a plataforma monta sozinha a lista de revisão: backlog sem dono, alunos em revisão de situação e tarefas paradas. | A lista abre pronta com os três grupos. Tarefa parada é a que está sem movimento há 7 dias, prazo configurável pelo serviço. | Proposta: Quadro de pendências; Implantação | Aprovado |
| RF-43 | A tela inicial é igual para todos: as pendências de cada um e, para o professor, as aulas marcadas. | Cada papel entra e vê as próprias pendências; o professor vê também as aulas marcadas. | Proposta: Experiência do usuário. Entrevista: R6 P2 | Aprovado |

### Agenda

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RF-44 | Agenda própria com calendário por professor, aulas marcadas e reuniões. | Aulas e reuniões marcadas aparecem no calendário de quem participa. | Proposta: Agenda. Entrevista: R1 P5 | Aprovado |
| RF-45 | Conexão opcional com Google e Outlook. | Com a conexão ligada, uma aula marcada aparece na agenda externa da pessoa. A sincronização é de mão única, da plataforma para a agenda externa. | Proposta: Agenda. Entrevista: R1 P5 | Aprovado |
| RF-46 | A ordem de atendimento segue um critério simples e visível: dias sem aula, dias de internação e uma marca de risco de evasão que o professor ou a orientação liga; a pessoa sempre pode mudar a ordem à mão. | A lista mostra a ordem e por que cada aluno está ali; a mudança à mão vale. Os dias de internação vêm de um campo de data de internação na ficha, que o professor preenche e atualiza. | Proposta: Agenda. Entrevista: item N | Aprovado |

### Notificações

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RF-47 | Notificações na plataforma, por e-mail e por push; no iPhone, o push pede a plataforma instalada na tela inicial. | Uma tarefa nova chega pelos três canais a quem os ligou. | Proposta: Notificações. Entrevista: R5 P2 | Aprovado |
| RF-48 | O cadastro da equipe tem o campo de WhatsApp de trabalho; o envio por WhatsApp fica para a versão seguinte. | O campo existe e é salvo; nada é enviado por WhatsApp nesta versão. | Proposta: Notificações. Entrevista: R5 P2 | Aprovado |
| RF-49 | Por padrão, cada pessoa recebe um resumo por dia, no horário que escolher, e aviso na hora só do que vence no próprio dia; cada um ajusta. | Uma pessoa nova recebe o resumo no horário padrão e o aviso do que vence hoje; ao mudar o horário, o resumo muda. | Proposta: Notificações. Entrevista: R5 P3 | Aprovado |
| RF-50 | A notificação leva à lista de pendências. | Tocar na notificação abre a lista de pendências da pessoa. | Proposta: Notificações. Entrevista: R5 P3 | Aprovado |

### Pré-preenchimento e leitura de documentos

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RF-51 | Em todo formulário, a pessoa digita ou pré-preenche por foto com OCR, por áudio ou por IA. | Ficha, registro de aula e ata aceitam as três formas. | Proposta: Pré-preenchimento e digitalização. Entrevista: R5 P6, R6 P4 | Aprovado |
| RF-52 | A pessoa valida tudo o que veio pré-preenchido, numa tela pensada para isso, e fica registrado quem validou. | Nenhum valor pré-preenchido vira dado do aluno sem validação; o registro mostra quem validou. O que a pessoa digita salva na hora; o que veio de foto, áudio ou IA fica “a validar” até ela confirmar. | Proposta: Experiência do usuário. Entrevista: R6 P5 | Aprovado |
| RF-53 | Um agente ajuda a validar o que a leitura trouxe. | O agente marca os campos em que a leitura ficou em dúvida, e eles aparecem primeiro para a pessoa conferir. | Proposta: Pré-preenchimento e digitalização. Entrevista: R5 P6 | Aprovado |

### Indicadores e atestado

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RF-54 | Indicadores tirados do próprio sistema: aulas, atendimentos e tarefas paradas, e com quem estão. | Coordenação e quem configura veem os indicadores por mês e por professor; tarefa parada segue a definição do RF-42. | Proposta: Indicadores. Entrevista: item P | Aprovado |
| RF-55 | As aulas contam pela regra de equivalência de cada serviço; na Escola Móvel, 30 minutos de atendimento contam 1 aula. | Na Escola Móvel, 60 minutos de atendimento contam 2 aulas. | Proposta: Indicadores. Entrevista: item R | Aprovado |
| RF-56 | A plataforma gera o atestado de aula a partir das aulas registradas, com a regra de equivalência e a assinatura de quem coordena; a família recebe por link ou impresso. | O atestado traz as aulas do período e a assinatura de quem coordena. O nível de assinatura é a LGPD-07. | Proposta: Atestado de aula | Aguarda advogado |
| RF-57 | O atestado de presença do médico fica fora da plataforma; o pedido vira tarefa para o professor orientar a família. | Registrar o pedido cria a tarefa para o professor. | Proposta: Atestado de aula | Aprovado |

### Customização

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RF-58 | Formulários configuráveis (ficha, registro de aula, ata), com campos de texto, data, lista, sim ou não, assinatura, foto e anexo, e com versões. | Quem configura cria um formulário com cada tipo de campo e publica uma versão nova sem perder as respostas da antiga. | Proposta: Customização. Entrevista: Sugestão para o fluxo livre | Aprovado |
| RF-59 | Etapas e fluxos configuráveis: cada etapa diz que papel faz, que formulário preenche, o prazo e o que conta como concluído; as etapas se agrupam em fases e seguem caminhos conforme uma condição. | Um fluxo com uma condição (por exemplo, família não autoriza contato) segue o caminho certo para cada aluno. | Proposta: Customização. Entrevista: Sugestão para o fluxo livre | Aprovado |
| RF-60 | Regras no formato “quando acontecer X, criar a tarefa Y para o papel Z, com prazo de N dias”, com X numa lista fixa: aluno cadastrado, autorização recebida, contato atualizado, aula registrada, link não aberto e situação do aluno mudou. | Uma regra criada por quem configura passa a gerar a tarefa no evento escolhido, com o prazo certo. | Proposta: Customização | Aprovado |
| RF-61 | Modelos de carta e e-mail com campos que se preenchem sozinhos. | Uma carta gerada traz o nome do aluno e da escola sem digitação. | Proposta: Customização. Entrevista: Sugestão para o fluxo livre | Aprovado |
| RF-62 | Parâmetros configuráveis pelo serviço: o que a escola vê, lembretes, envio automático, frequência das notificações, prazo da revisão de aluno ativo, motivos de saída, regra de equivalência e lista da BNCC. | Cada parâmetro muda o comportamento do requisito dele sem ajuda do administrador. | Proposta: Customização, Serviço | Aprovado |
| RF-63 | Fluxos com versões: quem está no meio segue a versão em que começou, quem entra depois segue a nova, e quem configura pode mover alunos para a nova. | Depois de uma versão nova, os alunos antigos seguem a anterior; a mudança de um aluno de versão fica na trilha de auditoria. | Proposta: Customização | Aprovado |

## Requisitos não funcionais

São 14 requisitos de acessibilidade, aparelho, resiliência e arquitetura. A proposta fecha o que a plataforma precisa garantir, mas não dá números (volume, tempo fora do ar, quanto guardar de cópia), então cinco esperavam uma resposta sua; agora nenhum espera mais.

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| RNF-01 | Tablet, celular e computador, com a mesma tela adaptada. | O professor faz o cadastro no leito e o registro de aula do início ao fim num tablet e num celular; quem configura, a coordenação e o apoio administrativo trabalham também no computador. | Proposta: Experiência do usuário, Aparelho. Entrevista: R6 P1. Resposta à P5 | Aprovado |
| RNF-02 | A plataforma roda no navegador do tablet, do celular e do computador, sem instalar nada, e precisa de internet. O uso sem internet saiu da primeira versão em 12/10/2026. | O professor faz o cadastro e registra aula num navegador comum do tablet, sem instalar aplicativo. | Proposta: Experiência do usuário; Arquitetura funcional. Entrevista: R6 P3. Resposta à P1 | Aprovado |
| RNF-03 | Nada se perde: cada campo é salvo no servidor na hora; se a internet cair, o que foi digitado continua na tela, com aviso, e é enviado quando a conexão volta. | Com internet, fechar a plataforma logo depois de preencher um campo não apaga o campo; se a conexão cai, a tela avisa e envia o que ficou pendente quando ela volta, sem a pessoa redigitar. | Proposta: Arquitetura funcional, Robusta e resiliente | Aprovado |
| RNF-04 | A plataforma avisa quando duas pessoas mudaram o mesmo dado ao mesmo tempo, e quem salva por último escolhe a versão. | Quando duas pessoas editam o mesmo campo ao mesmo tempo, a segunda a salvar vê o aviso com as duas versões, e nenhuma vale antes da escolha. | Proposta: Arquitetura funcional, Robusta e resiliente. Resposta à P2 | Aprovado |
| RNF-05 | E-mail que falha é reenviado sozinho e, se falhar de vez, vira tarefa. | Um e-mail recusado é reenviado por 24 horas; depois disso sem sucesso, nasce a tarefa. | Proposta: Arquitetura funcional, Robusta e resiliente. Resposta à P16 | Aprovado |
| RNF-06 | Cópia de segurança diária, guardada por 30 dias, com teste de restauração mensal. | Existem as cópias dos últimos 30 dias, e o teste do mês devolve os dados. | Proposta: Arquitetura funcional, Robusta e resiliente. Resposta à P17 | Aprovado |
| RNF-07 | O administrador é avisado quando algo para de funcionar. | Uma falha de envio, de sincronização, de leitura de documentos ou da própria plataforma gera aviso ao administrador. | Proposta: Arquitetura funcional, Robusta e resiliente | Aprovado |
| RNF-08 | Núcleo e módulos que se encaixam conforme o serviço, não necessariamente microsserviços. O núcleo tem cadastros, fluxos, quadro de pendências, agenda, permissões, trilha de auditoria, indicadores e funcionamento sem internet. | Ligar ou desligar um módulo para um serviço não muda o núcleo nem os outros serviços. | Proposta: Arquitetura funcional. Entrevista: pedido 19 | Aprovado |
| RNF-09 | Aberta para crescer: aceita depois o envio por WhatsApp, o WhatsApp automatizado, o editor visual de fluxo e agentes de IA sem refazer o núcleo. | O desenho da etapa 5 mostra onde cada um desses módulos se encaixa. | Proposta: Princípios; Arquitetura funcional, Módulos do futuro. Entrevista: pedido 11 | Aprovado |
| RNF-10 | A leitura de documentos passa por uma camada própria, para trocar de fornecedor sem refazer nada. | Trocar o fornecedor de leitura muda só essa camada; formulários e telas seguem iguais. | Proposta: Pré-preenchimento e digitalização | Aprovado |
| RNF-11 | O fornecedor de leitura é escolhido por critério, entre eles boa leitura de letra de mão; os critérios de dados estão na LGPD-10 e na LGPD-11. | Na escolha, cada candidato é testado com amostras de fichas preenchidas à mão. | Proposta: Pré-preenchimento e digitalização | Aprovado |
| RNF-12 | Vários serviços na mesma plataforma, cada um com a sua configuração; a Escola Móvel é a primeira. | Dois serviços configurados de formas diferentes funcionam ao mesmo tempo sem um afetar o outro. | Proposta: Princípios. Entrevista: R1 P1, pedido 15 | Aprovado |
| RNF-13 | A plataforma atende, na primeira versão, um serviço (a Escola Móvel) com até 300 alunos e 20 professores, números que já têm folga, e fica fora do ar no máximo algumas horas por mês, fora do horário de aula, já que o uso sem internet cobre quedas curtas. | Um teste de carga com 300 alunos, 20 professores e a equipe de apoio usando ao mesmo tempo não mostra lentidão perceptível. O crescimento para outros serviços não foi dimensionado; a plataforma já nasce preparada para vários (RNF-12). | Proposta: Princípios, Robusta e resiliente. Resposta à P18 | Aprovado |
| RNF-14 | A plataforma segue a WCAG 2.2, nível AA. | Uma revisão de acessibilidade das telas principais não encontra falha de nível A nem AA. | Resposta à P23 | Aprovado |

## Requisitos de segurança

São 9 requisitos. A proposta fecha login individual, acesso por papel e por tipo de dado, trilha de auditoria e separação entre serviços; a proteção do login, do tablet usado pela família e dos dados guardados no aparelho veio das suas respostas às P19, P20 e P21.

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| SEG-01 | Cada pessoa da equipe entra com o próprio login; escola e família não têm login e chegam só por link. | Nenhuma tela com dados abre sem login, exceto o painel da escola e o termo da família, cada um pelo seu link. | Proposta: Segurança e níveis de acesso; Escola e família | Aprovado |
| SEG-02 | Cada pessoa vê só os dados que o papel permite, por tipo de dado (RF-07). | Um teste com cada papel da Escola Móvel confirma que nenhum dado fora da permissão aparece. | Proposta: Segurança e níveis de acesso | Aprovado |
| SEG-03 | Trilha de auditoria: quem validou cada informação, quem editou depois e por quê. | Editar um dado já validado pede o motivo; a trilha mostra a validação e cada edição com autor, data e motivo. | Proposta: Trilha de auditoria. Entrevista: R6 P5 | Aprovado |
| SEG-04 | Também ficam na trilha: liberação de permissões, mudança de situação do aluno, mudança de aluno de versão de fluxo e cada abertura do link da escola. | Cada um desses eventos aparece na trilha com autor, quando houver, e data. | Proposta: Segurança; Ciclo do aluno; Customização; Escola e família | Aprovado |
| SEG-05 | Os dados de cada serviço ficam separados dos outros; só a base de escolas é compartilhada. | Uma pessoa de um serviço não chega a nenhum dado de outro serviço, nem digitando o endereço direto. | Proposta: Arquitetura funcional, Robusta e resiliente; Cadastros, Escola de origem | Aprovado |
| SEG-06 | O link da escola é só de leitura, mostra só os alunos dela com autorização de contato válida ou provisória e pode ser cancelado e reenviado. O risco de encaminhamento foi aceito; as defesas são cancelar o link e o serviço escolher o que aparece. | Um aluno sem autorização não aparece; o link cancelado não abre. Se o link sem código basta é a LGPD-06. | Proposta: Escola e família. Entrevista: R3 P2, P3 e P4 | Aguarda advogado |
| SEG-07 | Proteção do login e dos dados da plataforma. | Senha forte, verificação em duas etapas para o administrador e quem configura, sessão que expira sem uso, e dados criptografados na rede e guardados. | Proposta: Princípios, Robusta e resiliente | Aprovado |
| SEG-08 | Quando a família assina no tablet do professor, ela não vê nada além do termo. | Um modo assinatura mostra só o termo e, ao terminar, volta pedindo o login do professor. | Proposta: Autorizações da família, tablet no leito | Aprovado |
| SEG-09 | Nenhum dado de aluno fica guardado no aparelho além da sessão aberta, porque a plataforma não funciona sem internet. | Depois de sair, o botão voltar do navegador não mostra dados de aluno, e desativar o login de uma pessoa encerra as sessões abertas dela. | Proposta: Experiência do usuário, Sem internet no leito | Aprovado |

## Requisitos de LGPD

São 13 requisitos; onze aguardam o advogado: os oito pontos da pesquisa jurídica da proposta, mais os meios do controlador, a prova do consentimento e os direitos da família, que você incluiu na pesquisa. Eles entram já numerados para que a experiência do usuário e a arquitetura reservem espaço para a resposta. Os artigos citados vêm da pesquisa na aba Entrevista e pesquisa, que não é parecer jurídico.

| ID | Requisito | Critério de aceite | Origem | Situação |
| --- | --- | --- | --- | --- |
| LGPD-01 | O serviço é o controlador dos dados e a EntreLaço, a operadora; a plataforma dá ao serviço os meios de indicar encarregado, manter registro das operações, proteger os dados e comunicar incidentes (arts. 37, 41, 46 e 48). | Quais meios exatamente, o advogado define. | Proposta: LGPD. Entrevista: R2 P6 | Aguarda advogado |
| LGPD-02 | Os termos pedem consentimento específico e destacado, com as duas autorizações separadas, dado pelo responsável legal (arts. 8º, 11 e 14). | O texto dos termos, o advogado escreve ou revisa. | Proposta: Em aberto, ponto 1 | Aguarda advogado |
| LGPD-03 | A plataforma guarda a prova de cada autorização: quem autorizou, o quê, quando, e que o documento não mudou depois, porque o ônus da prova é do serviço (art. 8º, § 2º). | Cada autorização tem responsável, termo e versão, data e hora, forma de coleta e quem colheu. A lista final de campos por forma, o advogado confirma. | Entrevista: LGPD e assinaturas | Aguarda advogado |
| LGPD-04 | A revogação vale a qualquer momento e para o envio na hora (art. 8º, § 5º). | Depois da revogação registrada, nada mais é enviado (RF-29). | Proposta: Autorizações da família | Aprovado |
| LGPD-05 | O sim provisório por WhatsApp sustenta o contato com a escola? | Resposta do advogado; até lá vale RF-27. | Proposta: Em aberto, ponto 2 | Aguarda advogado |
| LGPD-06 | O link da escola sem código atende ao dever de segurança, já que mostra dados de saúde? | Resposta do advogado; até lá vale SEG-06. | Proposta: Em aberto, ponto 3 | Aguarda advogado |
| LGPD-07 | Que nível de assinatura os documentos enviados a escolas públicas precisam, inclusive o atestado de aula (Lei 14.063/2020)? | Resposta do advogado; define RF-36 e RF-56. | Proposta: Em aberto, ponto 4 | Aguarda advogado |
| LGPD-08 | Por quanto tempo guardar o papel original depois da foto. | Resposta do advogado; vira regra de guarda no RF-12. | Proposta: Em aberto, ponto 5 | Aguarda advogado |
| LGPD-09 | O direito ao atendimento educacional no hospital (LDB, art. 4º-A) sustenta uma base legal sem consentimento para parte dos dados? | Resposta do advogado de cada serviço. | Proposta: Em aberto, ponto 6 | Aguarda advogado |
| LGPD-10 | A leitura de documentos manda só a foto ou o áudio do formulário, nunca o perfil inteiro do aluno. | O que sai para o serviço de leitura é só o arquivo do formulário, sem outros dados do aluno. | Proposta: Pré-preenchimento e digitalização | Aprovado |
| LGPD-11 | O serviço de leitura tem contrato que proíbe usar os dados para treinar modelos e servidores no Brasil, ou transferência internacional aprovada pelo jurídico (arts. 33 a 36). | Contrato e termos, o advogado revisa antes de ligar o módulo. | Proposta: Pré-preenchimento; Em aberto, ponto 7 | Aguarda advogado |
| LGPD-12 | O ECA Digital (Lei 15.211/2025) se aplica, caso famílias ou crianças passem a usar a plataforma? | Resposta do advogado; na primeira versão a família só assina por link. | Proposta: Em aberto, ponto 8 | Aguarda advogado |
| LGPD-13 | Direitos da família sobre os dados (acesso, correção, exclusão) e prazo de guarda depois que o aluno é encerrado. | Entra na pesquisa jurídica como nono ponto, pela sua resposta à P22. | Nova, não está na proposta | Aguarda advogado |

## Perguntas para você

Você respondeu as 23 perguntas em 12/10/2026, todas com a opção recomendada, e as respostas já estão nos requisitos. Os números da P18 vieram depois: um serviço, 300 alunos e 20 professores, já com folga.

### Rodada 1: no leito e com a família

| # | Pergunta | Opções | Afeta | Sua resposta |
| --- | --- | --- | --- | --- |
| P1 | O que o professor faz sem internet no leito? | a) ★ Cadastro, autorização no tablet, registro de aula com fotos, ver agenda e pendências; a leitura por OCR ou IA e os envios esperam a rede. b) Tudo, inclusive a leitura por OCR ou IA. c) Só o registro de aula. | RNF-02 | a |
| P2 | Quando duas pessoas mudam o mesmo dado sem internet, como se resolve? | a) ★ Quem sincroniza por último vê as duas versões e escolhe. b) Vale a última, e as duas pessoas são avisadas. | RNF-04 | a |
| P3 | O salvamento imediato vale para o que veio pré-preenchido? | a) ★ O que a pessoa digita salva na hora; o que veio de foto, áudio ou IA fica “a validar” e só vira dado do aluno quando ela confirma. b) Tudo salva na hora como dado do aluno, e a validação vem depois. | RF-52 | a |
| P4 | O que o agente que ajuda a validar faz na primeira versão? | a) ★ Marca os campos em que a leitura ficou em dúvida, para a pessoa conferir primeiro. b) Além disso, compara com dados que o aluno já tem e aponta diferenças. c) Conversa com a pessoa para corrigir. | RF-53 | a |
| P5 | Além de tablet e celular, a plataforma roda no computador? | a) ★ Sim, com a mesma tela adaptada, para quem configura, a coordenação e o apoio administrativo. b) Não, só tablet e celular. | RNF-01 | a |
| P6 | Sem o envio por WhatsApp na primeira versão, como o link da escola e o sim provisório passam pelo WhatsApp? | a) ★ A plataforma gera o link e a pessoa manda pelo WhatsApp de trabalho dela; o sim provisório é registrado anexando a conversa. b) Esses dois casos esperam o módulo de WhatsApp. | RF-26, RF-32 | a |
| P7 | Como o link de assinatura chega ao celular da família? | a) ★ Por e-mail pela plataforma, ou copiado pela equipe para o WhatsApp de trabalho. b) Também por SMS enviado pela plataforma, um módulo a mais. | RF-26 | a |
| P8 | Cada autorização tem as situações pendente, provisória, válida, recusada e revogada, como sugerido na entrevista? | a) ★ Sim, e pendente e provisória viram tarefa para quem colheu. b) Outra lista. | RF-25 a RF-29 | a |

### Rodada 2: regras do dia a dia

| # | Pergunta | Opções | Afeta | Sua resposta |
| --- | --- | --- | --- | --- |
| P9 | O que é urgente nos alertas do dia e o que é tarefa parada? | a) ★ Urgente: vence hoje ou já venceu. Parada: sem movimento há 7 dias, prazo configurável pelo serviço. b) Outra definição. | RF-41, RF-42, RF-54 | a |
| P10 | A conexão com Google e Outlook vai em que sentido? | a) ★ Mão única, da plataforma para a agenda externa. b) Mão dupla, e um evento criado no Google vira aula na plataforma. | RF-45 | a |
| P11 | De onde vêm os dias de internação usados na prioridade? | a) ★ De um campo de data de internação na ficha, que o professor preenche e atualiza. b) Do sistema do hospital, o que pede integração, como a do Tasy. | RF-46 | a |
| P12 | Como a plataforma sabe que o aluno é do TMO, para criar a tarefa do professor domiciliar? | a) ★ Um campo na ficha diz a unidade ou o tipo de tratamento; saída por alta com TMO marcado cria a tarefa. b) Um motivo de saída próprio, “alta do TMO”. | RF-24 | a |
| P13 | A troca de escola do aluno entra na primeira versão? Ela estava no ciclo da entrevista, mas não na proposta final. | a) ★ Sim: trocar a escola tira o aluno do painel antigo e dispara carta e link para a nova, com a revisão de escolas no início do ano. b) Fica para depois. | Novo RF | a |
| P14 | O contato da escola confirmado por um serviço aparece para os outros serviços? | a) ★ Não, cada serviço vê só o contato que confirmou; a base pública é que é comum. b) Sim, o contato confirmado vira ponto de partida para todos. | RF-14, SEG-05 | a |
| P15 | Quem vê os indicadores e com que recorte? | a) ★ Coordenação e quem configura, por mês e por professor. b) Toda a equipe. c) Outro recorte. | RF-54 | a |

### Rodada 3: números e segurança

| # | Pergunta | Opções | Afeta | Sua resposta |
| --- | --- | --- | --- | --- |
| P16 | Por quanto tempo a plataforma tenta reenviar um e-mail antes de virar tarefa? | a) ★ Por 24 horas. b) Outro prazo. | RNF-05 | a |
| P17 | Quanto tempo guardar as cópias de segurança e a cada quanto testar a restauração? | a) ★ 30 dias de cópias, teste mensal. b) Outro prazo. | RNF-06 | a |
| P18 | Quantos serviços, pessoas e alunos ativos na primeira versão e em dois anos, e quanto tempo fora do ar é aceitável? | Resposta livre para os números. Para o tempo fora do ar: a) ★ Algumas horas por mês, fora do horário de aula, porque o uso sem internet cobre quedas curtas. b) Quase nunca, o que encarece a hospedagem. | RNF-13 | a |
| P19 | Que proteção de login e de dados a plataforma tem? | a) ★ Senha forte, verificação em duas etapas para o administrador e quem configura, sessão que expira sem uso e dados criptografados na rede e guardados. b) Verificação em duas etapas para todos. | SEG-07 | a |
| P20 | Quando a família assina no tablet do professor, como se protege o resto? | a) ★ Um modo assinatura mostra só o termo e, ao terminar, volta pedindo o login do professor. b) Só o termo na tela, sem pedir login de novo. | SEG-08 | a |
| P21 | O que protege os dados guardados no aparelho se ele for perdido? | a) ★ Os dados no aparelho ficam criptografados, só o necessário fica guardado, e desativar o login da pessoa apaga esses dados na próxima conexão. b) Só a criptografia. | SEG-09 | a |
| P22 | Os direitos da família sobre os dados e o prazo de guarda depois do encerramento entram na pesquisa jurídica? | a) ★ Sim, como nono ponto. b) Não agora. | LGPD-13 | a |
| P23 | A plataforma segue um padrão de acessibilidade? | a) ★ Sim, WCAG 2.2 nível AA, o padrão de referência para sites. b) Não como requisito agora. | Novo RNF | a |

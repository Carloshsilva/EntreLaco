# Jornada: registrar a aula no leito

Situação: rascunho (exemplo do formato, a revisar com os professores) · Papel principal: Professor ·
Requisitos: RF-15, RF-19, RF-43, RF-46

## Contexto

O professor acabou de atender uma criança no leito. Está de pé, com o celular, e tem poucos minutos
antes do próximo atendimento. Às vezes a criança ainda não tem cadastro completo.

## Objetivo

"Deixar a aula registrada antes de esquecer, e saber quem atendo agora."

## Passo a passo

| # | A pessoa | A plataforma | Tela |
| --- | --- | --- | --- |
| 1 | Abre a plataforma. | Mostra a agenda de hoje com a aula marcada no topo. | [Início](../telas/inicio.md) |
| 2 | Toca na aula marcada. | Abre o registro já com aluno, data e horário preenchidos. | Registrar aula |
| 3 | Escreve o que foi feito e tira foto da atividade. | Guarda as fotos junto da aula. | Registrar aula |
| 4 | Toca em "Registrar aula". | Salva, avisa "Aula registrada." e, se a ficha estiver incompleta, cria a pendência para ele. | Início |
| 5 | Vê quem é o próximo. | Mostra o próximo aluno da ordem de atendimento e o motivo. | Início |

## Caminhos alternativos e falhas

- **Aula não estava marcada:** começa por "Registrar aula" e escolhe o aluno pela busca.
- **Aluno sem cadastro:** registra mesmo assim; nasce a pendência da ficha e do termo (RF-19).
- **A aula não aconteceu:** toca em "A aula não aconteceu" e escolhe o motivo.
- **Internet caiu:** a definir. Hoje o registro se perde; ver pergunta abaixo.

## O que dói hoje no protótipo

- A completar com o feedback dos professores.

## Perguntas em aberto

- O registro deve funcionar sem internet e enviar depois? Recomendo que sim, porque o hospital pode
  ter sinal ruim.
- O próximo aluno aparece logo depois de salvar, ou o professor prefere voltar ao Início?

# Tela: Início

Situação: rascunho (exemplo do formato, descreve o protótipo) · Endereço hoje: `/` ·
Jornadas: [registrar a aula no leito](../jornadas/professor-registra-aula-no-leito.md) ·
Requisitos: RF-43, RF-08

## Para que serve

A primeira tela de todos: o que cada pessoa precisa fazer hoje.

## Quem usa e de onde

| Papel | Aparelho | O que vê de diferente |
| --- | --- | --- |
| Professor | Celular | Agenda de hoje com as aulas marcadas. |
| Supervisão e Coordenação | Computador | Alterna entre "Minhas" e "De todos" nas pendências. |
| Demais papéis | Computador | Só as próprias pendências. |

## O que a tela mostra

1. Saudação com o nome e a data de hoje.
2. Ações principais: "Registrar aula" e "Cadastrar aluno", conforme a permissão.
3. Pendências: total, quantas vencidas e quantas para hoje, e a lista.
4. Agenda de hoje e dos próximos dias, com "Ver a semana".

## Ações

| Ação | Texto do botão | Para onde leva |
| --- | --- | --- |
| Principal | "Registrar aula" | Registrar aula |
| Secundária | "Cadastrar aluno" | Cadastrar aluno |
| Filtro | "Minhas" / "De todos" | Mesma tela, filtrada |
| Ver mais | "Ver a semana" | Agenda |

## Estados

- **Sem pendências:** "Nenhuma pendência agora."
- **Agenda vazia:** "Nada marcado para hoje."

## Mudanças em relação ao protótipo

- A definir com o feedback.

## Perguntas em aberto

- No celular, o que vem primeiro para o professor: a agenda ou as pendências?

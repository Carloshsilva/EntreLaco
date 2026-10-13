# EntreLaço: experiência do usuário

Esta pasta descreve, em texto, como a EntreLaço deve ser usada: quem faz o quê, em que ordem, em qual
tela, e o que a tela mostra. A versão no ar é tratada como protótipo. A identidade visual dela fica
(cores, fonte, ícones, tom dos textos, componentes de `docs/arquitetura.md`); o que muda aqui é o
caminho de cada pessoa e o que cada tela faz.

O texto vem antes do código. Quando uma jornada e as telas dela estiverem aprovadas, elas viram a
especificação para refazer ou ajustar a plataforma.

## Como a pasta se organiza

| Pasta ou arquivo | O que tem |
| --- | --- |
| `papeis.md` | Quem usa a plataforma, o que precisa dela e de onde usa (celular no leito, computador na sala). |
| `inventario.md` | As telas que existem hoje no protótipo, com o endereço, para servir de ponto de partida. |
| `jornadas/` | Um arquivo por jornada: uma tarefa real de ponta a ponta, contada passo a passo por um papel. |
| `telas/` | Um arquivo por tela: objetivo, quem usa, o que mostra, ações, estados e textos. |
| `feedback/` | Um arquivo por rodada de conversa com a equipe, com cada comentário numerado. |
| `decisoes.md` | O que foi decidido, por quem e por quê, numerado (D-01, D-02…). |
| `_modelos/` | Os modelos em branco de jornada, tela e feedback. |

## Ordem de trabalho

1. **Papéis.** Confirmar quem usa e de onde (`papeis.md`).
2. **Jornadas.** Escrever as jornadas principais de cada papel. A jornada diz o caminho; ainda não
   desenha tela.
3. **Feedback.** Cada comentário da equipe entra em `feedback/` com um número (F-01, F-02…) e é
   ligado à jornada ou tela que ele afeta.
4. **Telas.** Das jornadas aprovadas saem as telas. Cada tela cita as jornadas que passam por ela e os
   requisitos (`RF-…` de `docs/requisitos.md`) que atende.
5. **Decisões.** Quando um comentário muda o rumo, a decisão vai para `decisoes.md` e a jornada ou
   tela passa a citá-la.

## Como o feedback entra

- Todo comentário vira uma linha em `feedback/AAAA-MM-DD-<quem ou onde>.md`, com as palavras da
  pessoa, o papel dela e a jornada ou tela a que se refere.
- Cada linha tem uma situação: **novo**, **aceito** (virou mudança em jornada ou tela), **decidir**
  (precisa de decisão do Carlos) ou **fora** (não entra, com o motivo).
- A jornada ou tela mudada cita o número do feedback (por exemplo, "muda por F-07"), para que se
  saiba de onde veio cada mudança.

## Convenções

- Escrito em português, com as palavras que a equipe usa ("aula", "leito", "pendência", "ficha").
- Papel sempre pelo nome: Supervisão, Coordenação, Orientação pedagógica, Professor, Apoio
  administrativo, Voluntário, Escola, Família.
- Textos de tela entre aspas e no tom do design system: verbo primeiro nos botões, sem exclamação,
  sem jargão.
- Situação de cada arquivo no topo: **rascunho**, **em revisão** ou **aprovado**.

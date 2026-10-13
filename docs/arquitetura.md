# Arquitetura da EntreLaço (primeira versão)

Este documento é o contrato do código: quem mexe em uma app segue estas regras para que todas as telas
pareçam uma só e para que permissão, trilha de auditoria e separação entre serviços valham em todo lugar.
Os requisitos citados (RF, RNF, SEG, LGPD) estão em [requisitos.md](requisitos.md).

## Tecnologia

- Django 5.2 (LTS), Python 3.12+, PostgreSQL em produção e no CI, SQLite só para desenvolvimento local.
- HTMX 2.0.11 (arquivo em `static/js/htmx.min.js`, sem CDN). Página inteira renderizada no servidor;
  o `<body hx-boost="true">` deixa a navegação e os formulários mais rápidos, e tudo funciona sem JavaScript.
- Sem framework de CSS: `static/css/tokens.css` (cores, espaços, fontes, tema claro e escuro) e
  `static/css/app.css` (classes `el-`). Fonte Atkinson Hyperlegible Next e Mono, servidas pelo próprio site.
- Ícones Lucide num sprite (`static/img/icones.svg`), com nomes em português; use `{% icone "nome" %}`.
- Nada de dado real: a faixa "Ambiente de teste" aparece enquanto `ENTRELACO_AMBIENTE_DE_TESTE` for verdadeiro.

## Apps

| App | O que cuida | Requisitos |
| --- | --- | --- |
| `core` | Serviço, pessoa (`Usuario`), papel, vínculo, permissões, trilha, login, duas etapas, início, agenda, pontos de encaixe | RF-01 a RF-08, RF-43, RF-44, SEG-01 a SEG-09 |
| `equipe` | Pessoas da equipe e papéis (telas do serviço), perfil do professor, componentes curriculares, configuração do serviço | RF-05, RF-06, RF-09, RF-48, RF-62 |
| `escolas` | Base nacional de escolas (comum) e o contato confirmado por serviço | RF-13, RF-14 |
| `alunos` | Ficha, responsáveis, situação (ativo, em pausa, encerrado), saída, ordem de atendimento | RF-10, RF-11, RF-19 a RF-22, RF-24, RF-46 |
| `autorizacoes` | Termos com versão e as autorizações da família, com o modo assinatura no tablet | RF-25 a RF-29, RF-64, SEG-08, LGPD-03 |
| `aulas` | Aula marcada e registrada, fotos, lista da BNCC, equivalência em aulas | RF-15, RF-16, RF-19, RF-55 |
| `reunioes` | Reuniões com pauta e ata e as citações de alunos | RF-17 |
| `documentos` | Fotos e scans no histórico do aluno | RF-12 |

## Regras que valem para todo código

### 1. Separação entre serviços (SEG-05)

- Todo modelo com dado de um serviço herda `core.models.ModeloDoServico` (campos `servico`, `criado_por`,
  `atualizado_por`, `criado_em`, `atualizado_em`, `versao`). A única exceção é `escolas.Escola`, a base pública comum.
- Toda consulta filtra por `request.servico`. Em views de classe, use `DoServicoMixin`; em funções,
  `get_object_or_404(Modelo, pk=pk, servico=request.servico)`. Objeto de outro serviço dá **404**, nunca 403.
- Chaves estrangeiras escolhidas em formulário (aluno, professor, escola de contato, componente, habilidade)
  também são filtradas pelo serviço no `queryset` do campo. Pessoas do serviço:
  `Usuario.objects.filter(vinculos__servico=servico, vinculos__ativo=True, is_active=True)`.

### 2. Permissão por tipo de dado (RF-07, SEG-02)

- `core/permissoes.py` define os tipos de dado (`GRUPOS_DE_DADOS`) e as ações (`ACOES`). Cada papel diz,
  por tipo, se a pessoa não vê, vê ou edita.
- Cada modelo declara `GRUPOS_DE_CAMPOS = {tipo: [campos]}`. Todo campo que aparece em tela precisa estar
  em um tipo. `campos_permitidos(Modelo, request.acesso, "ver"|"editar")` diz o que mostrar ou editar.
- Telas: `AcessoMixin` com `grupo` e `modo`, ou `acao`, ou `exige_configurar`. Tela que só exige login e
  serviço declara `so_login = True`, de propósito; tela com regra própria sobrescreve `tem_permissao`.
  Sem nenhuma dessas declarações, a tela levanta `ImproperlyConfigured`. Telas de cadastro e edição
  (os mixins de auditoria) sempre exigem editar o `grupo`, qualquer que seja a ordem dos mixins.
  Views em função conferem `request.acesso.pode_ver(grupo)`, `pode_editar(grupo)` e `tem(acao)` e
  levantam `PermissionDenied`.
- Quem cuida da equipe sem configurar o serviço só dá papéis e só mexe em pessoas cujo acesso cabe no
  dela (`Acesso.cobre`): nenhum tipo de dado a mais, nenhuma ação a mais.
- Templates: `{% if acesso|pode_ver:"sensivel" %}`, `{% if acesso|pode_editar:"aulas" %}`,
  `{% if acesso|tem_acao:"mudar_situacao" %}`. Botão que a pessoa não pode usar não aparece.
- Um dado escondido some de tudo: tela, lista, busca, resumo, PDF e trilha (`auditoria.preparar_para_exibir`).

### 3. Trilha de auditoria (SEG-03, SEG-04)

- Criar: `CriarComAuditoriaMixin`. Editar: `EditarComAuditoriaMixin` (pede "Por que você está alterando?",
  grava o motivo e detecta conflito). Em views próprias, chame `core.auditoria.registrar(...)` **dentro da
  mesma transação** da mudança, com `mudancas=auditoria.comparar(Modelo, antes, depois)`.
- Também vão para a trilha: mudança de situação do aluno (`Acao.MUDOU_SITUACAO`), autorização colhida ou
  revogada (`Acao.ASSINOU`/`Acao.ALTEROU`), abertura de documento (`Acao.BAIXOU_ARQUIVO`), validação
  (`Acao.VALIDOU`), papel e permissão (`Acao.MUDOU_PAPEL`, `Acao.LIBEROU_PERMISSAO`) e exclusão (`Acao.EXCLUIU`).
- Cada evento guarda o tipo de dado do registro (`grupo`): o único tipo de `GRUPOS_DE_CAMPOS`, ou o que o
  modelo devolve em `grupo_na_trilha()`. Ele pode devolver vários tipos: a citação em ata grava
  "atas+sensivel", e só vê o evento quem vê todos eles. Quem não vê o tipo não vê o evento, nem o motivo.
  Consultas de eventos passam por `auditoria.filtrar_visiveis(queryset, request.acesso)`. O nome do
  registro de um aluno só aparece na trilha para quem vê a identificação. Em modelos com vários tipos (a ficha do aluno), cada mudança é filtrada
  campo a campo, e o motivo só aparece para quem vê alguma das mudanças.
- Para mudar o que vai para a trilha (por exemplo, nomes em vez de ids), sobrescreva
  `mudancas_para_trilha(obj, mudancas)` no mixin de criar ou editar.
- Lista de eventos montada à mão passa sempre por `auditoria.preparar_para_exibir(eventos, request.acesso)`.
- Na tela de um registro, mostre o histórico com
  `{% include "core/_trilha.html" with eventos=eventos %}`, onde `eventos = core.views.eventos_do_objeto(request, obj)`
  (ou `eventos_do_aluno(request, aluno.pk)` no perfil do aluno).
- Excluir é raro: prefira desativar. Quando excluir, registre `Acao.EXCLUIU` com o `objeto_repr`.

### 4. Conflito de edição (RNF-04)

`EditarComAuditoriaMixin` resolve sozinho, desde que o template use `core/_formulario.html` (ou inclua o
campo escondido `estado_original` e `core/_conflito.html`). Campo que só a outra pessoa mudou fica com o
valor dela; campo que as duas mudaram mostra as duas versões e nada é salvo até a pessoa escolher.

### 5. Pontos de encaixe (`core/registro.py`)

Cada app registra no seu `encaixes.py` (importado pelo `ready()` do AppConfig):

- `registrar_menu(ItemDeMenu(...))`: item do menu lateral e da barra de baixo (já feito para todas as apps).
  `grupo` exige ver um tipo de dado; `grupos=(...)` exige ver todos os tipos da lista.
- `registrar_secao_do_aluno(SecaoDoAluno(chave, titulo, template, contexto, grupo, ordem))`: uma seção do
  perfil do aluno. `contexto(request, aluno)` devolve um dicionário (ou `None` para esconder). O perfil
  desenha cada seção como `<section id="secao-{chave}" class="el-card">` com o título num `h2`, e inclui o
  template da seção com `dados` (o dicionário), `aluno`, `acesso` e `request`. O template da seção não
  repete o título; dentro dele, use `h3`. O `manage.py check` acusa (`entrelaco.E001`) seção cujo
  template não existe.
  Ordem combinada: ficha 10, responsáveis 20, autorizações 30, aulas 40, citações em reunião 50,
  documentos 60, situação 70, histórico de alterações 90.
- `registrar_fonte_de_pendencias(funcao)`: `funcao(request, usuario, todas)` devolve uma lista de
  `Pendencia`. Com `todas=True` (quem tem `ver_tarefas_de_todos`), devolve as de todo o serviço, com
  `responsavel` preenchido. Pendências são calculadas, não guardadas, nesta versão.
- `registrar_fonte_da_agenda(funcao)`: `funcao(request, inicio, fim, usuario)` devolve uma lista de
  `EventoDaAgenda`. Com `usuario=None`, devolve os do serviço todo. Confira `request.acesso` antes.

### 6. Arquivos (fotos, documentos, assinaturas)

- `core/arquivos.py`: `validar_foto(arquivo)` limpa o EXIF e reduz; `validar_documento(arquivo)` aceita foto
  ou PDF; `resumo_sha256(arquivo)` gera a impressão digital; `servir_arquivo(campo, nome)` entrega o arquivo.
- Os arquivos ficam em `MEDIA_ROOT`, fora da pasta pública, e **só** saem por uma view que confere login,
  serviço e permissão. Nunca use `.url` de um arquivo em template; aponte para a view de download.
- Links para arquivos levam `hx-boost="false"`.
- O tipo do arquivo vem do conteúdo, e o nome guardado tem a extensão certa (um PDF é sempre `.pdf`). Na
  entrega, só JPG, PNG, WEBP, PDF e TXT saem com o próprio tipo (`tipo_do_arquivo`); o resto desce como
  arquivo genérico. Só imagens abrem na aba.

## Telas: padrão visual e de acessibilidade (WCAG 2.2 AA)

- Toda tela estende `base.html` e define `{% block titulo %}` e `{% block conteudo %}`; telas de
  formulário ou leitura usam `{% block largura %}el-page-narrow{% endblock %}`.
- Cabeçalho da tela:
  ```html
  <header class="el-pagehead">
    <div class="el-pagehead-text">
      <p class="el-breadcrumb"><a href="...">{% icone "seta-voltar" %}Alunos</a></p>
      <h1 class="el-display">Título da tela</h1>
      <p class="el-muted">Linha de apoio, se precisar.</p>
    </div>
    <div class="el-pagehead-actions"><a class="el-btn el-btn-primary" href="...">{% icone "mais" %}Ação principal</a></div>
  </header>
  ```
  Um único `h1` por tela; seções com `h2`, e cartões dentro delas com `h3`.
- Formulário: `{% include "core/_formulario.html" with botao="Salvar ficha" cancelar=url_de_volta secoes=secoes colunas=True %}`.
  `secoes` é uma lista de `{"titulo", "campos", "ajuda"}` montada na view. Para um campo solto, use
  `{% include "core/_campo.html" with campo=form.nome %}`. Rótulo visível, "(obrigatório)" no rótulo,
  dica e erro ligados por `aria-describedby`, resumo de erros no topo com links para os campos.
- Classes: botões `el-btn el-btn-primary|secondary|quiet|danger` (no máximo um `primary` por tela);
  cartões `el-card`; listas `el-list`, `el-list-plain`, `el-item-link`; tabelas `el-table-wrap` +
  `el-table el-table-stack` (com `data-label` em cada `td`, para virar cartão no celular); selos `el-badge`
  + `el-badge-laco|fita|success|danger`; avisos `el-alert el-alert-info|success|warning|error`; vazio
  `el-empty`; definições `el-dl` (`el-dl-cols` em duas colunas); filtros `el-filters`; abas `el-tabs`;
  resumo do aluno `el-student`, `el-student-flags`, `el-flag`, `el-flag-attention`; galeria `el-gallery`.
- Situação sempre com palavra, nunca só cor: ativo `el-badge-success`, em pausa `el-badge-fita`,
  encerrado `el-badge`; autorização válida `success`, provisória e pendente `fita`, recusada e revogada `danger`.
- Mensagens depois de salvar: `messages.success(request, "Ficha salva.")`. Texto no tom do design system:
  verbo primeiro nos botões ("Salvar ficha", "Registrar aula"), sem exclamação, sem jargão.
- Nome do aluno em listas: `aluno.nome_curto` ("Lia M."); completo só no perfil.
- Datas: `{{ data|date:"d/m/Y" }}`; horas: `{{ hora|time:"H:i" }}`.
- Busca enquanto digita: `<input type="search" ... hx-get="..." hx-trigger="input changed delay:300ms, search"
  hx-target="#resultados" hx-push-url="true">`; a mesma view devolve só o trecho `#resultados` quando
  `request.htmx` é verdadeiro (use `django_htmx`), e a página inteira quando não é. Os resultados ficam
  num `<div id="resultados" aria-live="polite">`.
- CSS e JavaScript próprios de uma app vão em `static/css/modulos/<app>.css` e `static/js/modulos/<app>.js`
  (já carregados em todas as telas). `static/css/app.css` e `static/js/app.js` são do núcleo.
- Proibido pela política de conteúdo: estilo inline (`style=`), `<script>` inline, `hx-on`, `onclick` e
  recursos de outros domínios. Comportamento novo vai em `static/js/app.js`, iniciado por `htmx.onLoad`.
- Áreas de toque de pelo menos 48px (as classes já garantem). Nada rola de lado na página inteira.

## Formulários

- Base: `core.formularios.ModeloFormularioBase` (aplica as classes e o `required`). Para formulários de
  edição com permissão por campo, use `formulario_para(...)` (é o que os mixins fazem).
- Datas com `core.formularios.DATA` e horas com `core.formularios.HORA` em `widgets`.
- Mensagens de erro dizem o que houve e como resolver: "Falta a data da saída. Preencha para encerrar o aluno."

## Testes

- `python manage.py test` (sem variáveis: os testes rodam com SQLite e chave de teste).
- `core/testes.py` cria serviço, papéis (professor, supervisão, apoio), pessoas, escolas e alunos inventados.
- Cada tela tem ao menos: abre para quem pode; dá 403 para quem não pode; dá 404 para objeto de outro
  serviço; salvar grava a trilha; e, onde houver dado sensível, o apoio administrativo não o vê.

## O que fica para depois

Quadro de pendências com Kanban, backlog e regras configuráveis (RF-38 a RF-42, RF-60); comunicação com a
escola e o painel vivo (RF-23, RF-30 a RF-37); link de assinatura para o celular da família (RF-26, forma
"link"); leitura por foto, áudio e IA (RF-51 a RF-53); notificações por e-mail e push (RF-47, RF-49, RF-50);
agenda externa (RF-45); indicadores e atestado (RF-54, RF-56, RF-57); formulários, fluxos e modelos
configuráveis (RF-58 a RF-61, RF-63); mudança manual da ordem de atendimento (RF-46); salvamento de cada
campo na hora (RNF-03, hoje o formulário inteiro é enviado e, sem internet, fica na tela até a conexão voltar);
convite com aceite para incluir na equipe quem já trabalha em outro serviço (hoje o vínculo é criado na hora
pelo e-mail; com um serviço só, isso não acontece).

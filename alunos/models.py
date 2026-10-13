from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import ModeloDoServico


class Aluno(ModeloDoServico):
    """Ficha do aluno (RF-10, RF-11).

    Só o nome é obrigatório para existir: o professor pode registrar aula antes
    do cadastro completo, e o que falta vira pendência (RF-19). Os campos e as
    opções partem do que a proposta cita da ficha da Escola Móvel e são ponto de
    partida para a equipe ajustar; formulários configuráveis (RF-58) vêm depois.
    """

    class Situacao(models.TextChoices):
        ATIVO = "ativo", "Ativo"
        PAUSA = "pausa", "Em pausa"
        ENCERRADO = "encerrado", "Encerrado"

    class Condicao(models.TextChoices):
        SEM_ALTERACAO = "sem_alteracao", "Sem alteração"
        COM_ALTERACAO = "com_alteracao", "Com alteração"
        NAO_AVALIADO = "nao_avaliado", "Ainda não avaliado"

    class Alfabetizacao(models.TextChoices):
        NAO_ALFABETIZADO = "nao_alfabetizado", "Não alfabetizado"
        EM_ALFABETIZACAO = "em_alfabetizacao", "Em alfabetização"
        ALFABETIZADO = "alfabetizado", "Alfabetizado"
        NAO_SE_APLICA = "nao_se_aplica", "Não se aplica pela idade"
        NAO_AVALIADO = "nao_avaliado", "Ainda não avaliado"

    class Reprovacao(models.TextChoices):
        NUNCA = "nunca", "Nunca reprovou"
        JA_REPROVOU = "ja_reprovou", "Já reprovou"
        NAO_INFORMADO = "nao_informado", "Não informado"

    class RacaCor(models.TextChoices):
        # Categorias do IBGE, por autodeclaração do responsável.
        BRANCA = "branca", "Branca"
        PRETA = "preta", "Preta"
        PARDA = "parda", "Parda"
        AMARELA = "amarela", "Amarela"
        INDIGENA = "indigena", "Indígena"
        NAO_DECLARADA = "nao_declarada", "Prefere não declarar"

    class AnoEscolar(models.TextChoices):
        INFANTIL = "infantil", "Educação infantil"
        ANO_1 = "1ano", "1º ano"
        ANO_2 = "2ano", "2º ano"
        ANO_3 = "3ano", "3º ano"
        ANO_4 = "4ano", "4º ano"
        ANO_5 = "5ano", "5º ano"
        ANO_6 = "6ano", "6º ano"
        ANO_7 = "7ano", "7º ano"
        ANO_8 = "8ano", "8º ano"
        ANO_9 = "9ano", "9º ano"
        EM_1 = "1em", "1ª série do ensino médio"
        EM_2 = "2em", "2ª série do ensino médio"
        EM_3 = "3em", "3ª série do ensino médio"
        EJA = "eja", "EJA"

    # Identificação
    nome = models.CharField("nome completo", max_length=150)
    nome_social = models.CharField("nome social ou como gosta de ser chamado", max_length=150, blank=True)
    data_nascimento = models.DateField("data de nascimento", null=True, blank=True)
    unidade = models.CharField(
        "unidade de atendimento", max_length=80, blank=True,
        help_text="Onde a criança está: internação, ambulatório, casa de apoio…",
    )
    leito = models.CharField(max_length=20, blank=True)
    data_internacao = models.DateField(
        "data de internação", null=True, blank=True,
        help_text="Atualize a cada nova internação. Entra na ordem de atendimento (RF-46).",
    )
    situacao = models.CharField(
        "situação", max_length=12, choices=Situacao.choices, default=Situacao.ATIVO, editable=False
    )
    situacao_desde = models.DateField("na situação desde", default=timezone.localdate, editable=False)

    # Condições e aprendizagem (em destaque no perfil, RF-10)
    visao = models.CharField("visão", max_length=20, choices=Condicao.choices, default=Condicao.NAO_AVALIADO)
    audicao = models.CharField("audição", max_length=20, choices=Condicao.choices, default=Condicao.NAO_AVALIADO)
    fala = models.CharField(max_length=20, choices=Condicao.choices, default=Condicao.NAO_AVALIADO)
    motricidade = models.CharField(max_length=20, choices=Condicao.choices, default=Condicao.NAO_AVALIADO)
    alfabetizacao = models.CharField(
        "alfabetização", max_length=20, choices=Alfabetizacao.choices, default=Alfabetizacao.NAO_AVALIADO
    )
    reprovacao = models.CharField(
        "reprovação", max_length=20, choices=Reprovacao.choices, default=Reprovacao.NAO_INFORMADO
    )
    condicoes_observacoes = models.TextField(
        "detalhes das condições e da aprendizagem", blank=True,
        help_text="Por exemplo: usa óculos, precisa de letra ampliada, reprovou no 3º ano.",
    )

    # Saúde e dados sensíveis
    diagnostico = models.TextField("diagnóstico", blank=True)
    tratamento = models.CharField(
        "unidade ou tipo de tratamento", max_length=120, blank=True, help_text="Por exemplo: oncologia, quimioterapia."
    )
    tmo = models.BooleanField(
        "em tratamento de TMO (transplante de medula óssea)", default=False,
        help_text="Na saída por alta, nasce a tarefa de ver se precisa de professor domiciliar (RF-24).",
    )
    raca_cor = models.CharField(
        "raça ou cor (autodeclarada)", max_length=20, choices=RacaCor.choices, blank=True
    )
    observacoes_saude = models.TextField("observações de saúde", blank=True)

    # Vida escolar
    escola = models.ForeignKey(
        "escolas.Escola", on_delete=models.PROTECT, null=True, blank=True, related_name="alunos",
        verbose_name="escola de origem",
    )
    sem_matricula = models.BooleanField(
        "não tem matrícula em escola", default=False,
        help_text="A orientação pedagógica acompanha até a matrícula (RF-20).",
    )
    ano_escolar = models.CharField("ano escolar", max_length=10, choices=AnoEscolar.choices, blank=True)
    turma = models.CharField(max_length=40, blank=True)
    ra = models.CharField("RA ou número de matrícula", max_length=40, blank=True)
    risco_evasao = models.BooleanField(
        "risco de evasão", default=False, help_text="Marca ligada pelo professor ou pela orientação (RF-46)."
    )
    risco_evasao_motivo = models.CharField("motivo do risco de evasão", max_length=255, blank=True)

    GRUPOS_DE_CAMPOS = {
        "identificacao": [
            "nome", "nome_social", "data_nascimento", "unidade", "leito", "data_internacao", "situacao",
            "situacao_desde",
        ],
        "aprendizagem": [
            "visao", "audicao", "fala", "motricidade", "alfabetizacao", "reprovacao", "condicoes_observacoes",
        ],
        "sensivel": ["diagnostico", "tratamento", "tmo", "raca_cor", "observacoes_saude"],
        "escolar": ["escola", "sem_matricula", "ano_escolar", "turma", "ra", "risco_evasao", "risco_evasao_motivo"],
    }

    class Meta:
        verbose_name = "aluno"
        verbose_name_plural = "alunos"
        ordering = ["nome"]
        indexes = [models.Index(fields=["servico", "situacao"]), models.Index(fields=["servico", "nome"])]

    def __str__(self):
        return self.nome

    @property
    def nome_curto(self):
        """Nome com sobrenome abreviado, para listas: "Lia M."."""
        partes = (self.nome_social or self.nome).split()
        if len(partes) >= 2:
            return f"{partes[0]} {partes[-1][0]}."
        return self.nome_social or self.nome

    @property
    def idade(self):
        if not self.data_nascimento:
            return None
        hoje = timezone.localdate()
        nascimento = self.data_nascimento
        return hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))

    def faltas_da_ficha_por_grupo(self):
        """O que falta para a ficha estar completa (RF-19), com o tipo de dado de cada item.

        Lista de (tipo de dado, rótulo). O tipo serve para não mostrar a quem não vê
        aquele tipo de dado o que falta nele (RF-07).
        """
        faltas = []
        if not self.data_nascimento:
            faltas.append(("identificacao", "data de nascimento"))
        if not self.unidade:
            faltas.append(("identificacao", "unidade de atendimento"))
        if not self.ano_escolar:
            faltas.append(("escolar", "ano escolar"))
        if not self.escola_id and not self.sem_matricula:
            faltas.append(("escolar", "escola de origem"))
        if self.pk and not self._tem_responsavel():
            faltas.append(("familia", "um responsável"))
        return faltas

    def faltas_da_ficha(self):
        """O que falta para a ficha estar completa (RF-19). Lista de rótulos."""
        return [rotulo for _, rotulo in self.faltas_da_ficha_por_grupo()]

    def faltas_visiveis(self, acesso):
        """Só o que falta nos tipos de dado que a pessoa vê."""
        return [rotulo for grupo, rotulo in self.faltas_da_ficha_por_grupo() if acesso.pode_ver(grupo)]

    def _tem_responsavel(self):
        # Em listas, a consulta anota `tem_responsavel` (ou traz os responsáveis junto) para não
        # fazer uma consulta por aluno.
        anotado = getattr(self, "tem_responsavel", None)
        if anotado is not None:
            return bool(anotado)
        guardados = getattr(self, "_prefetched_objects_cache", {})
        if "responsaveis" in guardados:
            return bool(guardados["responsaveis"])
        return self.responsaveis.exists()

    @property
    def ficha_completa(self):
        return not self.faltas_da_ficha()


class Responsavel(ModeloDoServico):
    """Responsável pela criança (família)."""

    class Parentesco(models.TextChoices):
        MAE = "mae", "Mãe"
        PAI = "pai", "Pai"
        AVO = "avo", "Avó ou avô"
        TIO = "tio", "Tia ou tio"
        IRMAO = "irmao", "Irmã ou irmão"
        TUTOR = "tutor", "Tutor ou guardião legal"
        OUTRO = "outro", "Outro"

    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name="responsaveis")
    nome = models.CharField("nome completo", max_length=150)
    parentesco = models.CharField(max_length=10, choices=Parentesco.choices)
    responsavel_legal = models.BooleanField(
        "é responsável legal", default=True, help_text="Só o responsável legal autoriza o uso dos dados (LGPD-02)."
    )
    telefone = models.CharField(max_length=20, blank=True)
    tem_whatsapp = models.BooleanField("o telefone tem WhatsApp", default=False)
    email = models.EmailField("e-mail", blank=True)
    observacoes = models.CharField("observações", max_length=255, blank=True)

    GRUPOS_DE_CAMPOS = {
        "familia": ["nome", "parentesco", "responsavel_legal", "telefone", "tem_whatsapp", "email", "observacoes"],
    }

    class Meta:
        verbose_name = "responsável"
        verbose_name_plural = "responsáveis"
        ordering = ["-responsavel_legal", "nome"]

    def __str__(self):
        return f"{self.nome} ({self.get_parentesco_display()})"


class MudancaDeSituacao(ModeloDoServico):
    """Histórico da situação do aluno (RF-11, RF-22).

    Toda mudança pede o motivo, inclusive a volta a ativo. O encerramento pede
    também a data de saída, o motivo de saída e o responsável pela saída.
    """

    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE, related_name="mudancas_de_situacao")
    de = models.CharField("situação anterior", max_length=12, choices=Aluno.Situacao.choices)
    para = models.CharField("nova situação", max_length=12, choices=Aluno.Situacao.choices)
    data = models.DateField("a partir de", default=timezone.localdate)
    motivo = models.TextField("motivo da mudança")
    motivo_saida = models.CharField(
        "motivo de saída", max_length=80, blank=True, help_text="Só no encerramento; a lista vem da configuração do serviço."
    )
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        verbose_name="responsável pela saída",
    )

    # Saída por alta de aluno do TMO: alguém confere se precisa de professor domiciliar (RF-24).
    domiciliar_verificado_em = models.DateField(
        "professor domiciliar verificado em", null=True, blank=True, editable=False
    )
    domiciliar_verificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", editable=False
    )
    domiciliar_observacao = models.TextField("o que foi decidido sobre o professor domiciliar", blank=True)

    GRUPOS_DE_CAMPOS = {
        "identificacao": [
            "de", "para", "data", "motivo", "motivo_saida", "responsavel", "domiciliar_verificado_em",
            "domiciliar_verificado_por", "domiciliar_observacao",
        ],
    }

    class Meta:
        verbose_name = "mudança de situação"
        verbose_name_plural = "mudanças de situação"
        ordering = ["-data", "-criado_em"]

    def __str__(self):
        return f"{self.aluno}: {self.get_de_display()} → {self.get_para_display()}"

    @property
    def e_alta(self):
        """Saída por alta: o motivo de saída começa com "Alta" (a lista é configurável, RF-22)."""
        return self.para == Aluno.Situacao.ENCERRADO and (self.motivo_saida or "").strip().lower().startswith("alta")

    @property
    def pede_professor_domiciliar(self):
        """Alta de aluno do TMO ainda sem a verificação do professor domiciliar (RF-24)."""
        return self.e_alta and self.aluno.tmo and self.domiciliar_verificado_em is None

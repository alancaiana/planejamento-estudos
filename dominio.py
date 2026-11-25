"""Classes de domínio e regras de negócio do Planejamento de Estudos.

Segue o Diagrama de Classes de Domínio e as regras RN01–RN08 descritas
na especificação dos casos de uso UC03 (Cadastrar disciplina e tópicos)
e UC05 (Realizar revisão).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

# RN01 – sequência de intervalos (em dias) de cada etapa de revisão.
INTERVALOS = (1, 3, 7, 15, 30)
ULTIMA_ETAPA = len(INTERVALOS) - 1

# RN04 – avaliação em até 7 dias torna os tópicos da disciplina prioritários.
DIAS_PRIORIDADE = 7


class Dificuldade(str, Enum):
    FACIL = "FACIL"
    MEDIO = "MEDIO"
    DIFICIL = "DIFICIL"

    @property
    def rotulo(self) -> str:
        return {"FACIL": "Fácil", "MEDIO": "Médio", "DIFICIL": "Difícil"}[self.value]


class StatusRevisao(str, Enum):
    PENDENTE = "PENDENTE"
    CONCLUIDA = "CONCLUIDA"
    ATRASADA = "ATRASADA"


class CadastroInvalido(ValueError):
    """Violação de RN06 ou RN07 no cadastro de disciplina."""


class ContaInvalida(ValueError):
    """Violação de RN09 na criação da conta do aluno."""


# RN09 – dados mínimos da conta (LGPD).
SENHA_MINIMA = 6
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class Aluno:
    id: int
    nome: str
    email: str
    dias_estudo_semana: int  # hábito declarado no cadastro: linha de base do KPI +40%

    @property
    def primeiro_nome(self) -> str:
        return self.nome.split()[0]


def validar_conta(
    nome: str,
    email: str,
    senha: str,
    dias_estudo_semana: int | None,
    aceitou_termo: bool,
    email_ja_cadastrado: bool,
) -> tuple[str, str]:
    """RN09 – nome, e-mail único e válido, senha mínima, hábito informado e aceite do termo LGPD."""
    nome, email = nome.strip(), email.strip().lower()
    if not nome:
        raise ContaInvalida("Informe seu nome.")
    if not _EMAIL.match(email):
        raise ContaInvalida("Informe um e-mail válido.")
    if email_ja_cadastrado:
        raise ContaInvalida("Já existe uma conta com este e-mail. Use “Entrar”.")
    if len(senha) < SENHA_MINIMA:
        raise ContaInvalida(f"A senha deve ter ao menos {SENHA_MINIMA} caracteres.")
    if dias_estudo_semana is None or not 0 <= dias_estudo_semana <= 7:
        raise ContaInvalida("Informe quantos dias por semana você estuda hoje.")
    if not aceitou_termo:
        raise ContaInvalida("É preciso aceitar o termo de uso de dados (LGPD) para criar a conta.")
    return nome, email


def gerar_hash_senha(senha: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, 200_000)
    return digest.hex(), salt.hex()


def conferir_senha(senha: str, hash_hex: str, salt_hex: str) -> bool:
    calculado, _ = gerar_hash_senha(senha, bytes.fromhex(salt_hex))
    return hmac.compare_digest(calculado, hash_hex)


def rotulo_etapa(etapa: int) -> str:
    return f"D+{INTERVALOS[etapa]}"


def proxima_etapa(etapa_atual: int, dificuldade: Dificuldade) -> int:
    """RN02 (ajuste por dificuldade) e RN08 (etapa máxima)."""
    if dificuldade is Dificuldade.FACIL:
        return min(etapa_atual + 1, ULTIMA_ETAPA)
    if dificuldade is Dificuldade.MEDIO:
        return etapa_atual
    return 0


def data_da_revisao(base: date, etapa: int) -> date:
    """RN01 – a data é contada a partir da última revisão (ou do cadastro)."""
    return base + timedelta(days=INTERVALOS[etapa])


def primeira_revisao(data_cadastro: date) -> date:
    """RN05 – a primeira revisão de um tópico acontece em D+1."""
    return data_da_revisao(data_cadastro, 0)


@dataclass
class Avaliacao:
    data: date

    def dias_restantes(self, hoje: date) -> int:
        return (self.data - hoje).days

    def torna_prioritario(self, hoje: date) -> bool:
        """RN04 – avaliação futura em até DIAS_PRIORIDADE dias."""
        return 0 <= self.dias_restantes(hoje) <= DIAS_PRIORIDADE


@dataclass
class Topico:
    id: int
    nome: str
    etapa_atual: int
    data_cadastro: date

    def intervalo_atual(self) -> int:
        return INTERVALOS[self.etapa_atual]

    def agendar_proxima(self, dificuldade: Dificuldade, hoje: date) -> date:
        """Avança a etapa conforme a dificuldade e devolve a data da próxima revisão."""
        self.etapa_atual = proxima_etapa(self.etapa_atual, dificuldade)
        return data_da_revisao(hoje, self.etapa_atual)


@dataclass
class Revisao:
    id: int
    data_prevista: date
    status: StatusRevisao = StatusRevisao.PENDENTE
    data_realizada: date | None = None
    dificuldade: Dificuldade | None = None

    def esta_atrasada(self, hoje: date) -> bool:
        """RN03 – revisão não feita na data prevista continua na fila dos dias seguintes como atrasada."""
        return self.status is not StatusRevisao.CONCLUIDA and self.data_prevista < hoje

    def concluir(self, dificuldade: Dificuldade, hoje: date) -> None:
        self.status = StatusRevisao.CONCLUIDA
        self.dificuldade = dificuldade
        self.data_realizada = hoje


def validar_cadastro(
    nome: str,
    topicos: list[str],
    data_avaliacao: date | None,
    hoje: date,
    nomes_existentes: list[str],
) -> tuple[str, list[str]]:
    """Aplica RN06 e RN07. Devolve o nome e a lista de tópicos normalizados."""
    nome = nome.strip()
    if not nome:
        raise CadastroInvalido("Informe o nome da disciplina.")
    if nome.casefold() in {n.casefold() for n in nomes_existentes}:
        raise CadastroInvalido(f"Você já possui a disciplina “{nome}”. Escolha outro nome.")

    limpos: list[str] = []
    vistos: set[str] = set()
    for topico in topicos:
        topico = topico.strip()
        if topico and topico.casefold() not in vistos:
            limpos.append(topico)
            vistos.add(topico.casefold())
    if not limpos:
        raise CadastroInvalido("Adicione ao menos um tópico à disciplina.")

    if data_avaliacao is not None and data_avaliacao < hoje:
        raise CadastroInvalido("A data da avaliação não pode ser anterior a hoje.")
    return nome, limpos


@dataclass
class ItemFila:
    """Uma revisão da fila do dia, com os dados necessários para exibi-la."""
    revisao_id: int
    topico_id: int
    topico: str
    disciplina: str
    etapa: int
    data_prevista: date
    atrasada: bool
    prioritario: bool


def ordenar_fila(itens: list[ItemFila]) -> list[ItemFila]:
    """UC05 passo 2 – atrasadas, depois prioritárias (RN04), depois por data prevista."""
    return sorted(
        itens,
        key=lambda i: (not i.atrasada, not i.prioritario, i.data_prevista, i.disciplina, i.topico),
    )

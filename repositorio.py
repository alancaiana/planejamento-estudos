"""Persistência em SQLite de alunos, disciplinas, tópicos e revisões."""
from __future__ import annotations

import os
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from dominio import (
    Aluno,
    Avaliacao,
    Dificuldade,
    ItemFila,
    Revisao,
    StatusRevisao,
    Topico,
    conferir_senha,
    gerar_hash_senha,
    ordenar_fila,
    primeira_revisao,
)

# KPI de cobertura: tópico revisado ao menos 2 vezes antes da prova.
REVISOES_PARA_COBERTURA = 2

ESQUEMA = """
CREATE TABLE IF NOT EXISTS aluno (
    id                  INTEGER PRIMARY KEY,
    nome                TEXT NOT NULL,
    email               TEXT NOT NULL UNIQUE COLLATE NOCASE,
    senha_hash          TEXT NOT NULL,
    senha_salt          TEXT NOT NULL,
    dias_estudo_semana  INTEGER NOT NULL,
    consentimento_lgpd  TEXT NOT NULL,
    data_cadastro       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS disciplina (
    id             INTEGER PRIMARY KEY,
    aluno_id       INTEGER NOT NULL REFERENCES aluno(id) ON DELETE CASCADE,
    nome           TEXT NOT NULL COLLATE NOCASE,
    data_avaliacao TEXT,
    UNIQUE (aluno_id, nome)
);
CREATE TABLE IF NOT EXISTS topico (
    id            INTEGER PRIMARY KEY,
    disciplina_id INTEGER NOT NULL REFERENCES disciplina(id) ON DELETE CASCADE,
    nome          TEXT NOT NULL,
    etapa_atual   INTEGER NOT NULL DEFAULT 0,
    data_cadastro TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revisao (
    id             INTEGER PRIMARY KEY,
    topico_id      INTEGER NOT NULL REFERENCES topico(id) ON DELETE CASCADE,
    data_prevista  TEXT NOT NULL,
    data_realizada TEXT,
    dificuldade    TEXT,
    status         TEXT NOT NULL DEFAULT 'PENDENTE'
);
"""

# Revisões de um aluno, com tópico e disciplina.
_REVISOES_DO_ALUNO = """
  FROM revisao r
  JOIN topico t ON t.id = r.topico_id
  JOIN disciplina d ON d.id = t.disciplina_id
 WHERE d.aluno_id = ?
"""


def _data(texto: str | None) -> date | None:
    return date.fromisoformat(texto) if texto else None


class Repositorio:
    def __init__(self, caminho: str | Path = ":memory:"):
        self.con = sqlite3.connect(str(caminho), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(ESQUEMA)

    # ---------- UC01 / UC02 – Criar conta e entrar ----------

    def email_cadastrado(self, email: str) -> bool:
        return self.con.execute("SELECT 1 FROM aluno WHERE email = ?", (email.strip(),)).fetchone() is not None

    def criar_aluno(self, nome: str, email: str, senha: str, dias_estudo_semana: int, hoje: date) -> Aluno:
        """Os dados já devem ter sido validados com ``dominio.validar_conta`` (RN09)."""
        senha_hash, salt = gerar_hash_senha(senha)
        with self.con:
            cur = self.con.execute(
                "INSERT INTO aluno (nome, email, senha_hash, senha_salt, dias_estudo_semana, consentimento_lgpd, data_cadastro)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nome, email, senha_hash, salt, dias_estudo_semana, hoje.isoformat(), hoje.isoformat()),
            )
        return Aluno(cur.lastrowid, nome, email, dias_estudo_semana)

    def autenticar(self, email: str, senha: str) -> Aluno | None:
        l = self.con.execute("SELECT * FROM aluno WHERE email = ?", (email.strip(),)).fetchone()
        if l is None or not conferir_senha(senha, l["senha_hash"], l["senha_salt"]):
            return None
        return Aluno(l["id"], l["nome"], l["email"], l["dias_estudo_semana"])

    def conta_demonstracao(self, hoje: date) -> Aluno:
        """Conta pronta para apresentações, com 4 semanas de histórico simulado."""
        email = "estudante.demo@example.com"
        l = self.con.execute("SELECT * FROM aluno WHERE email = ?", (email,)).fetchone()
        if l is not None:
            return Aluno(l["id"], l["nome"], l["email"], l["dias_estudo_semana"])
        aluno = self.criar_aluno("Estudante Demonstração", email, os.urandom(12).hex(), 2, hoje)
        self.carregar_exemplo(aluno.id, hoje)
        return aluno

    # ---------- UC03 – Cadastrar disciplina e tópicos ----------

    def nomes_disciplinas(self, aluno_id: int) -> list[str]:
        return [r["nome"] for r in self.con.execute("SELECT nome FROM disciplina WHERE aluno_id = ?", (aluno_id,))]

    def cadastrar_disciplina(
        self, aluno_id: int, nome: str, data_avaliacao: date | None, topicos: list[str], hoje: date
    ) -> list[tuple[str, date]]:
        """Registra a disciplina e agenda a primeira revisão de cada tópico (RN05).

        Os dados já devem ter sido validados com ``dominio.validar_cadastro``.
        Devolve, para cada tópico, a data da primeira revisão.
        """
        with self.con:
            cur = self.con.execute(
                "INSERT INTO disciplina (aluno_id, nome, data_avaliacao) VALUES (?, ?, ?)",
                (aluno_id, nome, data_avaliacao.isoformat() if data_avaliacao else None),
            )
            disciplina_id = cur.lastrowid
            agendados = []
            for nome_topico in topicos:
                cur = self.con.execute(
                    "INSERT INTO topico (disciplina_id, nome, etapa_atual, data_cadastro) VALUES (?, ?, 0, ?)",
                    (disciplina_id, nome_topico, hoje.isoformat()),
                )
                data = primeira_revisao(hoje)
                self.con.execute(
                    "INSERT INTO revisao (topico_id, data_prevista) VALUES (?, ?)",
                    (cur.lastrowid, data.isoformat()),
                )
                agendados.append((nome_topico, data))
        return agendados

    # ---------- UC04 / UC05 – Revisões do dia e realizar revisão ----------

    def fila_do_dia(self, aluno_id: int, hoje: date) -> list[ItemFila]:
        linhas = self.con.execute(
            "SELECT r.id AS revisao_id, r.data_prevista, r.status, t.id AS topico_id, t.nome AS topico,"
            "       t.etapa_atual, d.nome AS disciplina, d.data_avaliacao"
            + _REVISOES_DO_ALUNO
            + " AND r.status != 'CONCLUIDA' AND r.data_prevista <= ?",
            (aluno_id, hoje.isoformat()),
        ).fetchall()
        itens = []
        for l in linhas:
            revisao = Revisao(l["revisao_id"], _data(l["data_prevista"]), StatusRevisao(l["status"]))
            avaliacao = _data(l["data_avaliacao"])
            itens.append(
                ItemFila(
                    revisao_id=revisao.id,
                    topico_id=l["topico_id"],
                    topico=l["topico"],
                    disciplina=l["disciplina"],
                    etapa=l["etapa_atual"],
                    data_prevista=revisao.data_prevista,
                    atrasada=revisao.esta_atrasada(hoje),
                    prioritario=avaliacao is not None and Avaliacao(avaliacao).torna_prioritario(hoje),
                )
            )
        return ordenar_fila(itens)

    def concluir_revisao(
        self, aluno_id: int, revisao_id: int, dificuldade: Dificuldade, hoje: date
    ) -> tuple[int, date]:
        """UC05 passos 5–6: conclui a revisão e agenda a próxima (UC08). Devolve (etapa, data)."""
        l = self.con.execute(
            "SELECT r.id, r.data_prevista, t.id AS topico_id, t.nome, t.etapa_atual, t.data_cadastro"
            + _REVISOES_DO_ALUNO
            + " AND r.id = ? AND r.status != 'CONCLUIDA'",
            (aluno_id, revisao_id),
        ).fetchone()
        if l is None:
            raise ValueError("Revisão inexistente ou já concluída.")

        revisao = Revisao(l["id"], _data(l["data_prevista"]))
        topico = Topico(l["topico_id"], l["nome"], l["etapa_atual"], _data(l["data_cadastro"]))
        revisao.concluir(dificuldade, hoje)
        proxima = topico.agendar_proxima(dificuldade, hoje)

        with self.con:
            self.con.execute(
                "UPDATE revisao SET status = ?, data_realizada = ?, dificuldade = ? WHERE id = ?",
                (revisao.status.value, hoje.isoformat(), dificuldade.value, revisao.id),
            )
            self.con.execute("UPDATE topico SET etapa_atual = ? WHERE id = ?", (topico.etapa_atual, topico.id))
            self.con.execute(
                "INSERT INTO revisao (topico_id, data_prevista) VALUES (?, ?)",
                (topico.id, proxima.isoformat()),
            )
        return topico.etapa_atual, proxima

    def proxima_data_agendada(self, aluno_id: int, depois_de: date) -> date | None:
        l = self.con.execute(
            "SELECT MIN(r.data_prevista) AS d" + _REVISOES_DO_ALUNO + " AND r.status != 'CONCLUIDA' AND r.data_prevista > ?",
            (aluno_id, depois_de.isoformat()),
        ).fetchone()
        return _data(l["d"])

    # ---------- Indicadores do painel (C3) e relatórios (C5 / UC06) ----------

    def dias_seguidos(self, aluno_id: int, hoje: date) -> int:
        """Dias consecutivos com ao menos uma revisão concluída, até hoje (ou até ontem, se hoje ainda não houve)."""
        dias = {
            _data(r["data_realizada"])
            for r in self.con.execute(
                "SELECT DISTINCT r.data_realizada" + _REVISOES_DO_ALUNO + " AND r.status = 'CONCLUIDA' AND r.data_realizada <= ?",
                (aluno_id, hoje.isoformat()),
            )
        }
        dia = hoje if hoje in dias else hoje - timedelta(days=1)
        seguidos = 0
        while dia in dias:
            seguidos += 1
            dia -= timedelta(days=1)
        return seguidos

    def dias_com_estudo(self, aluno_id: int, inicio: date, fim: date) -> int:
        """Dias distintos com ao menos uma revisão concluída no período (KPI de regularidade)."""
        return self.con.execute(
            "SELECT COUNT(DISTINCT r.data_realizada)" + _REVISOES_DO_ALUNO
            + " AND r.status = 'CONCLUIDA' AND r.data_realizada BETWEEN ? AND ?",
            (aluno_id, inicio.isoformat(), fim.isoformat()),
        ).fetchone()[0]

    def adesao(self, aluno_id: int, inicio: date, fim: date) -> float | None:
        """KPI de adesão: revisões concluídas até a data prevista ÷ revisões previstas no período."""
        l = self.con.execute(
            "SELECT COUNT(*) AS total,"
            "       SUM(r.status = 'CONCLUIDA' AND r.data_realizada <= r.data_prevista) AS no_prazo"
            + _REVISOES_DO_ALUNO
            + " AND r.data_prevista BETWEEN ? AND ?",
            (aluno_id, inicio.isoformat(), fim.isoformat()),
        ).fetchone()
        return None if not l["total"] else l["no_prazo"] / l["total"]

    def adesao_semanal(self, aluno_id: int, hoje: date, semanas: int = 4) -> list[tuple[str, float | None]]:
        """Adesão das últimas semanas completas (até ontem: as revisões de hoje ainda estão no prazo)."""
        fim = hoje - timedelta(days=1)
        resultado = []
        for k in range(semanas):
            fim_semana = fim - timedelta(days=7 * (semanas - 1 - k))
            resultado.append((f"S{k + 1}", self.adesao(aluno_id, fim_semana - timedelta(days=6), fim_semana)))
        return resultado

    def cobertura_por_disciplina(self, aluno_id: int, hoje: date) -> list[dict]:
        """KPI de cobertura: tópicos com ao menos 2 revisões concluídas, por disciplina."""
        resultado = []
        for d in self.con.execute("SELECT * FROM disciplina WHERE aluno_id = ? ORDER BY nome", (aluno_id,)):
            contagens = [
                r["feitas"]
                for r in self.con.execute(
                    "SELECT (SELECT COUNT(*) FROM revisao r WHERE r.topico_id = t.id AND r.status = 'CONCLUIDA') AS feitas"
                    "  FROM topico t WHERE t.disciplina_id = ?",
                    (d["id"],),
                )
            ]
            avaliacao = _data(d["data_avaliacao"])
            resultado.append(
                {
                    "disciplina": d["nome"],
                    "topicos": len(contagens),
                    "cobertos": sum(c >= REVISOES_PARA_COBERTURA for c in contagens),
                    "sem_revisao": sum(c == 0 for c in contagens),
                    "dias_para_prova": (avaliacao - hoje).days if avaliacao else None,
                }
            )
        return resultado

    # ---------- Consulta das disciplinas ----------

    def disciplinas(self, aluno_id: int) -> list[dict]:
        resultado = []
        for d in self.con.execute("SELECT * FROM disciplina WHERE aluno_id = ? ORDER BY nome", (aluno_id,)):
            topicos = self.con.execute(
                """
                SELECT t.nome, t.etapa_atual,
                       (SELECT MIN(data_prevista) FROM revisao
                         WHERE topico_id = t.id AND status != 'CONCLUIDA') AS proxima,
                       (SELECT COUNT(*) FROM revisao
                         WHERE topico_id = t.id AND status = 'CONCLUIDA') AS feitas
                  FROM topico t WHERE t.disciplina_id = ? ORDER BY t.id
                """,
                (d["id"],),
            ).fetchall()
            resultado.append(
                {
                    "id": d["id"],
                    "nome": d["nome"],
                    "data_avaliacao": _data(d["data_avaliacao"]),
                    "topicos": [
                        {"nome": t["nome"], "etapa": t["etapa_atual"], "proxima": _data(t["proxima"]), "feitas": t["feitas"]}
                        for t in topicos
                    ],
                }
            )
        return resultado

    def excluir_disciplina(self, aluno_id: int, disciplina_id: int) -> None:
        with self.con:
            self.con.execute("DELETE FROM disciplina WHERE id = ? AND aluno_id = ?", (disciplina_id, aluno_id))

    def limpar(self, aluno_id: int) -> None:
        with self.con:
            self.con.execute("DELETE FROM disciplina WHERE aluno_id = ?", (aluno_id,))

    def _adicionar_topico(self, aluno_id: int, disciplina: str, topico: str, quando: date) -> None:
        with self.con:
            disciplina_id = self.con.execute(
                "SELECT id FROM disciplina WHERE aluno_id = ? AND nome = ?", (aluno_id, disciplina)
            ).fetchone()["id"]
            cur = self.con.execute(
                "INSERT INTO topico (disciplina_id, nome, etapa_atual, data_cadastro) VALUES (?, ?, 0, ?)",
                (disciplina_id, topico, quando.isoformat()),
            )
            self.con.execute(
                "INSERT INTO revisao (topico_id, data_prevista) VALUES (?, ?)",
                (cur.lastrowid, primeira_revisao(quando).isoformat()),
            )

    def carregar_exemplo(self, aluno_id: int, hoje: date) -> None:
        """Simula 4 semanas de uso real, aplicando o próprio algoritmo dia a dia.

        Resultado: histórico para os relatórios, revisões para hoje, algumas atrasadas
        e uma prova em 5 dias com tópicos ainda sem revisão.
        """
        self.limpar(aluno_id)
        inicio = hoje - timedelta(days=28)
        self.cadastrar_disciplina(
            aluno_id, "Engenharia de Software", hoje + timedelta(days=20),
            ["Requisitos", "Estórias de usuário", "Casos de uso", "Diagrama de classes"], inicio,
        )
        self.cadastrar_disciplina(
            aluno_id, "Banco de Dados", None, ["Modelo ER", "Normalização", "SQL – Joins"], inicio + timedelta(days=3),
        )
        self.cadastrar_disciplina(
            aluno_id, "Física I", hoje + timedelta(days=30), ["Leis de Newton", "Cinemática"], hoje - timedelta(days=10),
        )

        # Tópicos incluídos ao longo do semestre (ainda com poucas revisões).
        for disciplina, topico, dias_atras in (
            ("Banco de Dados", "Índices", 8), ("Engenharia de Software", "Testes de software", 5),
            ("Banco de Dados", "Transações", 3), ("Engenharia de Software", "Padrões de projeto", 2),
        ):
            self._adicionar_topico(aluno_id, disciplina, topico, hoje - timedelta(days=dias_atras))

        # O aluno vai criando o hábito: falta mais no começo e menos no fim (adesão crescente).
        sorteio = random.Random(7)
        total_dias = (hoje - inicio).days
        for n in range(total_dias):
            dia = inicio + timedelta(days=n)
            progresso = n / total_dias
            if n < total_dias - 4 and sorteio.random() < 0.3 - 0.25 * progresso:
                continue  # dia sem estudo
            for item in self.fila_do_dia(aluno_id, dia):
                if sorteio.random() < 0.25 - 0.2 * progresso:
                    continue  # revisão pulada: fica atrasada (RN03)
                dificuldade = sorteio.choices(list(Dificuldade), weights=(6, 3, 1))[0]
                self.concluir_revisao(aluno_id, item.revisao_id, dificuldade, dia)

        # Garante ao menos uma revisão atrasada (RN03) para a demonstração:
        # a próxima revisão pendente de Banco de Dados passa a ter vencido há 2 dias.
        with self.con:
            self.con.execute(
                "UPDATE revisao SET data_prevista = MIN(data_prevista, ?) WHERE id = ("
                "  SELECT r.id" + _REVISOES_DO_ALUNO + " AND d.nome = 'Banco de Dados' AND r.status != 'CONCLUIDA'"
                "  ORDER BY r.data_prevista LIMIT 1)",
                ((hoje - timedelta(days=2)).isoformat(), aluno_id),
            )

        self.cadastrar_disciplina(
            aluno_id, "Cálculo I", hoje + timedelta(days=5),
            ["Limites", "Continuidade", "Derivadas", "Regra da cadeia", "Integrais", "Teorema fundamental"],
            hoje - timedelta(days=1),
        )

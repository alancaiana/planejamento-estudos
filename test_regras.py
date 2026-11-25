"""Testes das regras de negócio RN01–RN09 e dos indicadores (executar com: python -m unittest -v)."""
import unittest
from datetime import date, timedelta

from dominio import (
    CadastroInvalido,
    ContaInvalida,
    Dificuldade,
    proxima_etapa,
    validar_cadastro,
    validar_conta,
)
from repositorio import Repositorio

HOJE = date(2026, 12, 1)


def dias(n: int) -> date:
    return HOJE + timedelta(days=n)


class RegrasDeAgendamento(unittest.TestCase):
    def test_rn02_facil_avanca_medio_repete_dificil_volta(self):
        self.assertEqual(proxima_etapa(2, Dificuldade.FACIL), 3)
        self.assertEqual(proxima_etapa(2, Dificuldade.MEDIO), 2)
        self.assertEqual(proxima_etapa(2, Dificuldade.DIFICIL), 0)

    def test_rn08_etapa_maxima_e_d30(self):
        self.assertEqual(proxima_etapa(4, Dificuldade.FACIL), 4)


class CadastroDeDisciplina(unittest.TestCase):
    def test_rn06_nome_duplicado_ignora_maiusculas(self):
        with self.assertRaises(CadastroInvalido):
            validar_cadastro("banco de dados", ["SQL"], None, HOJE, ["Banco de Dados"])

    def test_rn06_exige_ao_menos_um_topico(self):
        with self.assertRaises(CadastroInvalido):
            validar_cadastro("Física", ["", "   "], None, HOJE, [])

    def test_rn06_remove_topicos_repetidos_e_vazios(self):
        _, topicos = validar_cadastro("Física", ["Cinemática", "", "cinemática", "Dinâmica"], None, HOJE, [])
        self.assertEqual(topicos, ["Cinemática", "Dinâmica"])

    def test_rn07_avaliacao_no_passado_e_invalida(self):
        with self.assertRaises(CadastroInvalido):
            validar_cadastro("Física", ["Cinemática"], dias(-1), HOJE, [])

    def test_rn07_avaliacao_hoje_e_valida(self):
        validar_cadastro("Física", ["Cinemática"], HOJE, HOJE, [])


class CriacaoDeConta(unittest.TestCase):
    def valida(self, **mudancas):
        dados = dict(nome="Maria Souza", email="Maria@Exemplo.com ", senha="segredo1",
                     dias_estudo_semana=2, aceitou_termo=True, email_ja_cadastrado=False)
        dados.update(mudancas)
        return validar_conta(**dados)

    def test_rn09_dados_validos_normalizam_email(self):
        self.assertEqual(self.valida(), ("Maria Souza", "maria@exemplo.com"))

    def test_rn09_exige_aceite_do_termo_lgpd(self):
        with self.assertRaises(ContaInvalida):
            self.valida(aceitou_termo=False)

    def test_rn09_rejeita_email_invalido_duplicado_senha_curta_e_habito_ausente(self):
        for mudanca in ({"email": "maria"}, {"email_ja_cadastrado": True}, {"senha": "123"},
                        {"dias_estudo_semana": None}, {"nome": "  "}):
            with self.subTest(mudanca), self.assertRaises(ContaInvalida):
                self.valida(**mudanca)

    def test_senha_guardada_como_hash_e_autenticacao(self):
        repo = Repositorio()
        repo.criar_aluno("Maria Souza", "maria@exemplo.com", "segredo1", 2, HOJE)
        guardada = repo.con.execute("SELECT senha_hash FROM aluno").fetchone()[0]
        self.assertNotIn("segredo1", guardada)
        self.assertEqual(repo.autenticar("maria@exemplo.com", "segredo1").primeiro_nome, "Maria")
        self.assertIsNone(repo.autenticar("maria@exemplo.com", "errada"))
        self.assertTrue(repo.email_cadastrado("MARIA@exemplo.com"))


class FluxoCompleto(unittest.TestCase):
    def setUp(self):
        self.repo = Repositorio()
        self.aluno = self.repo.criar_aluno("Maria Souza", "maria@exemplo.com", "segredo1", 2, HOJE).id

    def cadastrar(self, nome, avaliacao, topicos, quando=HOJE):
        return self.repo.cadastrar_disciplina(self.aluno, nome, avaliacao, topicos, quando)

    def fila(self, dia):
        return self.repo.fila_do_dia(self.aluno, dia)

    def concluir(self, dia, dificuldade=Dificuldade.FACIL):
        return self.repo.concluir_revisao(self.aluno, self.fila(dia)[0].revisao_id, dificuldade, dia)

    def test_rn05_primeira_revisao_em_d1(self):
        self.assertEqual(self.cadastrar("Física", None, ["Cinemática"]), [("Cinemática", dias(1))])
        self.assertEqual(self.fila(HOJE), [])
        self.assertEqual(len(self.fila(dias(1))), 1)

    def test_rn01_sequencia_completa_com_respostas_faceis(self):
        self.cadastrar("Física", None, ["Cinemática"])
        dia, datas = dias(1), []
        for _ in range(6):
            _, dia = self.concluir(dia)
            datas.append(dia)
        intervalos = [(b - a).days for a, b in zip([dias(1)] + datas[:-1], datas)]
        self.assertEqual(intervalos, [3, 7, 15, 30, 30, 30])  # RN01 + RN08

    def test_rn02_dificil_volta_para_d1(self):
        self.cadastrar("Física", None, ["Cinemática"])
        self.concluir(dias(1))
        self.assertEqual(self.concluir(dias(4), Dificuldade.DIFICIL), (0, dias(5)))

    def test_rn03_revisao_nao_feita_aparece_atrasada_nos_dias_seguintes(self):
        self.cadastrar("Física", None, ["Cinemática"])
        self.assertFalse(self.fila(dias(1))[0].atrasada)
        self.assertTrue(self.fila(dias(2))[0].atrasada)
        self.assertTrue(self.fila(dias(9))[0].atrasada)

    def test_ordem_da_fila_atrasadas_prioritarias_e_depois_demais(self):
        self.cadastrar("A – Sem prova", None, ["Comum"])
        self.cadastrar("B – Prova próxima", dias(6), ["Prioritário"])
        self.cadastrar("C – Antiga", None, ["Atrasado"], dias(-3))
        fila = self.fila(dias(1))
        self.assertEqual([i.topico for i in fila], ["Atrasado", "Prioritário", "Comum"])
        self.assertTrue(fila[1].prioritario)  # RN04

    def test_concluir_duas_vezes_e_rejeitado(self):
        self.cadastrar("Física", None, ["Cinemática"])
        revisao = self.fila(dias(1))[0].revisao_id
        self.repo.concluir_revisao(self.aluno, revisao, Dificuldade.MEDIO, dias(1))
        with self.assertRaises(ValueError):
            self.repo.concluir_revisao(self.aluno, revisao, Dificuldade.MEDIO, dias(1))

    def test_exclusao_da_disciplina_remove_topicos_e_revisoes(self):
        self.cadastrar("Física", None, ["Cinemática"])
        self.repo.excluir_disciplina(self.aluno, self.repo.disciplinas(self.aluno)[0]["id"])
        self.assertEqual(self.repo.con.execute("SELECT COUNT(*) FROM revisao").fetchone()[0], 0)

    def test_alunos_nao_veem_dados_um_do_outro(self):
        outro = self.repo.criar_aluno("João", "joao@exemplo.com", "segredo2", 3, HOJE).id
        self.cadastrar("Física", None, ["Cinemática"])
        self.repo.cadastrar_disciplina(outro, "Física", None, ["Ótica"], HOJE)  # mesmo nome, outro aluno
        self.assertEqual([i.topico for i in self.fila(dias(1))], ["Cinemática"])
        with self.assertRaises(ValueError):
            self.repo.concluir_revisao(outro, self.fila(dias(1))[0].revisao_id, Dificuldade.FACIL, dias(1))

    def test_indicadores_dias_seguidos_adesao_e_cobertura(self):
        self.cadastrar("Física", dias(10), ["Cinemática", "Dinâmica"])
        self.concluir(dias(1))       # Dinâmica fica pendente e atrasa
        self.concluir(dias(2))       # Dinâmica concluída com 1 dia de atraso
        self.concluir(dias(4))       # Cinemática (D+3) no prazo
        self.assertEqual(self.repo.dias_seguidos(self.aluno, dias(2)), 2)
        self.assertEqual(self.repo.dias_seguidos(self.aluno, dias(4)), 1)
        self.assertAlmostEqual(self.repo.adesao(self.aluno, dias(1), dias(4)), 2 / 3)
        self.assertEqual(self.repo.dias_com_estudo(self.aluno, dias(1), dias(4)), 3)
        cobertura = self.repo.cobertura_por_disciplina(self.aluno, HOJE)[0]
        self.assertEqual((cobertura["topicos"], cobertura["cobertos"], cobertura["sem_revisao"]), (2, 1, 0))
        self.assertEqual(cobertura["dias_para_prova"], 10)

    def test_dados_de_exemplo(self):
        self.repo.carregar_exemplo(self.aluno, HOJE)
        fila = self.fila(HOJE)
        self.assertTrue(any(i.atrasada for i in fila))
        self.assertTrue(any(i.prioritario for i in fila))
        semanas = self.repo.adesao_semanal(self.aluno, HOJE)
        self.assertTrue(all(valor is not None for _, valor in semanas))
        calculo = next(c for c in self.repo.cobertura_por_disciplina(self.aluno, HOJE) if c["disciplina"] == "Cálculo I")
        self.assertEqual((calculo["dias_para_prova"], calculo["sem_revisao"]), (5, 6))


if __name__ == "__main__":
    unittest.main()

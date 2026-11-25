# Planejamento de Estudos com Repetição Espaçada — Protótipo executável

Projeto da disciplina Engenharia de Software (UFRN · T01 · 2026.2) — Alan Francisco.

As telas seguem os protótipos de baixa resolução do Documento de Requisitos:

| Tela | Caso de uso | Estórias |
|---|---|---|
| **C1 Cadastro do Aluno** (criar conta / entrar) | UC01 Criar conta · UC02 Entrar | EU1, EU2 |
| **C2 Nova disciplina** | UC03 Cadastrar disciplina e tópicos | EU3, EU4 |
| **C3 Painel “Revisões de Hoje”** | UC04 Consultar revisões do dia | EU5, EU6 |
| **C4 Sessão de Revisão** | UC05 Realizar revisão (+ UC08 Calcular próxima revisão) | EU7, EU8 |
| **C5 Relatórios de Desempenho** | UC06 Consultar relatórios | EU9, EU10 |

Os casos de uso especificados em detalhe no documento são o **UC03** e o **UC05**.

## Como executar

```bash
pip install -r requirements.txt
streamlit run app.py
```

- **Entrar com a conta de demonstração** abre uma conta com 4 semanas de uso simulado
  (histórico para os relatórios, revisões para hoje, uma atrasada e uma prova em 5 dias).
- **Simular a data**, na barra lateral, avança o “hoje” para ver as próximas revisões sem esperar dias reais.

## Regras de negócio implementadas

| Regra | Onde |
|---|---|
| RN01 Sequência de intervalos 1-3-7-15-30 | `dominio.INTERVALOS`, `data_da_revisao` |
| RN02 Fácil avança, médio repete, difícil volta para D+1 | `dominio.proxima_etapa` |
| RN03 Revisão não feita aparece como atrasada nos dias seguintes | `Revisao.esta_atrasada` |
| RN04 Avaliação em até 7 dias torna os tópicos prioritários | `Avaliacao.torna_prioritario`, `ordenar_fila` |
| RN05 Primeira revisão em D+1 | `dominio.primeira_revisao` |
| RN06 Nome de disciplina único (por aluno) e ao menos um tópico | `dominio.validar_cadastro` |
| RN07 Data da avaliação não pode ser passada | `dominio.validar_cadastro` |
| RN08 Etapa máxima D+30 | `dominio.proxima_etapa` |
| RN09 Conta: e-mail único, senha ≥ 6, hábito informado e aceite LGPD | `dominio.validar_conta` |

Senhas são guardadas apenas como hash (PBKDF2-SHA256 com salt).

## Indicadores (KPIs)

- **Adesão**: revisões concluídas até a data prevista ÷ revisões previstas (meta ≥ 80%).
- **Regularidade**: dias com revisão por semana × hábito declarado no cadastro (meta +40%).
- **Cobertura**: tópicos revisados ao menos 2× por disciplina (meta ≥ 90% antes da prova).

## Estrutura

- `dominio.py` — classes de domínio (Aluno, Avaliacao, Topico, Revisao, enumerações) e regras de negócio
- `repositorio.py` — persistência em SQLite (`planejamento.db`) e cálculo dos indicadores
- `app.py` — interface em Streamlit (telas C1–C5)
- `test_regras.py` — testes das regras e indicadores: `python -m unittest -v`

"""Protótipo executável – Planejamento de Estudos com Repetição Espaçada.

Telas construídas a partir dos protótipos de baixa resolução (C1–C5):
  C1 Cadastro do Aluno ............ UC01 Criar conta / UC02 Entrar
  C2 Nova disciplina .............. UC03 Cadastrar disciplina e tópicos
  C3 Painel “Revisões de Hoje” .... UC04 Consultar revisões do dia
  C4 Sessão de Revisão ............ UC05 Realizar revisão
  C5 Relatórios de Desempenho ..... UC06 Consultar relatórios

Executar com:  streamlit run app.py
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from dominio import (
    INTERVALOS,
    CadastroInvalido,
    ContaInvalida,
    Dificuldade,
    proxima_etapa,
    rotulo_etapa,
    validar_cadastro,
    validar_conta,
)
from repositorio import REVISOES_PARA_COBERTURA, Repositorio

st.set_page_config(page_title="Planejamento de Estudos", page_icon="📚", layout="wide")

PAGINAS = {
    "painel": "📅 Revisões de hoje",
    "disciplina": "➕ Nova disciplina",
    "revisao": "🧠 Sessão de revisão",
    "relatorios": "📊 Relatórios",
    "disciplinas": "📚 Minhas disciplinas",
}
EMOJI = {Dificuldade.FACIL: "😀", Dificuldade.MEDIO: "😐", Dificuldade.DIFICIL: "😣"}
META_ADESAO = 0.8  # KPI: ≥ 80% das revisões concluídas até o dia previsto

st.markdown(
    """
<style>
  .block-container { padding-top: 3.6rem; max-width: 1080px; }
  .rastreio { color:#64748b; font-size:.8rem; margin:0 0 .6rem; }
  .rastreio b { color:#4f46e5; }
  .cabecalho { display:flex; align-items:center; justify-content:space-between; gap:12px; }
  .cabecalho h2 { margin:0; padding:0; }
  .rotulo { font-size:.72rem; font-weight:700; letter-spacing:.06em; color:#64748b; text-transform:uppercase; margin:1rem 0 .35rem; }
  .tag { display:inline-block; font-size:.74rem; font-weight:700; padding:2px 10px; border-radius:999px;
         border:1px solid #cbd5e1; background:#f1f5f9; color:#475569; white-space:nowrap; }
  .tag-vermelha { background:#fee2e2; border-color:#fca5a5; color:#b91c1c; }
  .tag-ambar { background:#fef3c7; border-color:#fcd34d; color:#b45309; }
  .tag-indigo { background:#e0e7ff; border-color:#a5b4fc; color:#4338ca; }
  .indicadores { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
  .indicador { border:1.5px dashed #cbd5e1; border-radius:10px; padding:10px 14px; }
  .indicador b { display:block; font-size:1.45rem; color:#1e293b; line-height:1.2; }
  .indicador span { font-size:.85rem; color:#64748b; }
  .linha { display:flex; align-items:center; gap:10px; border:1.5px dashed #cbd5e1; border-radius:9px;
           padding:9px 12px; margin-bottom:8px; color:#334155; }
  .linha.atrasada { border-color:#fca5a5; }
  .linha .caixa { width:15px; height:15px; border:2px solid #94a3b8; border-radius:4px; flex:none; }
  .linha .tags { margin-left:auto; display:flex; gap:6px; }
  .cartao-info { background:#f8fafc; border:1px solid #e2e8f0; border-radius:12px; padding:14px 16px; margin-bottom:12px; }
  .cartao-info h4 { margin:0 0 4px; padding:0; font-size:1.02rem; }
  .cartao-info p { margin:0; color:#475569; font-size:.92rem; }
  .topico-titulo { font-size:1.6rem; font-weight:700; color:#1e293b; margin:.4rem 0 .2rem; }
  .barras { position:relative; display:flex; align-items:flex-end; gap:18px; height:170px;
            border:1.5px dashed #cbd5e1; border-radius:10px; padding:26px 18px 30px; }
  .barra { flex:1; display:flex; align-items:flex-end; height:100%; position:relative; }
  .barra .coluna { position:relative; width:100%; border-radius:6px 6px 0 0; }
  .barra .valor { position:absolute; top:-19px; width:100%; text-align:center; font-size:.78rem; font-weight:700; color:#334155; }
  .barra .semana { position:absolute; left:0; bottom:-22px; font-size:.78rem; color:#64748b; }
  .meta { position:absolute; left:10px; right:10px; border-top:2px dashed #16a34a; }
  .meta span { position:absolute; left:0; top:-17px; font-size:.7rem; font-weight:700; color:#16a34a; background:#fff; padding:0 4px; }
  .cobertura { display:flex; align-items:center; gap:12px; margin:8px 0; color:#334155; }
  .cobertura .nome { width:170px; font-size:.92rem; }
  .cobertura .trilho { flex:1; height:11px; background:#e2e8f0; border-radius:6px; overflow:hidden; }
  .cobertura .preenchido { height:100%; border-radius:6px; }
  .cobertura .pct { width:48px; text-align:right; font-weight:700; }
  .alerta { border:1.5px dashed #fcd34d; background:#fffbeb; color:#92400e; border-radius:9px; padding:10px 14px; margin-top:8px; }

  /* botões de dificuldade (C4) */
  .st-key-dif-FACIL button { background:#dcfce7; border-color:#86efac; color:#15803d; }
  .st-key-dif-MEDIO button { background:#fef3c7; border-color:#fcd34d; color:#b45309; }
  .st-key-dif-DIFICIL button { background:#fee2e2; border-color:#fca5a5; color:#b91c1c; }
  .st-key-dif-FACIL button[kind="primary"] { background:#16a34a; border-color:#16a34a; color:#fff; }
  .st-key-dif-MEDIO button[kind="primary"] { background:#d97706; border-color:#d97706; color:#fff; }
  .st-key-dif-DIFICIL button[kind="primary"] { background:#dc2626; border-color:#dc2626; color:#fff; }
  [class*="st-key-dif-"] button { min-height:64px; }
  [class*="st-key-dif-"] button p { line-height:1.35; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def abrir_repositorio() -> Repositorio:
    return Repositorio(Path(__file__).with_name("planejamento.db"))


repo = abrir_repositorio()


def fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def html(conteudo: str) -> None:
    st.markdown(conteudo, unsafe_allow_html=True)


def rastreio(componente: str, estorias: str, caso_de_uso: str) -> None:
    html(f'<div class="rastreio"><b>{componente}</b> · {estorias} · {caso_de_uso}</div>')


def ir_para(pagina: str) -> None:
    st.session_state.pagina = pagina


# ------------------------------------------------------------------ estado da sessão
s = st.session_state
s.setdefault("aluno", None)
s.setdefault("pagina", "painel")
s.setdefault("modo_conta", "criar")
s.setdefault("nd_topicos", [])
s.setdefault("rev", {"ativa": False, "inicio": 0.0, "feitas": 0, "pulados": set(), "escolha": None, "mensagem": None})


def reiniciar_revisao() -> None:
    s.rev = {"ativa": False, "inicio": 0.0, "feitas": 0, "pulados": set(), "escolha": None, "mensagem": None}


def iniciar_revisao() -> None:
    reiniciar_revisao()
    s.rev.update(ativa=True, inicio=time.time())
    s.pagina = "revisao"


# Link direto para a demonstração (ex.: ?demo=1&pagina=relatorios), usado na apresentação.
if "demo" in st.query_params and s.aluno is None:
    s.aluno = repo.conta_demonstracao(date.today())
    pagina_pedida = st.query_params.get("pagina")
    if pagina_pedida in PAGINAS:
        s.pagina = pagina_pedida
    if s.pagina == "revisao":
        iniciar_revisao()
    st.query_params.clear()


# ------------------------------------------------------------------ barra lateral
with st.sidebar:
    st.title("📚 Planejamento de Estudos")
    st.caption("Protótipo executável · Repetição espaçada")
    if s.aluno:
        st.radio("Navegação", list(PAGINAS), format_func=PAGINAS.get, key="pagina", label_visibility="collapsed")
    st.divider()
    st.markdown("**🕒 Simular a data**")
    hoje = st.date_input(
        "Data de hoje",
        value=date.today(),
        format="DD/MM/YYYY",
        key="hoje",
        help="Avance a data para ver as próximas revisões sem esperar os dias reais.",
        on_change=reiniciar_revisao,
    )
    if s.aluno:
        st.divider()
        if st.button("Recarregar dados de exemplo", use_container_width=True,
                     help="Substitui suas disciplinas por 4 semanas de uso simulado."):
            repo.carregar_exemplo(s.aluno.id, hoje)
            reiniciar_revisao()
            st.rerun()
        if st.button("Sair", use_container_width=True):
            s.aluno = None
            reiniciar_revisao()
            st.rerun()
    st.caption(f"Intervalos (RN01): {' · '.join(f'D+{i}' for i in INTERVALOS)}")


# ------------------------------------------------------------------ C1 – Cadastro do Aluno
def criar_conta(hoje: date) -> None:
    try:
        nome, email = validar_conta(
            s.c_nome, s.c_email, s.c_senha, s.c_dias, s.c_aceite, repo.email_cadastrado(s.c_email)
        )
    except ContaInvalida as erro:
        s.c_erro = str(erro)
        return
    s.aluno = repo.criar_aluno(nome, email, s.c_senha, s.c_dias, hoje)
    s.c_erro = None
    s.pagina = "disciplina"  # próximo passo: cadastrar a primeira disciplina


def entrar() -> None:
    aluno = repo.autenticar(s.e_email, s.e_senha)
    if aluno is None:
        s.e_erro = "E-mail ou senha incorretos."
        return
    s.aluno, s.e_erro, s.pagina = aluno, None, "painel"


def entrar_demonstracao(hoje: date) -> None:
    s.aluno = repo.conta_demonstracao(hoje)
    s.pagina = "painel"


def tela_conta(hoje: date) -> None:
    esquerda, direita = st.columns([1.15, 1], gap="large")
    with esquerda:
        with st.container(border=True):
            if s.modo_conta == "criar":
                st.subheader("Criar sua conta")
                st.text_input("Nome completo", placeholder="Ex.: Maria Souza", key="c_nome")
                st.text_input("E-mail", placeholder="seu@email.com", key="c_email")
                st.text_input("Senha", type="password", placeholder="mínimo de 6 caracteres", key="c_senha")
                st.segmented_control(
                    "Hoje, quantos dias por semana você estuda?", options=list(range(8)), key="c_dias"
                )
                st.checkbox("Li e aceito o termo de uso de dados (LGPD)", key="c_aceite")
                if s.get("c_erro"):
                    st.error(s.c_erro)
                a, b = st.columns(2)
                a.button("Já tenho conta · Entrar", on_click=lambda: s.update(modo_conta="entrar"),
                         use_container_width=True)
                b.button("Criar conta →", type="primary", on_click=criar_conta, args=(hoje,),
                         use_container_width=True)
            else:
                st.subheader("Entrar")
                st.text_input("E-mail", placeholder="seu@email.com", key="e_email")
                st.text_input("Senha", type="password", key="e_senha")
                if s.get("e_erro"):
                    st.error(s.e_erro)
                a, b = st.columns(2)
                a.button("Criar conta", on_click=lambda: s.update(modo_conta="criar"), use_container_width=True)
                b.button("Entrar →", type="primary", on_click=entrar, use_container_width=True)
        st.button("Entrar com a conta de demonstração", on_click=entrar_demonstracao, args=(hoje,),
                  use_container_width=True, help="Conta com 4 semanas de uso simulado, ideal para apresentações.")
    with direita:
        html('<h3 style="margin-top:.2rem">A porta de entrada do sistema</h3>')
        html('<div class="cartao-info"><h4>🔒 Dados mínimos (LGPD)</h4>'
             '<p>Só nome, e-mail e senha, com consentimento explícito e opção de excluir a conta.</p></div>')
        html('<div class="cartao-info"><h4>📊 Linha de base do KPI</h4>'
             '<p>O hábito informado no cadastro é a referência para medir os <b>+40% de regularidade</b>.</p></div>')
        html('<div class="cartao-info"><h4>➡️ Próximo passo</h4>'
             '<p>Depois de criar a conta, você cadastra sua primeira disciplina.</p></div>')


# ------------------------------------------------------------------ C2 – Nova disciplina
def adicionar_topico() -> None:
    novo = s.nd_novo.strip()
    if novo:
        s.nd_topicos.append(novo)
    s.nd_novo = ""


def remover_topico(indice: int) -> None:
    s.nd_topicos.pop(indice)


def limpar_formulario_disciplina() -> None:
    s.nd_nome, s.nd_data, s.nd_novo, s.nd_topicos = "", None, "", []


def cancelar_disciplina() -> None:
    limpar_formulario_disciplina()
    s.nd_erro = s.nd_resultado = None
    s.pagina = "painel"


def salvar_disciplina(aluno_id: int, hoje: date) -> None:
    topicos = s.nd_topicos + ([s.nd_novo] if s.nd_novo.strip() else [])
    try:
        nome, topicos = validar_cadastro(s.nd_nome, topicos, s.nd_data, hoje, repo.nomes_disciplinas(aluno_id))
    except CadastroInvalido as erro:
        s.nd_erro, s.nd_resultado = str(erro), None
        return
    data_avaliacao = s.nd_data
    agendados = repo.cadastrar_disciplina(aluno_id, nome, data_avaliacao, topicos, hoje)
    s.nd_erro, s.nd_resultado = None, (nome, data_avaliacao, agendados)
    limpar_formulario_disciplina()


def tela_disciplina(hoje: date) -> None:
    for chave, padrao in (("nd_nome", ""), ("nd_data", None), ("nd_novo", "")):
        s.setdefault(chave, padrao)
    rastreio("C2 Cadastro de Disciplinas & Tópicos", "EU3 · EU4", "UC03 Cadastrar disciplina e tópicos")

    if s.get("nd_resultado"):
        nome, data_avaliacao, agendados = s.nd_resultado
        st.success(f"Disciplina **{nome}** cadastrada com {len(agendados)} tópico(s). "
                   f"Primeira revisão em **{fmt(agendados[0][1])}** (D+1).")
        if data_avaliacao and (data_avaliacao - hoje).days <= 7:
            st.warning("⭐ Avaliação em até 7 dias: os tópicos desta disciplina são prioritários (RN04).")

    with st.container(border=True):
        st.subheader("Nova disciplina")
        st.text_input("Nome da disciplina", placeholder="Ex.: Engenharia de Software", key="nd_nome")
        st.date_input("Data da próxima avaliação", format="DD/MM/YYYY", key="nd_data")
        html('<div class="rotulo" style="margin-top:.2rem">Tópicos</div>')
        for i, topico in enumerate(s.nd_topicos):
            texto, botao = st.columns([12, 1], vertical_alignment="center")
            texto.markdown(f'<div class="linha" style="margin:0">• {escape(topico)}</div>', unsafe_allow_html=True)
            botao.button("✕", key=f"rm-{i}-{topico}", on_click=remover_topico, args=(i,), help="Remover tópico")
        campo, botao = st.columns([12, 1], vertical_alignment="center")
        campo.text_input("Adicionar tópico", placeholder="Adicionar tópico… (Enter)", key="nd_novo",
                         label_visibility="collapsed", on_change=adicionar_topico)
        botao.button("➕", on_click=adicionar_topico, help="Adicionar tópico")

        if s.get("nd_erro"):
            st.error(s.nd_erro)
        _, cancelar, salvar = st.columns([2, 1, 1.4])
        cancelar.button("Cancelar", on_click=cancelar_disciplina, use_container_width=True)
        salvar.button("Salvar disciplina", type="primary", on_click=salvar_disciplina,
                      args=(s.aluno.id, hoje), use_container_width=True)


# ------------------------------------------------------------------ C3 – Painel
def tags_do_item(item) -> str:
    tags = []
    if item.atrasada:
        tags.append('<span class="tag tag-vermelha">atrasada</span>')
    elif item.prioritario:
        tags.append('<span class="tag tag-ambar">⭐ prova próxima</span>')
    tags.append(f'<span class="tag">{rotulo_etapa(item.etapa)}</span>')
    return "".join(tags)


def tela_painel(hoje: date) -> None:
    aluno = s.aluno
    fila = repo.fila_do_dia(aluno.id, hoje)
    atrasadas = sum(i.atrasada for i in fila)
    adesao = repo.adesao(aluno.id, hoje - timedelta(days=28), hoje - timedelta(days=1))

    sino = f'<span class="tag tag-ambar">🔔 {atrasadas} atrasada{"s" if atrasadas != 1 else ""}</span>' if atrasadas else ""
    html(f'<div class="cabecalho"><h2>Olá, {escape(aluno.primeiro_nome)}! 👋</h2>{sino}</div>')
    rastreio("C3 Painel “Revisões de Hoje”", "EU5 · EU6", "UC04 Consultar revisões do dia")

    html(
        '<div class="indicadores">'
        f'<div class="indicador"><b>{len(fila)}</b><span>revisões hoje</span></div>'
        f'<div class="indicador"><b>{repo.dias_seguidos(aluno.id, hoje)}</b><span>dias seguidos</span></div>'
        f'<div class="indicador"><b>{"—" if adesao is None else f"{adesao:.0%}"}</b><span>adesão (4 semanas)</span></div>'
        "</div>"
    )

    html('<div class="rotulo">Revisões de hoje</div>')
    if fila:
        html("".join(
            f'<div class="linha{" atrasada" if i.atrasada else ""}"><div class="caixa"></div>'
            f"{escape(i.disciplina)} — {escape(i.topico)}<div class=\"tags\">{tags_do_item(i)}</div></div>"
            for i in fila
        ))
    else:
        proxima = repo.proxima_data_agendada(aluno.id, hoje)
        st.info("Nenhuma revisão para hoje. 🎉" + (f" Próxima em **{fmt(proxima)}**." if proxima else ""))

    a, b, _ = st.columns([1.3, 1.1, 2])
    a.button("▶ Iniciar revisões", type="primary", on_click=iniciar_revisao, disabled=not fila,
             use_container_width=True)
    b.button("➕ Novo tópico", on_click=ir_para, args=("disciplina",), use_container_width=True)


# ------------------------------------------------------------------ C4 – Sessão de Revisão
@st.fragment(run_every=1)
def cronometro(inicio: float) -> None:
    segundos = int(time.time() - inicio)
    html(f'<div style="text-align:right"><span class="tag">⏱ {segundos // 60:02d}:{segundos % 60:02d}</span></div>')


def escolher(dificuldade: Dificuldade) -> None:
    s.rev["escolha"] = dificuldade


def pular(revisao_id: int) -> None:
    s.rev["pulados"].add(revisao_id)
    s.rev.update(escolha=None, mensagem=None)


def concluir(aluno_id: int, item, hoje: date) -> None:
    dificuldade = s.rev["escolha"]
    etapa, data = repo.concluir_revisao(aluno_id, item.revisao_id, dificuldade, hoje)
    s.rev["feitas"] += 1
    s.rev["escolha"] = None
    s.rev["mensagem"] = (f"“{item.topico}” revisado como **{dificuldade.rotulo}**. "
                         f"Próxima revisão em **{fmt(data)}** ({rotulo_etapa(etapa)}).")


def tela_revisao(hoje: date) -> None:
    aluno, rev = s.aluno, s.rev
    rastreio("C4 Sessão de Revisão", "EU7 · EU8", "UC05 Realizar revisão")
    fila_completa = repo.fila_do_dia(aluno.id, hoje)

    if rev["mensagem"]:
        st.success(rev["mensagem"])

    # Fluxo alternativo (2): nenhuma revisão para hoje / revisões concluídas.
    if not fila_completa:
        if rev["feitas"]:
            st.balloons()
            st.subheader("🎉 Revisões do dia concluídas!")
        else:
            st.info("Nenhuma revisão para hoje.")
        proxima = repo.proxima_data_agendada(aluno.id, hoje)
        if proxima:
            st.write(f"Próxima revisão agendada: **{fmt(proxima)}**.")
        st.button("Voltar ao painel", on_click=lambda: (reiniciar_revisao(), ir_para("painel")))
        return

    if not rev["ativa"]:
        st.subheader("Sessão de revisão")
        st.write(f"Você tem **{len(fila_completa)}** revisão(ões) para hoje.")
        st.button("▶ Iniciar revisões", type="primary", on_click=iniciar_revisao)
        return

    fila = [i for i in fila_completa if i.revisao_id not in rev["pulados"]]
    if not fila:
        st.warning("Você pulou as revisões restantes. Elas continuam pendentes e voltam amanhã como atrasadas (RN03).")
        st.button("Voltar ao painel", on_click=lambda: (reiniciar_revisao(), ir_para("painel")))
        return

    item = fila[0]
    total = rev["feitas"] + len(fila_completa)
    esquerda, direita = st.columns([3, 1], vertical_alignment="center")
    esquerda.markdown(f'<div class="rotulo" style="margin:0">Revisão {rev["feitas"] + 1} de {total}</div>',
                      unsafe_allow_html=True)
    with direita:
        cronometro(rev["inicio"])
    st.progress(rev["feitas"] / total)

    with st.container(border=True):
        tags = [f'<span class="tag">{escape(item.disciplina)}</span>',
                f'<span class="tag tag-indigo">etapa atual: {rotulo_etapa(item.etapa)}</span>']
        if item.atrasada:
            tags.append('<span class="tag tag-vermelha">atrasada</span>')
        if item.prioritario:
            tags.append('<span class="tag tag-ambar">⭐ prova em até 7 dias</span>')
        html(f'<div style="display:flex;gap:6px;flex-wrap:wrap">{"".join(tags)}</div>'
             f'<div class="topico-titulo">{escape(item.topico)}</div>')
        st.caption("Revise o conteúdo com seus materiais (anotações, livro, exercícios) e diga como foi.")

    html('<div class="rotulo">Como foi esta revisão?</div>')
    for coluna, dificuldade in zip(st.columns(3), Dificuldade):
        dias = INTERVALOS[proxima_etapa(item.etapa, dificuldade)]
        with coluna.container(key=f"dif-{dificuldade.value}"):
            st.button(
                f"{EMOJI[dificuldade]} **{dificuldade.rotulo}**  \npróx. em {dias} d",
                type="primary" if rev["escolha"] is dificuldade else "secondary",
                on_click=escolher, args=(dificuldade,), use_container_width=True,
            )

    a, _, b = st.columns([1, 1.6, 1.4])
    a.button("Pular", on_click=pular, args=(item.revisao_id,), use_container_width=True)
    b.button("✓ Concluir revisão", type="primary", disabled=rev["escolha"] is None,
             on_click=concluir, args=(aluno.id, item, hoje), use_container_width=True,
             help=None if rev["escolha"] else "Escolha antes como foi a revisão.")


# ------------------------------------------------------------------ C5 – Relatórios
def grafico_adesao(dados: list[tuple[str, float | None]]) -> str:
    barras = []
    for semana, valor in dados:
        altura = 0 if valor is None else max(valor * 100, 2)
        cor = "#e2e8f0" if valor is None else ("#818cf8" if valor >= META_ADESAO else "#c7d2fe")
        rotulo = "—" if valor is None else f"{valor:.0%}"
        barras.append(
            f'<div class="barra"><div class="coluna" style="height:{altura:.0f}%;background:{cor}">'
            f'<div class="valor">{rotulo}</div></div>'
            f'<div class="semana" style="width:100%;text-align:center">{semana}</div></div>'
        )
    # a área útil das barras ocupa a altura interna; a meta fica a 80% dela
    meta = f'<div class="meta" style="bottom:calc(30px + (100% - 56px) * {META_ADESAO})"><span>meta 80%</span></div>'
    return f'<div class="barras">{meta}{"".join(barras)}</div>'


def tela_relatorios(hoje: date) -> None:
    aluno = s.aluno
    titulo, periodo = st.columns([2, 1], vertical_alignment="bottom")
    titulo.subheader("Meu desempenho")
    semanas = periodo.selectbox("Período", [4, 8], format_func=lambda n: f"Últimas {n} semanas",
                                label_visibility="collapsed")
    rastreio("C5 Relatórios de Desempenho", "EU9 · EU10", "UC06 Consultar relatórios")

    html('<div class="rotulo">Adesão semanal ao cronograma</div>')
    html(grafico_adesao(repo.adesao_semanal(aluno.id, hoje, semanas)))

    # KPI de regularidade: dias com estudo por semana × hábito declarado no cadastro (EU2).
    ontem = hoje - timedelta(days=1)
    dias_estudo = repo.dias_com_estudo(aluno.id, ontem - timedelta(days=7 * semanas - 1), ontem) / semanas
    base = aluno.dias_estudo_semana
    variacao = f" ({(dias_estudo - base) / base:+.0%})" if base else ""
    st.caption(f"Regularidade: **{dias_estudo:.1f} dias/semana** com revisão · "
               f"hábito declarado no cadastro: **{base} dias/semana**{variacao} · meta do KPI: +40%")

    html(f'<div class="rotulo">Cobertura por disciplina · tópicos revisados {REVISOES_PARA_COBERTURA}×</div>')
    cobertura = repo.cobertura_por_disciplina(aluno.id, hoje)
    if not cobertura:
        st.info("Cadastre disciplinas para acompanhar a cobertura.")
        return
    linhas, alertas = [], []
    for c in cobertura:
        pct = c["cobertos"] / c["topicos"] if c["topicos"] else 0
        cor = "#fca5a5" if pct < 0.5 else "#a5b4fc"
        linhas.append(
            f'<div class="cobertura"><span class="nome">{escape(c["disciplina"])}</span>'
            f'<div class="trilho"><div class="preenchido" style="width:{pct:.0%};background:{cor}"></div></div>'
            f'<span class="pct">{pct:.0%}</span></div>'
        )
        dias = c["dias_para_prova"]
        if dias is not None and 0 <= dias <= 7 and c["sem_revisao"]:
            alertas.append(
                f'<div class="alerta">⚠ Prova de <b>{escape(c["disciplina"])}</b> em {dias} dia{"s" if dias != 1 else ""}'
                f' — {c["sem_revisao"]} tópico{"s" if c["sem_revisao"] != 1 else ""} sem revisão</div>'
            )
    html("".join(linhas) + "".join(alertas))


# ------------------------------------------------------------------ consulta das disciplinas
def tela_disciplinas(hoje: date) -> None:
    st.subheader("📚 Minhas disciplinas")
    disciplinas = repo.disciplinas(s.aluno.id)
    if not disciplinas:
        st.info("Nenhuma disciplina cadastrada.")
        st.button("➕ Nova disciplina", on_click=ir_para, args=("disciplina",))
        return
    for d in disciplinas:
        titulo = d["nome"]
        if d["data_avaliacao"]:
            titulo += f" · prova em {fmt(d['data_avaliacao'])} ({(d['data_avaliacao'] - hoje).days} dias)"
        with st.expander(titulo, expanded=True):
            st.dataframe(
                pd.DataFrame({
                    "Tópico": [t["nome"] for t in d["topicos"]],
                    "Etapa atual": [rotulo_etapa(t["etapa"]) for t in d["topicos"]],
                    "Próxima revisão": [fmt(t["proxima"]) if t["proxima"] else "—" for t in d["topicos"]],
                    "Revisões feitas": [t["feitas"] for t in d["topicos"]],
                }),
                hide_index=True,
                use_container_width=True,
            )
            if st.button("Excluir disciplina", key=f"excluir-{d['id']}"):
                repo.excluir_disciplina(s.aluno.id, d["id"])
                st.rerun()


# ------------------------------------------------------------------ roteamento
if s.aluno is None:
    tela_conta(hoje)
else:
    {
        "painel": tela_painel,
        "disciplina": tela_disciplina,
        "revisao": tela_revisao,
        "relatorios": tela_relatorios,
        "disciplinas": tela_disciplinas,
    }[s.pagina](hoje)

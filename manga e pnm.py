import streamlit as st
import pandas as pd
import datetime
import pytz
import os
from supabase import create_client
from dotenv import load_dotenv
from pathlib import Path
import streamlit.components.v1 as components

# ==============================
# CONFIGURAÇÃO
# ==============================
env_path = Path(__file__).parent / "teste.env"
load_dotenv(dotenv_path=env_path)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TZ = pytz.timezone("America/Sao_Paulo")

st.set_page_config(page_title="Apontamento MANGA / PNM", layout="wide")

# ==============================
# UTIL
# ==============================
def status_emoji_para_texto(emoji):
    return {"✅": "Conforme", "❌": "Não Conforme", "🟡": "N/A"}.get(emoji, "Indefinido")

# ==============================
# APONTAMENTO
# ==============================
def salvar_apontamento(numero_serie, op, tipo_producao, usuario):

    check = supabase.table("apontamentos_manga_pnm") \
        .select("id") \
        .eq("numero_serie", numero_serie) \
        .execute()

    if check.data:
        return False, f"Série {numero_serie} já apontada."

    supabase.table("apontamentos_manga_pnm").insert({
        "numero_serie": numero_serie,
        "op": op,
        "tipo_producao": tipo_producao,
        "usuario": usuario,
        "data_hora": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }).execute()

    st.cache_data.clear()
    return True, None


def carregar_apontamentos():
    data = supabase.table("apontamentos_manga_pnm") \
        .select("*") \
        .order("data_hora", desc=True) \
        .limit(1000) \
        .execute()

    df = pd.DataFrame(data.data)
    if not df.empty:
        df["data_hora"] = pd.to_datetime(df["data_hora"], utc=True).dt.tz_convert(TZ)
    return df

# ==============================
# CHECKLIST – CARREGAMENTO COMPLETO
# ==============================
def carregar_checklists_manga_pnm_detalhes():
    data_total = []
    inicio = 0
    passo = 1000

    while True:
        resp = supabase.table("checklists_manga_pnm_detalhes") \
            .select("*") \
            .range(inicio, inicio + passo - 1) \
            .execute()

        if not resp.data:
            break

        data_total.extend(resp.data)
        inicio += passo

    return pd.DataFrame(data_total)

# ==============================
# CALLBACK LEITOR
# ==============================
def processar_leitura():
    leitura = st.session_state.get("input_leitor", "").strip()
    if not leitura:
        return

    if len(leitura) == 9:
        st.session_state["numero_serie"] = leitura
        st.session_state["erro"] = None

    elif len(leitura) == 11:
        if not st.session_state.get("numero_serie"):
            st.session_state["erro"] = "⚠️ Leia primeiro o número de série"
        else:
            st.session_state["op"] = leitura
            sucesso, erro = salvar_apontamento(
                st.session_state["numero_serie"],
                st.session_state["op"],
                st.session_state["tipo_producao"],
                st.session_state.get("usuario", "Operador_Logado")
            )

            if sucesso:
                st.session_state["sucesso"] = "✅ Apontamento realizado"
                st.session_state["numero_serie"] = ""
                st.session_state["op"] = ""
            else:
                st.session_state["erro"] = erro

    st.session_state["input_leitor"] = ""

# ==============================
# CHECKLIST DE QUALIDADE
# ==============================
def checklist_qualidade_manga_pnm(numero_serie, tipo_producao, usuario, op):

    st.markdown(f"## ✔️ Checklist – Série: {numero_serie} | OP: {op} | {tipo_producao}")

    perguntas = [
        "Etiqueta do produto conforme?",
        "Placa do Inmetro conforme?",
        "Etiqueta ABS conforme?",
        "Rodagem correta?",
        "Graxeiras e anéis ok?",
        "Sistema de atuação correto?",
        "Catraca correta?",
        "Tampa do cubo conforme?",
        "Pintura do eixo conforme?",
        "Solda conforme?",
        "Caixas corretas?",
        "Etiqueta pede suspensor?",
        "Etiqueta pede suporte bolsa?",
        "Etiqueta pede mão francesa?"
    ]

    if tipo_producao == "MANGA":
        perguntas.append("Grau do Manga conforme etiqueta?")

    resultados = {}

    with st.form(key=f"form_{numero_serie}"):
        for i, p in enumerate(perguntas, start=1):
            col1, col2 = st.columns([6, 2])
            col1.markdown(f"**{i}. {p}**")
            resultados[i] = col2.radio(
                "",
                ["✅", "❌", "🟡"],
                index=None,
                horizontal=True,
                key=f"{numero_serie}_{i}"
            )

        submit = st.form_submit_button("💾 Salvar Checklist")

    if submit:
        if any(v is None for v in resultados.values()):
            st.error("⚠️ Responda todos os itens")
            return

        registros = [{
            "numero_serie": numero_serie,
            "op": op,
            "tipo_producao": tipo_producao,
            "item": f"ITEM_{i}",
            "status": status_emoji_para_texto(resultados[i]),
            "usuario": usuario,
            "data_hora": datetime.datetime.now(datetime.timezone.utc).isoformat()
        } for i in resultados]

        supabase.table("checklists_manga_pnm_detalhes").insert(registros).execute()

        st.cache_data.clear()
        st.success("✅ Checklist salvo")
        st.rerun()

# ==============================
# PÁGINA APONTAMENTO
# ==============================
def pagina_apontamento():
    st.title("📦 Apontamento MANGA / PNM")

    st.radio("Tipo do Produto", ["MANGA", "PNM"], key="tipo_producao", horizontal=True)

    st.text_input("Leitor", key="input_leitor", on_change=processar_leitura)

    col1, col2 = st.columns(2)
    col1.markdown(f"Série: **{st.session_state.get('numero_serie','-')}**")
    col2.markdown(f"OP: **{st.session_state.get('op','-')}**")

    if st.session_state.get("erro"):
        st.error(st.session_state["erro"])
        st.session_state["erro"] = None

    if st.session_state.get("sucesso"):
        st.success(st.session_state["sucesso"])
        st.session_state["sucesso"] = None

# ==============================
# PÁGINA CHECKLIST (SEM BUG)
# ==============================
def pagina_checklist():
    st.title("🧾 Checklist de Qualidade")

    df_apont = carregar_apontamentos()
    hoje = datetime.datetime.now(TZ).date()

    df_hoje = df_apont[df_apont["data_hora"].dt.date == hoje]

    if df_hoje.empty:
        st.info("Nenhum apontamento hoje")
        return

    df_checks = carregar_checklists_manga_pnm_detalhes()
    series_com_check = df_checks["numero_serie"].unique() if not df_checks.empty else []

    pendentes = [
        s for s in df_hoje["numero_serie"].unique()
        if s not in series_com_check
    ]

    if not pendentes:
        st.success("✅ Todos os itens já foram inspecionados")
        return

    numero_serie = st.selectbox("Selecione a série", pendentes)

    linha = df_hoje[df_hoje["numero_serie"] == numero_serie].iloc[0]

    checklist_qualidade_manga_pnm(
        numero_serie,
        linha["tipo_producao"],
        st.session_state.get("usuario", "Operador_Logado"),
        linha["op"]
    )

# ==============================
# APP
# ==============================
def app():
    if "usuario" not in st.session_state:
        st.session_state["usuario"] = "Operador_Logado"

    menu = st.sidebar.radio("Menu", ["Apontamento", "Checklist"])

    if menu == "Apontamento":
        pagina_apontamento()
    else:
        pagina_checklist()

# ==============================
# EXECUÇÃO
# ==============================
if __name__ == "__main__":
    app()



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
load_dotenv(env_path)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TZ = pytz.timezone("America/Sao_Paulo")

st.set_page_config(page_title="Apontamento MANGA / PNM", layout="wide")

# ==============================
# UTIL
# ==============================
def status_emoji_para_texto(emoji):
    return {"✅": "Conforme", "❌": "Não Conforme", "🟡": "N/A"}.get(emoji)

# ==============================
# APONTAMENTOS
# ==============================
def carregar_apontamentos():
    data = supabase.table("apontamentos_manga_pnm") \
        .select("*") \
        .order("data_hora", desc=True) \
        .execute()

    df = pd.DataFrame(data.data)
    if not df.empty:
        df["data_hora"] = pd.to_datetime(df["data_hora"], utc=True).dt.tz_convert(TZ)
    return df

# ==============================
# CHECKLIST
# ==============================
def checklist_qualidade_manga_pnm(numero_serie, tipo_producao, usuario, op):

    st.markdown(f"## ✔️ Checklist – Série: {numero_serie} | OP: {op} | {tipo_producao}")

    perguntas = [
        "Etiqueta do produto conforme?",
        "Placa Inmetro correta?",
        "Teste ABS aprovado?",
        "Rodagem correta?",
        "Graxeiras ok?",
        "Sistema de atuação correto?",
        "Catraca correta?",
        "Tampa do cubo correta?",
        "Pintura conforme?",
        "Solda conforme?",
        "Caixas corretas?",
        "Etiqueta pede suspensor?",
        "Etiqueta pede suporte bolsa?",
        "Etiqueta pede mão francesa?"
    ]

    resultados = {}

    with st.form(f"form_{numero_serie}", clear_on_submit=False):
        for i, pergunta in enumerate(perguntas):
            resultados[i] = st.radio(
                pergunta,
                ["✅", "❌", "🟡"],
                horizontal=True,
                key=f"{numero_serie}_{i}"
            )

        salvar = st.form_submit_button("💾 Salvar Checklist")

        if salvar:
            registros = [{
                "numero_serie": numero_serie,
                "tipo_producao": tipo_producao,
                "item": perguntas[i],
                "status": status_emoji_para_texto(v),
                "usuario": usuario,
                "data_hora": datetime.datetime.now(datetime.timezone.utc).isoformat()
            } for i, v in resultados.items()]

            supabase.table("checklists_manga_pnm_detalhes") \
                .insert(registros) \
                .execute()

            # ✅ RESET CORRETO DO SELECTBOX
            if "serie_checklist" in st.session_state:
                del st.session_state["serie_checklist"]

            st.success("✅ Checklist salvo com sucesso")
            st.rerun()

# ==============================
# PÁGINA CHECKLIST (CORRIGIDA)
# ==============================
def pagina_checklist():
    st.title("🧾 Checklist de Qualidade")

    df_apont = carregar_apontamentos()
    hoje = datetime.datetime.now(TZ).date()
    df_hoje = df_apont[df_apont["data_hora"].dt.date == hoje]

    if df_hoje.empty:
        st.info("Nenhum apontamento hoje")
        return

    check = supabase.table("checklists_manga_pnm_detalhes") \
        .select("numero_serie") \
        .execute()

    series_com_checklist = {c["numero_serie"] for c in check.data} if check.data else set()

    pendentes = df_hoje[~df_hoje["numero_serie"].isin(series_com_checklist)]

    if pendentes.empty:
        st.success("✅ Todos os checklists já foram feitos")
        return

    if "serie_checklist" not in st.session_state:
        st.session_state["serie_checklist"] = pendentes["numero_serie"].iloc[0]

    numero_serie = st.selectbox(
        "Selecione a série",
        pendentes["numero_serie"].unique(),
        key="serie_checklist"
    )

    linha_df = pendentes[pendentes["numero_serie"] == numero_serie]
    if linha_df.empty:
        if "serie_checklist" in st.session_state:
            del st.session_state["serie_checklist"]
        st.rerun()
        return

    linha = linha_df.iloc[0]

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

    if menu == "Checklist":
        pagina_checklist()

if __name__ == "__main__":
    app()

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
# SUPABASE – APONTAMENTO
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
        .limit(50) \
        .execute()

    df = pd.DataFrame(data.data)
    if not df.empty:
        df["data_hora"] = pd.to_datetime(df["data_hora"], utc=True).dt.tz_convert(TZ)
    return df

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
            sucesso, erro = salvar_apontamento(
                st.session_state["numero_serie"],
                leitura,
                st.session_state.get("tipo_producao"),
                st.session_state.get("usuario", "Operador_Logado")
            )

            if sucesso:
                st.session_state["sucesso"] = "✅ Apontamento realizado"
                st.session_state["numero_serie"] = ""
            else:
                st.session_state["erro"] = erro

    st.session_state["input_leitor"] = ""

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

    with st.form(f"form_{numero_serie}"):
        for i, p in enumerate(perguntas):
            resultados[i] = st.radio(
                p, ["✅", "❌", "🟡"],
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

            # 🔑 CONTROLE CORRETO DE ESTADO
            st.session_state["serie_checklist"] = None
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

    df_linha = pendentes[pendentes["numero_serie"] == numero_serie]

    if df_linha.empty:
        st.session_state["serie_checklist"] = None
        st.rerun()
        return

    linha = df_linha.iloc[0]

    checklist_qualidade_manga_pnm(
        numero_serie,
        linha["tipo_producao"],
        st.session_state.get("usuario", "Operador_Logado"),
        linha["op"]
    )

# ==============================
# APONTAMENTO
# ==============================
def pagina_apontamento():
    st.title("📦 Apontamento MANGA / PNM")

    st.radio("Tipo do Produto", ["MANGA", "PNM"], key="tipo_producao", horizontal=True)

    st.text_input(
        "Leitor",
        key="input_leitor",
        on_change=processar_leitura,
        label_visibility="collapsed"
    )

    components.html("""
    <script>
    const i = window.parent.document.querySelector('input[id^="input_leitor"]');
    if(i){ i.focus(); }
    </script>
    """, height=0)

    st.markdown(f"📦 Série: **{st.session_state.get('numero_serie','-')}**")

    if st.session_state.get("erro"):
        st.error(st.session_state["erro"])
        st.session_state["erro"] = None

    if st.session_state.get("sucesso"):
        st.success(st.session_state["sucesso"])
        st.session_state["sucesso"] = None

    df = carregar_apontamentos()
    if not df.empty:
        st.dataframe(df, use_container_width=True)

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

if __name__ == "__main__":
    app()

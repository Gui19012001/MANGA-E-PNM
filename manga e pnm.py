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
# FUNÇÕES SUPABASE – APONTAMENTO
# ==============================
def salvar_apontamento(numero_serie, op, tipo_producao, usuario):
    check = supabase.table("apontamentos_manga_pnm") \
        .select("id") \
        .eq("numero_serie", numero_serie) \
        .execute()

    if check.data:
        return False, f"Série {numero_serie} já apontada."

    try:
        supabase.table("apontamentos_manga_pnm").insert({
            "numero_serie": numero_serie,
            "op": op,
            "tipo_producao": tipo_producao,
            "usuario": usuario,
            "data_hora": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }).execute()

        st.cache_data.clear()
        return True, None

    except Exception as e:
        return False, str(e)


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
# CALLBACK DO LEITOR
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
                st.session_state.get("tipo_producao"),
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
        "Etiqueta do produto – As informações estão corretas / legíveis conforme modelo e gravação do eixo?",
        "Placa do Inmetro está correta / fixada e legível?",
        "Etiqueta do ABS está conforme?",
        "Rodagem – tipo correto?",
        "Graxeiras e Anéis elásticos estão em perfeito estado?",
        "Sistema de atuação correto?",
        "Catraca do freio correta?",
        "Tampa do cubo correta?",
        "Pintura do eixo conforme?",
        "Cordões de solda conformes?",
        "As caixas estão corretas?",
        "Etiqueta pede suspensor?",
        "Etiqueta pede Suporte da Bolsa?",
        "Etiqueta pede Mão Francesa?"
    ]

    if tipo_producao == "MANGA":
        perguntas.append("Grau do Manga conforme etiqueta?")

    item_keys = {
        i + 1: f"ITEM_{i + 1}" for i in range(len(perguntas))
    }

    resultados = {}

    with st.form(key=f"form_checklist_{numero_serie}"):

        for i, pergunta in enumerate(perguntas, start=1):
            col1, col2 = st.columns([6, 2])
            col1.markdown(f"**{i}. {pergunta}**")
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

        registros = []
        for i in resultados:
            registros.append({
                "numero_serie": numero_serie,
                "tipo_producao": tipo_producao,
                "item": item_keys[i],
                "status": status_emoji_para_texto(resultados[i]),
                "usuario": usuario,
                "data_hora": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })

        try:
            supabase.table("checklists_manga_pnm_detalhes").insert(registros).execute()

            st.success("✅ Checklist salvo com sucesso")

            # 🔑 LIMPA SELEÇÃO E AVANÇA
            st.session_state["serie_checklist"] = None
            st.cache_data.clear()
            st.rerun()

        except Exception as e:
            st.error(f"❌ Erro ao salvar checklist: {e}")

# ==============================
# PÁGINA CHECKLIST
# ==============================
def pagina_checklist():

    st.title("🧾 Checklist de Qualidade")

    if "serie_checklist" not in st.session_state:
        st.session_state["serie_checklist"] = None

    df_apont = carregar_apontamentos()
    hoje = datetime.datetime.now(TZ).date()

    df_hoje = df_apont[df_apont["data_hora"].dt.date == hoje]

    if df_hoje.empty:
        st.info("Nenhum apontamento hoje")
        return

    checks = supabase.table("checklists_manga_pnm_detalhes") \
        .select("numero_serie") \
        .execute()

    feitos = {c["numero_serie"] for c in checks.data} if checks.data else set()

    pendentes = df_hoje[~df_hoje["numero_serie"].isin(feitos)]

    if pendentes.empty:
        st.success("✅ Todos os checklists de hoje já foram realizados")
        return

    numero_serie = st.selectbox(
        "Selecione a série",
        pendentes["numero_serie"].tolist(),
        key="serie_checklist"
    )

    linha = pendentes[pendentes["numero_serie"] == numero_serie].iloc[0]

    checklist_qualidade_manga_pnm(
        numero_serie,
        linha["tipo_producao"],
        st.session_state.get("usuario", "Operador_Logado"),
        linha["op"]
    )

# ==============================
# APP PRINCIPAL
# ==============================
def app():
    if "usuario" not in st.session_state:
        st.session_state["usuario"] = "Operador_Logado"

    menu = st.sidebar.radio("Menu", ["Apontamento", "Checklist"])

    if menu == "Checklist":
        pagina_checklist()

# ==============================
# EXECUÇÃO
# ==============================
if __name__ == "__main__":
    app()

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
        .limit(20) \
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

    # Nº de Série
    if len(leitura) == 9:
        st.session_state["numero_serie"] = leitura
        st.session_state["erro"] = None

    # OP
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
        "Etiqueta do produto – As informações estão corretas / legíveis?",
        "Placa do Inmetro correta e legível?",
        "Etiqueta do ABS conforme?",
        "Rodagem – tipo correto?",
        "Graxeiras e anéis elásticos OK?",
        "Sistema de atuação correto?",
        "Catraca do freio correta?",
        "Tampa do cubo correta?",
        "Pintura do eixo conforme?",
        "Solda conforme?",
        "Caixas corretas?",
        "Etiqueta pede suspensor?",
        "Etiqueta pede suporte da bolsa?",
        "Etiqueta pede mão francesa?"
    ]

    if tipo_producao == "MANGA":
        perguntas.append("Grau do Manga conforme etiqueta?")

    item_keys = {
        i + 1: f"ITEM_{i+1}" for i in range(len(perguntas))
    }

    resultados = {}
    st.caption("✅ Conforme | ❌ Não Conforme | 🟡 N/A")

    with st.form(f"form_{numero_serie}"):
        for i, pergunta in enumerate(perguntas, start=1):
            cols = st.columns([8, 2])
            cols[0].markdown(f"**{i}. {pergunta}**")
            resultados[i] = cols[1].radio(
                "",
                ["✅", "❌", "🟡"],
                index=None,
                horizontal=True,
                key=f"{numero_serie}_{i}"
            )

        salvar = st.form_submit_button("💾 Salvar Checklist")

        if salvar:
            if any(v is None for v in resultados.values()):
                st.error("⚠️ Responda todos os itens")
                return

            # 🔒 Evita duplicidade
            existe = supabase.table("checklists_manga_pnm") \
                .select("id") \
                .eq("numero_serie", numero_serie) \
                .execute()

            if existe.data:
                st.warning("⚠️ Checklist já realizado para esta série")
                return

            agora = datetime.datetime.now(datetime.timezone.utc)

            detalhes = [{
                "numero_serie": numero_serie,
                "tipo_producao": tipo_producao,
                "item": item_keys[i],
                "status": status_emoji_para_texto(resultados[i]),
                "usuario": usuario,
                "data_hora": agora.isoformat()
            } for i in resultados]

            try:
                supabase.table("checklists_manga_pnm_detalhes").insert(detalhes).execute()
                supabase.table("checklists_manga_pnm").insert({
                    "numero_serie": numero_serie,
                    "tipo_producao": tipo_producao,
                    "usuario": usuario,
                    "data_hora": agora.isoformat()
                }).execute()

                st.cache_data.clear()
                st.success("✅ Checklist salvo com sucesso")
                st.rerun()

            except Exception as e:
                st.error("❌ Erro ao salvar checklist")
                st.exception(e)


# ==============================
# PÁGINA APONTAMENTO
# ==============================
def pagina_apontamento():
    st.title("📦 Apontamento MANGA / PNM")

    st.radio(
        "Tipo do Produto",
        ["MANGA", "PNM"],
        key="tipo_producao",
        horizontal=True
    )

    st.text_input(
        "Leitor",
        key="input_leitor",
        placeholder="Aproxime o leitor...",
        label_visibility="collapsed",
        on_change=processar_leitura
    )

    components.html("""
    <script>
    function focar(){
        const i = window.parent.document.querySelector('input[id^="input_leitor"]');
        if(i){ i.focus(); }
    }
    focar();
    new MutationObserver(focar).observe(
        window.parent.document.body,
        {childList:true, subtree:true}
    );
    </script>
    """, height=0)

    col1, col2 = st.columns(2)
    col1.markdown(f"📦 Série: **{st.session_state.get('numero_serie','-')}**")
    col2.markdown(f"🧾 OP: **{st.session_state.get('op','-')}**")

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
# PÁGINA CHECKLIST
# ==============================
def pagina_checklist():
    st.title("🧾 Checklist de Qualidade")

    df = carregar_apontamentos()
    hoje = datetime.datetime.now(TZ).date()
    df_hoje = df[df["data_hora"].dt.date == hoje]

    if df_hoje.empty:
        st.info("Nenhum apontamento hoje")
        return

    try:
        res = supabase.table("checklists_manga_pnm") \
            .select("numero_serie") \
            .execute()

        series_com_checklist = {r["numero_serie"] for r in res.data} if res.data else set()

    except Exception:
        series_com_checklist = set()

    pendentes = df_hoje[~df_hoje["numero_serie"].isin(series_com_checklist)]

    if pendentes.empty:
        st.success("✅ Todos os itens já possuem checklist")
        return

    serie = st.selectbox("Selecione a série", pendentes["numero_serie"].unique())
    linha = pendentes[pendentes["numero_serie"] == serie].iloc[0]

    checklist_qualidade_manga_pnm(
        serie,
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

    if menu == "Apontamento":
        pagina_apontamento()
    else:
        pagina_checklist()

# ==============================
# EXECUÇÃO
# ==============================
if __name__ == "__main__":
    app()


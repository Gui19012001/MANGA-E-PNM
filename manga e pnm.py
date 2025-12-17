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
# FUNÇÕES SUPABASE – APONTAMENTO
# ==============================
def salvar_apontamento(numero_serie, tipo, usuario):

    check = supabase.table("apontamentos_manga_pnm") \
        .select("id") \
        .eq("numero_serie", numero_serie) \
        .eq("tipo", tipo) \
        .execute()

    if check.data:
        return False, f"Série {numero_serie} já apontada para {tipo}"

    data_hora = datetime.datetime.now(datetime.timezone.utc).isoformat()

    try:
        supabase.table("apontamentos_manga_pnm").insert({
            "numero_serie": numero_serie,
            "tipo": tipo,
            "usuario": usuario,
            "data_hora": data_hora
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
# FUNÇÕES SUPABASE – CHECKLIST
# ==============================
def carregar_checklists():
    data = supabase.table("checklists_manga_pnm_detalhes") \
        .select("*") \
        .execute()
    return pd.DataFrame(data.data)


def salvar_checklist(numero_serie, tipo, respostas, usuario):

    erros = []

    for item, status in respostas.items():
        try:
            supabase.table("checklists_manga_pnm_detalhes").insert({
                "numero_serie": numero_serie,
                "item": item,
                "status": status,
                "usuario": usuario,
                "tipo": tipo,
                "data_hora": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }).execute()
        except Exception as e:
            erros.append(str(e))

    if erros:
        return False, "; ".join(erros)

    st.cache_data.clear()
    return True, None


# ==============================
# CALLBACK DO LEITOR
# ==============================
def processar_leitura():
    leitura = st.session_state.get("input_leitor", "").strip()
    if not leitura:
        return

    tipo = st.session_state.get("tipo")

    if not tipo:
        st.session_state["erro"] = "⚠️ Selecione MANGA ou PNM antes da leitura"
        st.session_state["input_leitor"] = ""
        return

    sucesso, erro = salvar_apontamento(
        leitura,
        tipo,
        st.session_state.get("usuario", "Operador_Logado")
    )

    if sucesso:
        st.session_state["sucesso"] = "✅ Apontamento realizado"
    else:
        st.session_state["erro"] = erro

    st.session_state["input_leitor"] = ""


# ==============================
# CHECKLIST DE QUALIDADE
# ==============================
def checklist_qualidade(numero_serie, tipo):

    st.subheader(f"Checklist – {numero_serie} ({tipo})")

    perguntas = {
        "ETIQUETA": "Etiqueta conforme?",
        "CODIGO": "Código legível?",
        "DIMENSAO": "Dimensão correta?",
        "ACABAMENTO": "Acabamento conforme?",
        "AVARIAS": "Produto sem avarias?"
    }

    respostas = {}

    with st.form(f"form_{numero_serie}"):

        for key, pergunta in perguntas.items():
            respostas[key] = st.radio(
                pergunta,
                ["Conforme", "Não Conforme", "N/A"],
                index=None,
                horizontal=True,
                key=f"{numero_serie}_{key}"
            )

        submit = st.form_submit_button("💾 Salvar Checklist")

    if submit:
        if any(v is None for v in respostas.values()):
            st.error("⚠️ Responda todas as perguntas")
            return

        sucesso, erro = salvar_checklist(
            numero_serie,
            tipo,
            respostas,
            st.session_state["usuario"]
        )

        if sucesso:
            st.success("Checklist salvo com sucesso")
            st.rerun()
        else:
            st.error(erro)


# ==============================
# PÁGINAS
# ==============================
def pagina_apontamento():
    st.title("📦 Apontamento MANGA / PNM")

    st.radio(
        "Tipo do Produto",
        ["MANGA", "PNM"],
        key="tipo",
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

    if st.session_state.get("erro"):
        st.error(st.session_state["erro"])
        st.session_state["erro"] = None

    if st.session_state.get("sucesso"):
        st.success(st.session_state["sucesso"])
        st.session_state["sucesso"] = None

    st.markdown("---")

    df = carregar_apontamentos()
    if not df.empty:
        st.dataframe(df, use_container_width=True)


def pagina_checklist():
    st.title("🧾 Checklist de Qualidade")

    df_apont = carregar_apontamentos()
    df_check = carregar_checklists()

    hoje = datetime.datetime.now(TZ).date()
    df_apont = df_apont[df_apont["data_hora"].dt.date == hoje]

    feitos = set(
        zip(df_check["numero_serie"], df_check["tipo"])
    ) if not df_check.empty else set()

    pendentes = [
        (r.numero_serie, r.tipo)
        for r in df_apont.itertuples()
        if (r.numero_serie, r.tipo) not in feitos
    ]

    if not pendentes:
        st.info("Nenhum checklist pendente hoje")
        return

    numero_serie, tipo = st.selectbox(
        "Selecione para inspeção",
        pendentes,
        format_func=lambda x: f"{x[0]} - {x[1]}"
    )

    checklist_qualidade(numero_serie, tipo)


# ==============================
# APP PRINCIPAL
# ==============================
def app():

    if "usuario" not in st.session_state:
        st.session_state["usuario"] = "Operador_Logado"

    menu = st.sidebar.radio(
        "Menu",
        ["Apontamento", "Checklist de Qualidade"]
    )

    if menu == "Apontamento":
        pagina_apontamento()
    else:
        pagina_checklist()


# ==============================
# EXECUÇÃO
# ==============================
if __name__ == "__main__":
    app()

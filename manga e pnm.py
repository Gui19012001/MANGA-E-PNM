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
    return {
        "✅": "Conforme",
        "❌": "Não Conforme",
        "🟡": "N/A"
    }.get(emoji)

# ==============================
# FUNÇÕES SUPABASE – APONTAMENTO
# ==============================
def salvar_apontamento(numero_serie, tipo_producao, usuario):

    check = supabase.table("apontamentos_manga_pnm") \
        .select("id") \
        .eq("numero_serie", numero_serie) \
        .eq("tipo_producao", tipo_producao) \
        .execute()

    if check.data:
        return False, f"Série {numero_serie} já apontada para {tipo_producao}"

    try:
        supabase.table("apontamentos_manga_pnm").insert({
            "numero_serie": numero_serie,
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
    if not df.empty and "data_hora" in df.columns:
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


def salvar_checklist(numero_serie, tipo_producao, dados, usuario):

    erros = []

    for item, info in dados.items():
        try:
            supabase.table("checklists_manga_pnm_detalhes").insert({
                "numero_serie": numero_serie,
                "item": item,
                "status": info["status"],
                "usuario": usuario,
                "tipo_producao": tipo_producao,
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

    tipo_producao = st.session_state.get("tipo_producao")

    if not tipo_producao:
        st.session_state["erro"] = "⚠️ Selecione MANGA ou PNM antes da leitura"
        st.session_state["input_leitor"] = ""
        return

    sucesso, erro = salvar_apontamento(
        leitura,
        tipo_producao,
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
def checklist_qualidade_manga_pnm(numero_serie, tipo_producao, usuario):
    import time

    st.markdown(f"## ✔️ Checklist de Qualidade – Nº de Série: {numero_serie} ({tipo_producao})")

    perguntas = [
        "Etiqueta do produto – As informações estão corretas / legíveis?",
        "Placa do Inmetro está correta / fixada e legível?",
        "Etiqueta do ABS está conforme? Número compatível?",
        "Rodagem – tipo correto?",
        "Graxeiras e Anéis elásticos estão em perfeito estado?",
        "Sistema de atuação correto?",
        "Catraca do freio correta?",
        "Tampa do cubo correta?",
        "Pintura do eixo conforme?",
        "Cordões de solda conformes?"
    ]

    item_keys = {
        1: "ETIQUETA",
        2: "PLACA_INMETRO",
        3: "TESTE_ABS",
        4: "RODAGEM",
        5: "GRAXEIRAS",
        6: "SISTEMA_ATUACAO",
        7: "CATRACA",
        8: "TAMPA_CUBO",
        9: "PINTURA",
        10: "SOLDA"
    }

    resultados = {}
    modelos = {}

    with st.form(key=f"form_checklist_{numero_serie}", clear_on_submit=False):
        for i, pergunta in enumerate(perguntas, start=1):
            cols = st.columns([7, 3])
            cols[0].markdown(f"**{i}. {pergunta}**")
            escolha = cols[1].radio(
                "",
                ["✅", "❌", "🟡"],
                key=f"{numero_serie}_{i}",
                horizontal=True,
                index=None,
                label_visibility="collapsed"
            )
            resultados[i] = escolha
            modelos[i] = None

        submit = st.form_submit_button("💾 Salvar Checklist")

    if submit:
        if any(v is None for v in resultados.values()):
            st.error("⚠️ Responda todos os itens")
            return

        dados = {}
        for i, resp in resultados.items():
            dados[item_keys[i]] = {
                "status": status_emoji_para_texto(resp),
                "obs": None
            }

        ok, erro = salvar_checklist(numero_serie, tipo_producao, dados, usuario)

        if ok:
            st.success("✅ Checklist salvo com sucesso")
            time.sleep(0.5)
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

    if st.session_state.get("erro"):
        st.error(st.session_state["erro"])
        st.session_state["erro"] = None

    if st.session_state.get("sucesso"):
        st.success(st.session_state["sucesso"])
        st.session_state["sucesso"] = None

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
        zip(df_check["numero_serie"], df_check["tipo_producao"])
    ) if not df_check.empty else set()

    pendentes = [
        (r.numero_serie, r.tipo_producao)
        for r in df_apont.itertuples()
        if (r.numero_serie, r.tipo_producao) not in feitos
    ]

    if not pendentes:
        st.info("Nenhum checklist pendente hoje")
        return

    numero_serie, tipo_producao = st.selectbox(
        "Selecione para inspeção",
        pendentes,
        format_func=lambda x: f"{x[0]} - {x[1]}"
    )

    checklist_qualidade_manga_pnm(
        numero_serie,
        tipo_producao,
        st.session_state.get("usuario", "Operador_Logado")
    )

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


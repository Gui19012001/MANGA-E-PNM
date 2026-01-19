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
    st.markdown(
        f"## ✔️ Checklist – Série: {numero_serie} | OP: {op} | {tipo_producao}"
    )

    perguntas = [
        "Etiqueta do produto – As informações estão corretas / legíveis conforme modelo e gravação do eixo?",
        "Placa do Inmetro está correta / fixada e legível? Número corresponde à viga? Gravação do número de série da viga está legível e pintada?",
        "Etiqueta do ABS está conforme? Com número de série compatível ao da viga? Teste do ABS está aprovado?",
        "Rodagem – tipo correto? Especifique o modelo",
        "Graxeiras e Anéis elásticos estão em perfeito estado?",
        "Sistema de atuação correto? Springs ou cuícas em perfeitas condições? Especifique o modelo:",
        "Catraca do freio correta? Especifique modelo",
        "Tampa do cubo correta, livre de avarias e pintura nos critérios? As tampas dos cubos dos ambos os lados são iguais?",
        "Pintura do eixo livre de oxidação, isento de escorrimento, pontos sem tinta e camada conforme padrão?",
        "Os cordões de solda do eixo estão conformes?",
        "As caixas estão corretas? Escreva qual o modelo:",
        "Etiqueta pede suspensor?",
        "Etiqueta pede Suporte da Bolsa?",
        "Etiqueta pede Mão Francesa?"
    ]

    if tipo_producao == "MANGA":
        perguntas.append("Grau do Manga conforme etiqueta do produto? Escreva qual o Grau:")

    item_keys = {
        1: "ETIQUETA",
        2: "PLACA_IMETRO_E_NUMERO_SERIE",
        3: "TESTE_ABS",
        4: "RODAGEM",
        5: "GRAXEIRAS",
        6: "SISTEMA_ATUACAO",
        7: "CATRACA_FREIO",
        8: "TAMPA_CUBO",
        9: "PINTURA_EIXO",
        10: "SOLDA",
        11: "CAIXAS",
        12: "FALTA SUSPENSOR",
        13: "FALTA SPT_BOLSA",
        14: "FALTA MAO_FRANCESA",
        15: "GRAU DIVERGENTE"
    }

    opcoes_modelos = {
        4: ["Single", "Aço", "Alumínio", "N/A"],
        6: ["Spring", "Cuíca", "N/A"],
        7: ["Automático", "Manual", "N/A"],
        10: ["Conforme", "Respingo", "Falta de cordão", "Porosidade", "Falta de Fusão"]
    }

    resultados = {}
    complementos = {}

    st.caption("✅ = Conforme | ❌ = Não Conforme | 🟡 = N/A")

    with st.form(key=f"form_checklist_{numero_serie}", clear_on_submit=False):
        for i, pergunta in enumerate(perguntas, start=1):
            cols = st.columns([7, 2, 2])

            # Pergunta
            cols[0].markdown(f"**{i}. {pergunta}**")

            # Status padrão
            resultados[i] = cols[1].radio(
                "",
                ["✅", "❌", "🟡"],
                key=f"{numero_serie}_{i}",
                horizontal=True,
                index=None,
                label_visibility="collapsed"
            )

            # Complementos por pergunta
            if i in opcoes_modelos:
                complementos[i] = cols[2].selectbox(
                    "Modelo",
                    [""] + opcoes_modelos[i],
                    key=f"modelo_{numero_serie}_{i}",
                    label_visibility="collapsed"
                )

            elif i in [11, 15]:  # texto livre
                complementos[i] = cols[2].text_input(
                    "",
                    key=f"texto_{numero_serie}_{i}",
                    label_visibility="collapsed"
                )

            elif i in [12, 13, 14]:  # Sim / Não
                complementos[i] = cols[2].selectbox(
                    "",
                    ["", "Sim", "Não"],
                    key=f"sn_{numero_serie}_{i}",
                    label_visibility="collapsed"
                )
            else:
                complementos[i] = ""

        submit = st.form_submit_button("💾 Salvar Checklist")

        if submit:
            if any(v is None for v in resultados.values()):
                st.error("⚠️ Responda todos os itens")
                return

            # 🔒 trava contra duplo envio
            if st.session_state.get("salvando_checklist"):
                st.warning("⏳ Salvamento em andamento, aguarde...")
                return

            st.session_state["salvando_checklist"] = True
            registros = []

            for i in resultados:
                item_final = item_keys[i]
                if complementos.get(i):
                    item_final = f"{item_final} - {complementos[i]}"

                registros.append({
                    "numero_serie": numero_serie,
                    "tipo_producao": tipo_producao,
                    "item": item_final,
                    "status": status_emoji_para_texto(resultados[i]),
                    "usuario": usuario,
                    "data_hora": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })

            try:
                supabase.table("checklists_manga_pnm_detalhes") \
                    .insert(registros) \
                    .execute()

                st.success("✅ Checklist salvo com sucesso")
                st.session_state["salvando_checklist"] = False

            except Exception as e:
                st.session_state["salvando_checklist"] = False
                st.error(f"❌ Erro ao salvar checklist: {e}")

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

    df_apont = carregar_apontamentos()
    hoje = datetime.datetime.now(TZ).date()

    df_hoje = df_apont[df_apont["data_hora"].dt.date == hoje]

    if df_hoje.empty:
        st.info("Nenhum apontamento hoje")
        return

    checklists = supabase.table("checklists_manga_pnm") \
        .select("numero_serie") \
        .eq("tipo_producao", st.session_state.get("tipo_producao", "MANGA")) \
        .execute()

    series_com_checklist = {r["numero_serie"] for r in checklists.data} if checklists.data else set()

    df_pendentes = df_hoje[~df_hoje["numero_serie"].isin(series_com_checklist)]

    if df_pendentes.empty:
        st.success("✅ Todos os apontamentos de hoje já têm checklist salvo")
        return

    numero_serie = st.selectbox(
        "Selecione a série",
        df_pendentes["numero_serie"].unique()
    )

    linha = df_pendentes[df_pendentes["numero_serie"] == numero_serie].iloc[0]

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

    if menu == "Apontamento":
        pagina_apontamento()
    else:
        pagina_checklist()

# ==============================
# EXECUÇÃO
# ==============================
if __name__ == "__main__":
    app()


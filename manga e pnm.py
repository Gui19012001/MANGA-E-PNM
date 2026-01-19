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
# CHECKLIST DE QUALIDADE – MANGA / PNM
# ==============================

def salvar_checklist_manga_pnm_detalhes(
    numero_serie: str,
    tipo_producao: str,
    respostas: dict,
    usuario: str,
    op: str
):
    erros = []

    for item, dados in respostas.items():
        payload = {
            "numero_serie": numero_serie,
            "tipo_producao": tipo_producao,
            "op": op,
            "usuario": usuario,
            "data_hora": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "item": item,
            "status": dados["status"],
            "observacao": dados.get("obs")
        }

        try:
            supabase.table("checklists_manga_pnm_detalhes").insert(payload).execute()
        except Exception as e:
            erros.append(f"{item}: {str(e)}")

    if erros:
        return False, "; ".join(erros)

    return True, None


def checklist_qualidade_manga_pnm(numero_serie, tipo_producao, usuario, op):

    st.markdown(
        f"## ✔️ Checklist – Série: {numero_serie} | OP: {op} | {tipo_producao}"
    )

    perguntas = [
        "Etiqueta do produto – As informações estão corretas / legíveis conforme modelo e gravação do eixo?",
        "Placa do Inmetro está correta / fixada e legível? Número corresponde à viga?",
        "Etiqueta do ABS está conforme? Teste do ABS aprovado?",
        "Rodagem – tipo correto?",
        "Graxeiras e Anéis elásticos estão em perfeito estado?",
        "Sistema de atuação correto? (Spring ou Cuíca)",
        "Catraca do freio correta?",
        "Tampa do cubo correta e sem avarias?",
        "Pintura do eixo conforme padrão?",
        "Cordões de solda conformes?",
        "As caixas estão corretas?",
        "Etiqueta pede suspensor?",
        "Etiqueta pede Suporte da Bolsa?",
        "Etiqueta pede Mão Francesa?"
    ]

    if tipo_producao == "MANGA":
        perguntas.append("Grau do Manga conforme etiqueta?")

    item_keys = {
        1: "ETIQUETA",
        2: "PLACA_INMETRO",
        3: "TESTE_ABS",
        4: "RODAGEM",
        5: "GRAXEIRAS",
        6: "SISTEMA_ATUACAO",
        7: "CATRACA_FREIO",
        8: "TAMPA_CUBO",
        9: "PINTURA_EIXO",
        10: "SOLDA",
        11: "CAIXAS",
        12: "SUSPENSOR",
        13: "SUPORTE_BOLSA",
        14: "MAO_FRANCESA",
        15: "GRAU_MANGA"
    }

    perguntas_com_obs = [4, 6, 7, 11, 15]

    resultados = {}
    observacoes = {}

    st.caption("✅ = Conforme | ❌ = Não Conforme | 🟡 = N/A")

    with st.form(key=f"form_checklist_{numero_serie}"):

        for i, pergunta in enumerate(perguntas, start=1):

            col1, col2, col3 = st.columns([4, 1, 2])

            with col1:
                st.markdown(f"**{i}. {pergunta}**")

            with col2:
                resultados[i] = st.radio(
                    "",
                    ["✅", "❌", "🟡"],
                    horizontal=True,
                    index=None,
                    label_visibility="collapsed",
                    key=f"resp_{numero_serie}_{i}"
                )

            with col3:
                if i in perguntas_com_obs:
                    observacoes[i] = st.text_input(
                        "",
                        placeholder="Informe modelo / tipo / grau...",
                        key=f"obs_{numero_serie}_{i}"
                    )
                else:
                    observacoes[i] = None

        st.divider()
        submit = st.form_submit_button("💾 Salvar Checklist", use_container_width=True)

    if submit:

        faltando = [i for i, r in resultados.items() if r is None]
        faltando_obs = [i for i in perguntas_com_obs if not observacoes[i]]

        if faltando or faltando_obs:
            msg = ""
            if faltando:
                msg += f"⚠️ Responda todos os itens: {[item_keys[i] for i in faltando]}\n"
            if faltando_obs:
                msg += f"⚠️ Preencha observações obrigatórias: {[item_keys[i] for i in faltando_obs]}"
            st.error(msg)
            return

        dados_para_salvar = {
            item_keys[i]: {
                "status": status_emoji_para_texto(resultados[i]),
                "obs": observacoes[i]
            }
            for i in resultados
        }

        sucesso, erro = salvar_checklist_manga_pnm_detalhes(
            numero_serie=numero_serie,
            tipo_producao=tipo_producao,
            respostas=dados_para_salvar,
            usuario=usuario,
            op=op
        )

        if sucesso:
            st.success("✅ Checklist salvo com sucesso")
            st.rerun()
        else:
            st.error(f"❌ Erro ao salvar checklist: {erro}")


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

    resp = supabase.table("checklists_manga_pnm_detalhes") \
        .select("numero_serie") \
        .execute()

    series_com_check = {
        r["numero_serie"] for r in resp.data
    } if resp.data else set()

    df_pendentes = df_hoje[
        ~df_hoje["numero_serie"].isin(series_com_check)
    ]

    if df_pendentes.empty:
        st.success("✅ Todos os apontamentos de hoje já possuem checklist")
        return

    numero_serie = st.selectbox(
        "Selecione a série pendente",
        sorted(df_pendentes["numero_serie"].unique())
    )

    linha = df_pendentes[df_pendentes["numero_serie"] == numero_serie].iloc[0]

    checklist_qualidade_manga_pnm(
        numero_serie=numero_serie,
        tipo_producao=linha["tipo_producao"],
        usuario=st.session_state.get("usuario", "Operador_Logado"),
        op=linha["op"]
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

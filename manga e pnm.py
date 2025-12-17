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
# CHECKLIST DE QUALIDADE (MANGA/PNM)
# ==============================
def checklist_qualidade_manga_pnm(numero_serie, usuario):
    import time

    st.markdown(f"## ✔️ Checklist de Qualidade – Nº de Série: {numero_serie}")

    # Controle de sessão para evitar perda de estado
    if "checklist_bloqueado" not in st.session_state:
        st.session_state.checklist_bloqueado = False

    if "checklist_cache" not in st.session_state:
        st.session_state.checklist_cache = {}

    # ==============================
    # Perguntas padrão Manga/PNM
    # ==============================
    perguntas = [
        "Etiqueta do produto – As informações estão corretas / legíveis?",
        "Placa do Inmetro está correta / fixada e legível?",
        "Etiqueta do ABS está conforme? Número compatível?",
        "Rodagem – tipo correto?",
        "Graxeiras e Anéis elásticos estão em perfeito estado?",
        "Sistema de atuação correto? Springs ou cuícas em perfeitas condições?",
        "Catraca do freio correta? Especifique modelo",
        "Tampa do cubo correta, livre de avarias e pintura nos critérios?",
        "Pintura do eixo livre de oxidação e respingos?",
        "Cordões de solda do eixo conformes?"
    ]

    # Mapeamento de chaves para salvar no Supabase
    item_keys = {
        1: "ETIQUETA",
        2: "PLACA_IMETRO",
        3: "TESTE_ABS",
        4: "RODAGEM_MODELO",
        5: "GRAXEIRAS_E_ANÉIS",
        6: "SISTEMA_ATUACAO",
        7: "CATRACA_FREIO",
        8: "TAMPA_CUBO",
        9: "PINTURA_EIXO",
        10: "SOLDA"
    }

    # Opções de modelo quando necessário
    opcoes_modelos = {
        4: ["Single", "Aço", "Alumínio", "N/A"],
        6: ["Spring", "Cuíca", "N/A"],
        7: ["Automático", "Manual", "N/A"],
        10: ["Conforme", "Respingo", "Falta de cordão", "Porosidade", "Falta de Fusão"]
    }

    resultados = {}
    modelos = {}

    st.write("Clique no botão correspondente a cada item:")
    st.caption("✅ = Conforme | ❌ = Não Conforme | 🟡 = N/A")

    # ==============================
    # FORMULÁRIO CONTROLADO
    # ==============================
    with st.form(key=f"form_checklist_{numero_serie}", clear_on_submit=False):
        for i, pergunta in enumerate(perguntas, start=1):
            cols = st.columns([7, 2, 2])  # pergunta + radio + modelo

            # Pergunta
            cols[0].markdown(f"**{i}. {pergunta}**")

            # Radio de conformidade
            escolha = cols[1].radio(
                "",
                ["✅", "❌", "🟡"],
                key=f"resp_{numero_serie}_{i}",
                horizontal=True,
                index=None,
                label_visibility="collapsed"
            )
            resultados[i] = escolha

            # Seleção de modelos (quando necessário)
            if i in opcoes_modelos:
                modelo = cols[2].selectbox(
                    "Modelo",
                    [""] + opcoes_modelos[i],
                    key=f"modelo_{numero_serie}_{i}",
                    label_visibility="collapsed"
                )
                modelos[i] = modelo
            else:
                modelos[i] = None

        # Botão de envio (salvar)
        submit = st.form_submit_button("💾 Salvar Checklist")

    # ==============================
    # LÓGICA DE SALVAMENTO
    # ==============================
    if submit:
        # Evita salvar múltiplas vezes em caso de atualização
        if st.session_state.checklist_bloqueado:
            st.warning("⏳ Salvamento em andamento... aguarde.")
            return

        st.session_state.checklist_bloqueado = True

        # Validação de campos obrigatórios
        faltando = [i for i, resp in resultados.items() if resp is None]
        modelos_faltando = [
            i for i in opcoes_modelos
            if modelos.get(i) is None or modelos[i] == ""
        ]

        if faltando or modelos_faltando:
            msg = ""
            if faltando:
                msg += f"⚠️ Responda todas as perguntas! Faltam: {[item_keys[i] for i in faltando]}\n"
            if modelos_faltando:
                msg += f"⚠️ Preencha todos os modelos! Faltam: {[item_keys[i] for i in modelos_faltando]}"
            st.error(msg)
            st.session_state.checklist_bloqueado = False
            return

        # Formata dados para salvar no Supabase
        dados_para_salvar = {}
        for i, resp in resultados.items():
            chave_item = item_keys.get(i, f"Item_{i}")
            dados_para_salvar[chave_item] = {
                "status": status_emoji_para_texto(resp),
                "obs": modelos.get(i)
            }

        try:
            salvar_checklist(numero_serie, dados_para_salvar, usuario)
            st.success(f"✅ Checklist do Nº de Série {numero_serie} salvo com sucesso!")

            # Cache local (mantém preenchimento)
            st.session_state.checklist_cache[numero_serie] = dados_para_salvar

            # Pequeno delay para garantir gravação
            time.sleep(0.5)

        except Exception as e:
            st.error(f"❌ Erro ao salvar checklist: {e}")
        finally:
            st.session_state.checklist_bloqueado = False



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

    # Conjunto de checklists já feitos hoje (usando 'tipo_producao')
    feitos = set(
        zip(df_check["numero_serie"], df_check["tipo_producao"])
    ) if not df_check.empty else set()

    # Pendentes: aqueles apontados hoje mas ainda sem checklist
    pendentes = [
        (r.numero_serie, r.tipo_producao)  # aqui também muda para tipo_producao
        for r in df_apont.itertuples()
        if (r.numero_serie, r.tipo_producao) not in feitos
    ]

    if not pendentes:
        st.info("Nenhum checklist pendente hoje")
        return

    numero_serie, tipo = st.selectbox(
        "Selecione para inspeção",
        pendentes,
        format_func=lambda x: f"{x[0]} - {x[1]}"
    )

    # Passando numero_serie e tipo para a função do checklist
    checklist_qualidade_manga_pnm(numero_serie, st.session_state.get("usuario", "Operador_Logado"))



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

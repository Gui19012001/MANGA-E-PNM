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

# Bucket do Storage (crie no Supabase)
BUCKET_FOTOS = "checklist_fotos"

# ==============================
# UTIL
# ==============================
def status_emoji_para_texto(emoji):
    return {"✅": "Conforme", "❌": "Não Conforme", "🟡": "N/A"}.get(emoji)

def _ext_from_mime(mime: str) -> str:
    mime = (mime or "").lower().strip()
    if mime in ("image/jpeg", "image/jpg"):
        return "jpg"
    if mime == "image/png":
        return "png"
    if mime == "image/webp":
        return "webp"
    return "jpg"

def _sanitize(s: str) -> str:
    s = (s or "").strip()
    # evita caracteres ruins no nome do arquivo
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        s = s.replace(ch, "_")
    return s.replace(" ", "_")

def listar_fotos_da_serie(numero_serie: str, tipo_producao: str | None = None):
    q = supabase.table("checklists_manga_pnm_fotos").select("*").eq("numero_serie", numero_serie)
    if tipo_producao:
        q = q.eq("tipo_producao", tipo_producao)
    data = q.order("data_hora", desc=True).limit(20).execute()
    df = pd.DataFrame(data.data)
    if not df.empty and "data_hora" in df.columns:
        df["data_hora"] = pd.to_datetime(df["data_hora"], utc=True).dt.tz_convert(TZ)
    return df

def upload_foto_para_supabase_storage(numero_serie: str, tipo_producao: str, op: str, usuario: str, arquivo, origem: str):
    """
    arquivo: UploadedFile do Streamlit (camera_input ou file_uploader)
    Retorna: (url_publica, storage_path, nome_arquivo)
    """
    if arquivo is None:
        return None, None, None

    try:
        file_bytes = arquivo.getvalue()
        if not file_bytes:
            return None, None, None

        ext = _ext_from_mime(getattr(arquivo, "type", "image/jpeg"))
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        safe_tipo = _sanitize(tipo_producao or "NA")
        safe_usuario = _sanitize(usuario or "NA")
        safe_op = _sanitize(op or "NA")
        safe_serie = _sanitize(numero_serie or "NA")

        # ✅ NOME DO ARQUIVO COMEÇA COM A SÉRIE (PRA "APARECER" NO STORAGE)
        nome_arquivo = f"{safe_serie}__OP{safe_op}__{safe_usuario}__{ts}.{ext}"

        # ✅ PATH ORGANIZADO: TIPO/SERIE/ARQUIVO
        storage_path = f"{safe_tipo}/{safe_serie}/{nome_arquivo}"

        supabase.storage.from_(BUCKET_FOTOS).upload(
            storage_path,
            file_bytes,
            file_options={
                "content-type": getattr(arquivo, "type", "image/jpeg"),
                "upsert": "true"
            }
        )

        # URL pública (funciona se o bucket for PUBLIC)
        url_publica = supabase.storage.from_(BUCKET_FOTOS).get_public_url(storage_path)

        # ✅ grava no banco, mostrando claramente a série
        payload = {
            "numero_serie": numero_serie,
            "tipo_producao": tipo_producao,
            "op": op,
            "usuario": usuario,
            "url": url_publica,
            "origem": origem,
            "data_hora": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "storage_path": storage_path,
            "nome_arquivo": nome_arquivo,
        }

        # se sua tabela não tiver as colunas novas, remova antes de inserir
        try:
            supabase.table("checklists_manga_pnm_fotos").insert(payload).execute()
        except Exception:
            payload.pop("storage_path", None)
            payload.pop("nome_arquivo", None)
            supabase.table("checklists_manga_pnm_fotos").insert(payload).execute()

        return url_publica, storage_path, nome_arquivo

    except Exception as e:
        st.error(f"❌ Erro ao enviar foto: {e}")
        return None, None, None

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
# CHECKLIST DE QUALIDADE
# ==============================
def checklist_qualidade_manga_pnm(numero_serie, tipo_producao, usuario, op):
    st.markdown(f"## ✔️ Checklist – Série: {numero_serie} | OP: {op} | {tipo_producao}")

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
            cols[0].markdown(f"**{i}. {pergunta}**")

            resultados[i] = cols[1].radio(
                "",
                ["✅", "❌", "🟡"],
                key=f"{numero_serie}_{i}",
                horizontal=True,
                index=None,
                label_visibility="collapsed"
            )

            if i in opcoes_modelos:
                complementos[i] = cols[2].selectbox(
                    "Modelo",
                    [""] + opcoes_modelos[i],
                    key=f"modelo_{numero_serie}_{i}",
                    label_visibility="collapsed"
                )
            elif i in [11, 15]:
                complementos[i] = cols[2].text_input(
                    "",
                    key=f"texto_{numero_serie}_{i}",
                    label_visibility="collapsed"
                )
            elif i in [12, 13, 14]:
                complementos[i] = cols[2].selectbox(
                    "",
                    ["", "Sim", "Não"],
                    key=f"sn_{numero_serie}_{i}",
                    label_visibility="collapsed"
                )
            else:
                complementos[i] = ""

        st.divider()
        st.markdown("### 📷 Fotos (com número de série no nome do arquivo)")

        # ✅ IMPORTANTE: não dá pra forçar traseira no st.camera_input.
        st.info(
            "⚠️ No Streamlit não dá pra forçar câmera traseira no `camera_input`. "
            "Se abrir na frontal, use o botão de trocar câmera do próprio navegador/app de câmera "
            "ou tire a foto no celular (traseira) e anexe abaixo."
        )

        # opção 1: camera_input (pode abrir frontal dependendo do dispositivo)
        foto_camera = st.camera_input("Tirar foto (pode abrir frontal)", key=f"foto_camera_{numero_serie}")

        # opção 2: upload (recomendado p/ traseira)
        fotos_upload = st.file_uploader(
            "📎 Anexar foto(s) (recomendado para usar câmera traseira do celular)",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key=f"fotos_upload_{numero_serie}"
        )

        submit = st.form_submit_button("💾 Salvar Checklist")

        if submit:
            if any(v is None for v in resultados.values()):
                st.error("⚠️ Responda todos os itens")
                return

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

            supabase.table("checklists_manga_pnm_detalhes").insert(registros).execute()

            # Upload das fotos
            urls = []

            if foto_camera is not None:
                url, _, _ = upload_foto_para_supabase_storage(
                    numero_serie=numero_serie,
                    tipo_producao=tipo_producao,
                    op=op,
                    usuario=usuario,
                    arquivo=foto_camera,
                    origem="camera"
                )
                if url:
                    urls.append(url)

            if fotos_upload:
                for arq in fotos_upload:
                    url, _, _ = upload_foto_para_supabase_storage(
                        numero_serie=numero_serie,
                        tipo_producao=tipo_producao,
                        op=op,
                        usuario=usuario,
                        arquivo=arq,
                        origem="upload"
                    )
                    if url:
                        urls.append(url)

            if urls:
                st.success(f"✅ Checklist salvo + {len(urls)} foto(s) enviada(s)")
            else:
                st.success("✅ Checklist salvo (sem fotos)")

            st.session_state["checklist_salvo"] = True
            st.rerun()

    # ✅ FORA DO FORM: mostra fotos já salvas da série
    st.divider()
    st.markdown(f"### 🖼️ Fotos já salvas — Série **{numero_serie}**")
    df_fotos = listar_fotos_da_serie(numero_serie, tipo_producao=tipo_producao)
    if df_fotos.empty:
        st.caption("Nenhuma foto salva ainda para esta série.")
    else:
        # mostra tabela com série + url
        cols_show = [c for c in ["data_hora", "numero_serie", "tipo_producao", "op", "usuario", "origem", "nome_arquivo", "url"] if c in df_fotos.columns]
        st.dataframe(df_fotos[cols_show], use_container_width=True)

        # galeria simples
        for _, r in df_fotos.head(6).iterrows():
            st.markdown(f"**Série:** {r.get('numero_serie','-')} | **OP:** {r.get('op','-')} | **Usuário:** {r.get('usuario','-')}")
            st.image(r.get("url"), use_container_width=True)

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

    hoje_str = hoje.strftime("%Y-%m-%d")

    checklists = supabase.table("checklists_manga_pnm_detalhes") \
        .select("numero_serie, tipo_producao") \
        .gte("data_hora", f"{hoje_str}T00:00:00") \
        .lte("data_hora", f"{hoje_str}T23:59:59") \
        .execute()

    if checklists.data:
        df_check = pd.DataFrame(checklists.data)
        df_pendentes = df_hoje.merge(
            df_check,
            on=["numero_serie", "tipo_producao"],
            how="left",
            indicator=True
        ).query('_merge == "left_only"').drop(columns="_merge")
    else:
        df_pendentes = df_hoje.copy()

    if df_pendentes.empty:
        st.success("✅ Todos os apontamentos de hoje já têm checklist salvo")
        return

    numero_serie = st.selectbox(
        "Selecione a série",
        df_pendentes["numero_serie"].unique(),
        key="serie_selecionada"
    )

    df_sel = df_pendentes[df_pendentes["numero_serie"] == numero_serie]
    if df_sel.empty:
        st.warning("Série já inspecionada")
        return

    linha = df_sel.iloc[0]

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

if __name__ == "__main__":
    app()


import os
import re
import json
import math
import datetime
from pathlib import Path
from html import escape
from urllib.parse import quote_plus
import pandas as pd
import pytz
import requests
import streamlit as st
import streamlit.components.v1 as components
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from supabase import create_client

# ==============================
# CONFIG
# ==============================
APP_NAME = "MANGA E PNM"

env_path = Path(__file__).parent / "teste.env"
load_dotenv(env_path)


def _cfg(key: str, default=None):
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)


SUPABASE_URL = _cfg("SUPABASE_URL")
SUPABASE_KEY = _cfg("SUPABASE_KEY")

TOTVS_API_BASE = str(_cfg(
    "TOTVS_API_BASE",
    "http://200.201.240.47:8383/rest01/PY_APONTAMEN"
)).rstrip("/")

TOTVS_TIMEOUT = int(_cfg("TOTVS_TIMEOUT", "100"))
TOTVS_USERNAME = str(_cfg("TOTVS_USERNAME", "")).strip()
TOTVS_PASSWORD = str(_cfg("TOTVS_PASSWORD", "")).strip()
TOTVS_TENANT_ID = str(_cfg("TOTVS_TENANT_ID", "")).strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL / SUPABASE_KEY não encontrados no teste.env ou st.secrets")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TZ = pytz.timezone("America/Sao_Paulo")

st.set_page_config(
    page_title=APP_NAME,
    layout="wide"
)

BUCKET_FOTOS = "checklist_fotos"
USAR_SIGNED_URL = False
SIGNED_URL_EXPIRA_SEG = 60 * 60

# ==============================
# LOGIN APP
# ==============================
USUARIOS_FIXOS = [
    "LUCAS.SILVA",
    "VICTOR.BARBOSA",
    "FABIO.VIEIRA",
    "MARCOS.MIRANDA",
]


def _usuario_env_key(usuario: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", usuario.upper()).strip("_")


def _carregar_usuarios_app():
    usuarios = {}
    for usuario in USUARIOS_FIXOS:
        chave_env = f"APP_PASS_{_usuario_env_key(usuario)}"
        senha = str(_cfg(chave_env, "")).strip()
        usuarios[usuario.upper()] = senha
    return usuarios


USUARIOS_APP = _carregar_usuarios_app()


def inicializar_estado():
    defaults = {
        "autenticado": False,
        "usuario": None,
        "tipo_producao": "MANGA",
        "numero_serie": "",
        "op": "",
        "erro": None,
        "sucesso": None,
        "aviso": None,
        "input_leitor": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def validar_login_app(usuario: str, senha: str):
    usuario = (usuario or "").strip().upper()
    senha = str(senha or "").strip()

    if not usuario or not senha:
        return False, "Informe usuário e senha."

    if usuario not in USUARIOS_APP:
        return False, "Usuário inválido."

    senha_cadastrada = USUARIOS_APP.get(usuario, "")
    if not senha_cadastrada:
        return False, f"Senha do usuário {usuario} não configurada no env."

    if senha != senha_cadastrada:
        return False, "Senha inválida."

    return True, None


def tela_login():
    st.markdown(f"## 🔐 {APP_NAME}")
    st.caption("Acesso restrito")

    with st.form("form_login_app", clear_on_submit=False):
        usuario = st.text_input("Usuário", placeholder="Ex.: LUCAS.SILVA").strip().upper()
        senha = st.text_input("Senha", type="password")
        entrar = st.form_submit_button("Entrar", use_container_width=True)

    if entrar:
        ok, msg = validar_login_app(usuario, senha)
        if ok:
            st.session_state["autenticado"] = True
            st.session_state["usuario"] = usuario
            st.rerun()
        st.error(msg)

    st.stop()


def exigir_login():
    if not st.session_state.get("autenticado", False):
        tela_login()


def logout_app():
    for chave in [
        "autenticado", "usuario", "numero_serie", "op",
        "erro", "sucesso", "aviso", "input_leitor"
    ]:
        if chave in st.session_state:
            del st.session_state[chave]
    inicializar_estado()


# ==============================
# UTIL GERAL
# ==============================
def normalizar_texto(valor) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


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


def _sanitize(s) -> str:
    if s is None:
        s = ""
    elif isinstance(s, float) and math.isnan(s):
        s = ""
    s = str(s).strip()
    for ch in ['\\', '/', ':', '*', '?', '"', '<', '>', '|']:
        s = s.replace(ch, "_")
    return s.replace(" ", "_")


def _normaliza_codigo(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _agora_utc_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _converter_datas_df(df, colunas):
    if df.empty:
        return df
    for col in colunas:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce").dt.tz_convert(TZ)
    return df


def _fmt_data(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "-"
    try:
        if pd.isna(v):
            return "-"
    except Exception:
        pass
    if hasattr(v, "strftime"):
        return v.strftime("%d/%m/%Y %H:%M:%S")
    return str(v)


def _mostrar_feedback_fila():
    feedback = st.session_state.pop("fila_feedback", None)
    if feedback:
        tipo, msg = feedback
        if tipo == "success":
            st.success(msg)
        elif tipo == "warning":
            st.warning(msg)
        else:
            st.error(msg)


def headers_totvs():
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if TOTVS_TENANT_ID:
        headers["tenantId"] = TOTVS_TENANT_ID
    return headers


def headers_totvs_get():
    headers = {
        "Accept": "application/json",
    }
    if TOTVS_TENANT_ID:
        headers["tenantId"] = TOTVS_TENANT_ID
    return headers


def _totvs_auth():
    return HTTPBasicAuth(TOTVS_USERNAME, TOTVS_PASSWORD)


def _texto_body_http(body):
    if isinstance(body, (dict, list)):
        try:
            return json.dumps(body, ensure_ascii=False)
        except Exception:
            return str(body)
    return str(body or "").strip()


# ==============================
# CONSULTA TOTVS - GET ID
# ==============================
def corpo_resposta_http(resp):
    try:
        return resp.json()
    except Exception:
        txt = (resp.text or "").strip()
        return txt if txt else "Sem conteúdo"


def consultar_numero_serie_totvs(numero_serie: str):
    numero_serie = _normaliza_codigo(numero_serie)

    if not numero_serie:
        return {
            "ok": False,
            "existe": False,
            "mensagem": "Número de série inválido para consulta.",
            "body": None,
            "url": None,
            "status_code": None,
        }

    if not TOTVS_USERNAME or not TOTVS_PASSWORD:
        return {
            "ok": False,
            "existe": False,
            "mensagem": "TOTVS_USERNAME ou TOTVS_PASSWORD não configurados.",
            "body": None,
            "url": None,
            "status_code": None,
        }

    urls = [
        f"{TOTVS_API_BASE}/get_id?{numero_serie}",
        f"{TOTVS_API_BASE}/get_id?{quote_plus(numero_serie)}",
        f"{TOTVS_API_BASE}/get_id?id={quote_plus(numero_serie)}",
    ]

    ultimo_resultado = None

    for url in urls:
        try:
            response = requests.get(
                url,
                headers=headers_totvs_get(),
                auth=_totvs_auth(),
                timeout=TOTVS_TIMEOUT
            )

            body = corpo_resposta_http(response)
            body_txt = _texto_body_http(body).strip()
            body_upper = body_txt.upper()

            if response.status_code in (200, 204, 404):
                if (
                    body_txt in ("", "[]", "{}", "null", "None")
                    or "NAO ENCONTR" in body_upper
                    or "NÃO ENCONTR" in body_upper
                    or "NOT FOUND" in body_upper
                ):
                    return {
                        "ok": True,
                        "existe": False,
                        "mensagem": f"Série {numero_serie} não encontrada no TOTVS.",
                        "body": body,
                        "url": url,
                        "status_code": response.status_code,
                    }

                return {
                    "ok": True,
                    "existe": True,
                    "mensagem": f"Série {numero_serie} já encontrada no TOTVS.",
                    "body": body,
                    "url": url,
                    "status_code": response.status_code,
                }

            if response.status_code == 500:
                if (
                    body_txt in ("", "[]", "{}", "null", "None")
                    or "NAO ENCONTR" in body_upper
                    or "NÃO ENCONTR" in body_upper
                    or "NOT FOUND" in body_upper
                ):
                    return {
                        "ok": True,
                        "existe": False,
                        "mensagem": f"Série {numero_serie} não encontrada no TOTVS.",
                        "body": body,
                        "url": url,
                        "status_code": response.status_code,
                    }

                if numero_serie in body_txt:
                    return {
                        "ok": True,
                        "existe": True,
                        "mensagem": f"Série {numero_serie} já encontrada no TOTVS.",
                        "body": body,
                        "url": url,
                        "status_code": response.status_code,
                    }

                ultimo_resultado = {
                    "ok": False,
                    "existe": False,
                    "mensagem": "Falha na verificação do número de série no TOTVS.",
                    "body": body,
                    "url": url,
                    "status_code": response.status_code,
                }
                continue

            ultimo_resultado = {
                "ok": False,
                "existe": False,
                "mensagem": f"Falha na verificação do número de série no TOTVS. HTTP {response.status_code}.",
                "body": body,
                "url": url,
                "status_code": response.status_code,
            }

        except Exception as e:
            ultimo_resultado = {
                "ok": False,
                "existe": False,
                "mensagem": f"Falha ao verificar série no TOTVS: {e}",
                "body": None,
                "url": url,
                "status_code": None,
            }

    return ultimo_resultado or {
        "ok": False,
        "existe": False,
        "mensagem": "Não foi possível verificar a série no TOTVS.",
        "body": None,
        "url": None,
        "status_code": None,
    }


# ==============================
# TRATAMENTO RETORNO TOTVS
# ==============================
def normalizar_quebras(msg: str) -> str:
    return str(msg).replace("\r\n", "\n").replace("\r", "\n")


def remover_cabecalho_ajuda(msg: str) -> str:
    msg = normalizar_quebras(msg)
    linhas = msg.split("\n")

    if linhas and linhas[0].strip().upper().startswith("AJUDA:"):
        linhas = linhas[1:]

    return "\n".join(linhas).strip()


def limpar_mensagem_totvs(msg) -> str:
    if msg is None:
        return "Sem conteúdo"

    msg = remover_cabecalho_ajuda(str(msg))
    linhas = [re.sub(r"\s+", " ", linha).strip() for linha in msg.split("\n") if linha.strip()]
    return " ".join(linhas).strip()


def converter_saldo_para_float(valor):
    if valor is None:
        return None

    txt = str(valor).strip()
    if not txt:
        return None

    txt = txt.replace(".", "").replace(",", ".") if txt.count(",") == 1 and txt.count(".") > 1 else txt.replace(",", ".")
    try:
        return float(txt)
    except Exception:
        return None


def _fmt_qtd_br(valor):
    num = converter_saldo_para_float(valor)
    if num is None:
        return str(valor).strip()

    txt = f"{num:,.2f}"
    txt = txt.replace(",", "X").replace(".", ",").replace("X", ".")
    txt = txt.replace("-", "- ")
    return txt


def _fmt_status_item(valor):
    txt = re.sub(r"\s+", " ", str(valor or "")).strip()
    txt_upper = txt.upper()

    mapa = {
        "SEM SALDO EM ESTOQUE": "Falta de saldo",
        "SALDO INDISPONIVEL": "Saldo Indisponivel",
        "SALDO INDISPONÍVEL": "Saldo Indisponivel",
    }

    if txt_upper in mapa:
        return mapa[txt_upper]

    if not txt:
        return "-"

    return txt[:1].upper() + txt[1:]


def extrair_itens_erro_estoque(msg):
    if msg is None:
        return []

    texto = remover_cabecalho_ajuda(str(msg))
    texto = re.sub(r"\s+", " ", texto).strip()

    padrao_item = re.compile(
        r'(?P<produto>[A-Z0-9]{2,}(?:\.[A-Z0-9]{1,})+)'
        r'\s+'
        r'(?P<armazem>[A-Z0-9]{1,10})'
        r'\s+'
        r'(?P<saldo>-?\d+(?:[.,]\d+)?)'
        r'\s+'
        r'(?P<ocorrencia>.*?)(?=(?:[A-Z0-9]{2,}(?:\.[A-Z0-9]{1,})+\s+[A-Z0-9]{1,10}\s+-?\d)|$)',
        flags=re.IGNORECASE
    )

    itens = []
    for m in padrao_item.finditer(texto):
        produto = m.group("produto").strip()
        armazem = m.group("armazem").strip()
        saldo = m.group("saldo").strip()
        ocorrencia = re.sub(r"\s+", " ", m.group("ocorrencia")).strip()

        if produto.upper() == "PRODUTO":
            continue

        itens.append({
            "produto": produto,
            "armazem": armazem,
            "saldo": saldo,
            "saldo_num": converter_saldo_para_float(saldo),
            "ocorrencia": ocorrencia,
            "motivo": ocorrencia,
        })

    return itens


def formatar_mensagem_tela_totvs(msg):
    if msg is None:
        return "Sem conteúdo", []

    texto = remover_cabecalho_ajuda(str(msg))
    texto_unico = re.sub(r"\s+", " ", texto).strip()
    texto_upper = texto_unico.upper()

    itens = extrair_itens_erro_estoque(texto)

    if (
        "NÃO EXISTE QUANTIDADE SUFICIENTE EM ESTOQUE" in texto_upper
        or "NAO EXISTE QUANTIDADE SUFICIENTE EM ESTOQUE" in texto_upper
    ):
        linhas = [
            "Não existe quantidade suficiente em estoque para atender esta requisição. Itens Sem Sld / Bloqs. / Empenhos Pendentes Produto Armazem",
            "",
            "CÓDIGO | ARMAZEM | QUANTIDADE | STATUS"
        ]

        if itens:
            for item in itens:
                codigo = item.get("produto", "").strip()
                armazem = item.get("armazem", "").strip()
                quantidade = _fmt_qtd_br(item.get("saldo"))
                status = _fmt_status_item(item.get("ocorrencia"))
                linhas.append(f"{codigo} | {armazem} | {quantidade} | {status}")
        else:
            linhas.append("Sem itens identificados.")

        return "\n".join(linhas).strip(), itens

    linhas = [
        re.sub(r"\s+", " ", linha).strip()
        for linha in texto.split("\n")
        if linha.strip()
    ]
    return "\n".join(linhas).strip(), itens


def interpretar_retorno_totvs(response):
    corpo = corpo_resposta_http(response)

    if isinstance(corpo, dict):
        body_raw = json.dumps(corpo, ensure_ascii=False, indent=2)

        note = corpo.get("note")
        message = corpo.get("message")
        error = corpo.get("error")
        error_id = corpo.get("errorId")

        mensagem_base = note or message or error or body_raw

        mensagem_amigavel = limpar_mensagem_totvs(mensagem_base)
        mensagem_tela, itens_estoque = formatar_mensagem_tela_totvs(mensagem_base)

        texto_upper = mensagem_amigavel.upper()

        erro_negocio = bool(error_id or error)
        if "OP NÃO EXISTE" in texto_upper or "OP NAO EXISTE" in texto_upper:
            erro_negocio = True

        sucesso = (200 <= response.status_code < 300) and not erro_negocio

        return {
            "sucesso": sucesso,
            "status_code": response.status_code,
            "body_raw": body_raw,
            "body_json": corpo,
            "mensagem_amigavel": mensagem_amigavel,
            "mensagem_tela": mensagem_tela,
            "itens_estoque": itens_estoque,
            "headers": dict(response.headers),
        }

    body_raw = str(corpo)
    mensagem_amigavel = limpar_mensagem_totvs(body_raw)
    mensagem_tela, itens_estoque = formatar_mensagem_tela_totvs(body_raw)
    texto_upper = mensagem_amigavel.upper()

    erro_negocio = "OP NÃO EXISTE" in texto_upper or "OP NAO EXISTE" in texto_upper
    sucesso = (200 <= response.status_code < 300) and not erro_negocio

    return {
        "sucesso": sucesso,
        "status_code": response.status_code,
        "body_raw": body_raw,
        "body_json": None,
        "mensagem_amigavel": mensagem_amigavel,
        "mensagem_tela": mensagem_tela,
        "itens_estoque": itens_estoque,
        "headers": dict(response.headers),
    }


# ==============================
# APONTAMENTO TOTVS
# ==============================
def apontar_op_totvs(op: str, quant: str, lotectl: str):
    op = normalizar_texto(op)
    quant = normalizar_texto(quant)
    lotectl = normalizar_texto(lotectl)

    if not TOTVS_USERNAME or not TOTVS_PASSWORD:
        return False, {
            "erro": "TOTVS_USERNAME ou TOTVS_PASSWORD não configurados no teste.env."
        }

    if not op:
        return False, {"erro": "Informe a OP."}

    if not quant:
        return False, {"erro": "Informe a quantidade."}

    try:
        int(float(quant))
    except Exception:
        return False, {"erro": f"Quantidade inválida: {quant}"}

    payload = {
        "quant": 1,
        "lotectl": lotectl if lotectl else " ",
        "op": op
    }

    url = f"{TOTVS_API_BASE}/NEW"

    try:
        response = requests.post(
            url,
            json=payload,
            headers=headers_totvs(),
            auth=_totvs_auth(),
            timeout=TOTVS_TIMEOUT
        )

        interpretado = interpretar_retorno_totvs(response)

        retorno = {
            "url": url,
            "payload": payload,
            "status_code": interpretado["status_code"],
            "headers": interpretado["headers"],
            "body": interpretado["body_raw"],
            "body_json": interpretado["body_json"],
            "mensagem_amigavel": interpretado["mensagem_amigavel"],
            "mensagem_tela": interpretado["mensagem_tela"],
            "itens_estoque": interpretado["itens_estoque"],
        }

        return interpretado["sucesso"], retorno

    except Exception as e:
        return False, {
            "url": url,
            "payload": payload,
            "erro": f"Falha ao chamar API TOTVS: {e}"
        }


# ==============================
# STORAGE / FOTOS
# ==============================
def listar_fotos_da_serie(numero_serie, tipo_producao=None):
    numero_serie = _normaliza_codigo(numero_serie)
    q = supabase.table("checklists_manga_pnm_fotos").select("*").eq("numero_serie", numero_serie)
    if tipo_producao:
        q = q.eq("tipo_producao", tipo_producao)
    data = q.order("data_hora", desc=True).limit(50).execute()
    df = pd.DataFrame(data.data)
    df = _converter_datas_df(df, ["data_hora"])
    return df


def listar_arquivos_no_storage(prefixo: str):
    try:
        res = supabase.storage.from_(BUCKET_FOTOS).list(path=prefixo)
        return res or []
    except Exception as e:
        st.error(f"❌ Erro ao listar Storage (prefixo={prefixo}): {e}")
        return []


def upload_foto_para_supabase_storage(numero_serie, tipo_producao, op, usuario, arquivo, origem):
    if arquivo is None:
        st.error("❌ Nenhum arquivo recebido pelo uploader.")
        return None, None, None

    file_bytes = arquivo.getvalue()
    if not file_bytes:
        st.error("❌ Arquivo veio vazio (0 bytes).")
        return None, None, None

    numero_serie = _normaliza_codigo(numero_serie)
    op = _normaliza_codigo(op)
    tipo_producao = _normaliza_codigo(tipo_producao)
    usuario = _normaliza_codigo(usuario) or "Operador_Logado"

    ext = _ext_from_mime(getattr(arquivo, "type", "image/jpeg"))
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    safe_tipo = _sanitize(tipo_producao or "NA")
    safe_serie = _sanitize(numero_serie or "NA")
    safe_op = _sanitize(op or "NA")
    safe_user = _sanitize(usuario or "NA")

    nome_arquivo = f"{safe_serie}__OP{safe_op}__{safe_user}__{origem}__{ts}.{ext}"
    storage_path = f"{safe_tipo}/{safe_serie}/{nome_arquivo}"

    try:
        resp = supabase.storage.from_(BUCKET_FOTOS).upload(
            path=storage_path,
            file=file_bytes,
            file_options={
                "content-type": getattr(arquivo, "type", "image/jpeg"),
                "upsert": True,
            },
        )
    except Exception as e:
        st.error(f"❌ EXCEÇÃO no upload do Storage:\n{e}")
        return None, None, None

    if isinstance(resp, dict) and resp.get("error"):
        st.error(f"❌ ERRO do Storage (resp.error): {resp['error']}")
        st.code(str(resp))
        return None, None, None

    url = None
    if USAR_SIGNED_URL:
        try:
            signed = supabase.storage.from_(BUCKET_FOTOS).create_signed_url(
                storage_path,
                SIGNED_URL_EXPIRA_SEG
            )
            url = signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
        except Exception as e:
            st.warning(f"⚠️ Não consegui gerar signed URL: {e}")
    else:
        try:
            url = supabase.storage.from_(BUCKET_FOTOS).get_public_url(storage_path)
        except Exception as e:
            st.warning(f"⚠️ Não consegui gerar public URL: {e}")

    try:
        supabase.table("checklists_manga_pnm_fotos").insert({
            "numero_serie": numero_serie,
            "tipo_producao": tipo_producao,
            "op": op,
            "usuario": usuario,
            "url": url or "",
            "origem": origem,
            "data_hora": _agora_utc_iso(),
            "storage_path": storage_path,
            "nome_arquivo": nome_arquivo
        }).execute()
    except Exception as e:
        st.error(f"❌ EXCEÇÃO ao inserir registro da foto: {e}")

    return url, storage_path, nome_arquivo


# ==============================
# OCORRÊNCIAS TOTVS
# ==============================
def salvar_ocorrencias_apontamento_totvs(numero_serie, op, tipo_producao, usuario, itens_estoque, resposta_api):
    numero_serie = _normaliza_codigo(numero_serie)
    op = _normaliza_codigo(op)
    tipo_producao = _normaliza_codigo(tipo_producao)
    usuario = _normaliza_codigo(usuario) or st.session_state.get("usuario") or "Operador_Logado"

    if not itens_estoque:
        return False, "Nenhum item de ocorrência para salvar."

    registros = []
    for item in itens_estoque:
        codigo = _normaliza_codigo(item.get("produto"))
        quantidade = item.get("saldo_num")

        if quantidade is None:
            quantidade = converter_saldo_para_float(item.get("saldo"))

        registros.append({
            "numero_serie": numero_serie,
            "op": op,
            "codigo": codigo,
            "quantidade": quantidade,
            "tipo_producao": tipo_producao,
            "usuario": usuario
        })

    try:
        supabase.table("ocorrencias_apontamento_totvs").insert(registros).execute()
        return True, f"{len(registros)} ocorrência(s) salva(s) com sucesso."
    except Exception as e:
        return False, f"Falha ao salvar ocorrências no Supabase: {e}"


# ==============================
# FILA TOTVS
# ==============================
def criar_item_fila_totvs(apontamento_id, numero_serie, op, tipo_producao, usuario, data_hora):
    numero_serie = _normaliza_codigo(numero_serie)
    op = _normaliza_codigo(op)
    tipo_producao = _normaliza_codigo(tipo_producao)
    usuario = _normaliza_codigo(usuario) or "Operador_Logado"

    if apontamento_id is None or str(apontamento_id).strip() == "":
        return False, "ID do apontamento não encontrado."

    try:
        apontamento_id = int(apontamento_id)
    except Exception:
        return False, f"ID do apontamento inválido para a fila: {apontamento_id}"

    try:
        existe = supabase.table("fila_apontamento_totvs") \
            .select("id,status") \
            .eq("apontamento_id", apontamento_id) \
            .limit(1) \
            .execute()

        if existe.data:
            return True, None

        supabase.table("fila_apontamento_totvs").insert({
            "apontamento_id": apontamento_id,
            "numero_serie": numero_serie,
            "op": op,
            "tipo_producao": tipo_producao,
            "usuario": usuario,
            "data_hora": data_hora,
            "status": "pendente",
            "tentativas": 0,
            "ultimo_erro": None,
            "resposta_api": None
        }).execute()

        return True, None

    except Exception as e:
        return False, str(e)


def carregar_fila_totvs(status=None, limit=200):
    try:
        q = supabase.table("fila_apontamento_totvs").select("*").order("criado_em", desc=True).limit(limit)
        if status:
            q = q.eq("status", status)
        data = q.execute()
        df = pd.DataFrame(data.data)
        df = _converter_datas_df(df, ["data_hora", "criado_em", "enviado_em"])
        return df
    except Exception as e:
        st.error(f"❌ Erro ao carregar fila TOTVS: {e}")
        return pd.DataFrame()


def buscar_item_fila(fila_id):
    try:
        res = supabase.table("fila_apontamento_totvs") \
            .select("*") \
            .eq("id", int(fila_id)) \
            .limit(1) \
            .execute()
        if res.data:
            return res.data[0]
        return None
    except Exception:
        return None


def atualizar_item_fila(fila_id, payload):
    supabase.table("fila_apontamento_totvs").update(payload).eq("id", int(fila_id)).execute()


def _parse_resposta_api(valor):
    if not valor:
        return None
    if isinstance(valor, dict):
        return valor
    try:
        return json.loads(valor)
    except Exception:
        return None


def executar_apontamento_totvs(fila_id):
    item = buscar_item_fila(fila_id)
    if not item:
        return False, "Item da fila não encontrado."

    op = _normaliza_codigo(item.get("op"))
    numero_serie = _normaliza_codigo(item.get("numero_serie"))
    tipo_producao = _normaliza_codigo(item.get("tipo_producao"))
    usuario = _normaliza_codigo(item.get("usuario")) or st.session_state.get("usuario") or "Operador_Logado"
    tentativas = int(item.get("tentativas") or 0) + 1

    if not op:
        msg = "OP vazia no item da fila."
        atualizar_item_fila(fila_id, {
            "status": "erro",
            "tentativas": tentativas,
            "ultimo_erro": msg,
            "resposta_api": msg
        })
        return False, msg

    verificacao = consultar_numero_serie_totvs(numero_serie)
    if not verificacao["ok"]:
        msg = verificacao["mensagem"]
        atualizar_item_fila(fila_id, {
            "status": "erro",
            "tentativas": tentativas,
            "ultimo_erro": msg,
            "resposta_api": json.dumps(verificacao, ensure_ascii=False, indent=2)
        })
        return False, msg

    if verificacao["existe"]:
        msg = f"Série {numero_serie} já está apontada no TOTVS."
        atualizar_item_fila(fila_id, {
            "status": "erro",
            "tentativas": tentativas,
            "ultimo_erro": msg,
            "resposta_api": json.dumps(verificacao, ensure_ascii=False, indent=2)
        })
        return False, msg

    sucesso, retorno = apontar_op_totvs(op=op, quant="1", lotectl=numero_serie)

    if "erro" in retorno:
        msg = retorno["erro"]
        atualizar_item_fila(fila_id, {
            "status": "erro",
            "tentativas": tentativas,
            "ultimo_erro": msg,
            "resposta_api": json.dumps(retorno, ensure_ascii=False, indent=2)
        })
        return False, msg

    resposta_completa = {
        "url": retorno.get("url"),
        "payload": retorno.get("payload"),
        "status_code": retorno.get("status_code"),
        "headers": retorno.get("headers"),
        "body": retorno.get("body"),
        "body_json": retorno.get("body_json"),
        "mensagem_amigavel": retorno.get("mensagem_amigavel"),
        "mensagem_tela": retorno.get("mensagem_tela"),
        "itens_estoque": retorno.get("itens_estoque", [])
    }

    resposta_json = json.dumps(resposta_completa, ensure_ascii=False, indent=2)

    itens_estoque = retorno.get("itens_estoque", [])
    if itens_estoque:
        salvar_ocorrencias_apontamento_totvs(
            numero_serie=numero_serie,
            op=op,
            tipo_producao=tipo_producao,
            usuario=usuario,
            itens_estoque=itens_estoque,
            resposta_api=resposta_json
        )

    if sucesso:
        atualizar_item_fila(fila_id, {
            "status": "enviado",
            "tentativas": tentativas,
            "ultimo_erro": None,
            "resposta_api": resposta_json,
            "enviado_em": _agora_utc_iso(),
            "usuario": usuario
        })
        return True, retorno.get("mensagem_amigavel") or f"✅ Série {numero_serie} apontada no TOTVS com sucesso."

    msg = retorno.get("mensagem_amigavel") or f"HTTP {retorno.get('status_code')}"
    atualizar_item_fila(fila_id, {
        "status": "erro",
        "tentativas": tentativas,
        "ultimo_erro": msg,
        "resposta_api": resposta_json,
        "usuario": usuario
    })
    return False, msg


# ==============================
# APONTAMENTOS SUPABASE
# ==============================
def salvar_apontamento(numero_serie, op, tipo_producao, usuario):
    numero_serie = _normaliza_codigo(numero_serie)
    op = _normaliza_codigo(op)
    tipo_producao = _normaliza_codigo(tipo_producao)
    usuario = _normaliza_codigo(usuario) or st.session_state.get("usuario") or "Operador_Logado"

    check = supabase.table("apontamentos_manga_pnm") \
        .select("id") \
        .eq("numero_serie", numero_serie) \
        .limit(1) \
        .execute()

    if check.data:
        return False, f"Série {numero_serie} já apontada no app.", None

    verificacao = consultar_numero_serie_totvs(numero_serie)
    if not verificacao["ok"]:
        detalhe = f" URL: {verificacao.get('url')}" if verificacao.get("url") else ""
        return False, verificacao["mensagem"] + detalhe, None

    if verificacao["existe"]:
        return False, f"Série {numero_serie} já está apontada no TOTVS.", None

    agora = _agora_utc_iso()

    try:
        ins = supabase.table("apontamentos_manga_pnm").insert({
            "numero_serie": numero_serie,
            "op": op,
            "tipo_producao": tipo_producao,
            "usuario": usuario,
            "data_hora": agora
        }).execute()

        apontamento_id = None

        if getattr(ins, "data", None):
            if len(ins.data) > 0:
                apontamento_id = ins.data[0].get("id")

        if apontamento_id is None:
            busca = supabase.table("apontamentos_manga_pnm") \
                .select("id") \
                .eq("numero_serie", numero_serie) \
                .order("data_hora", desc=True) \
                .limit(1) \
                .execute()

            if busca.data:
                apontamento_id = busca.data[0].get("id")

        if apontamento_id is None:
            st.cache_data.clear()
            return True, None, "⚠️ Apontamento salvo, mas não consegui localizar o ID para criar a fila TOTVS."

        try:
            apontamento_id = int(apontamento_id)
        except Exception:
            st.cache_data.clear()
            return True, None, f"⚠️ Apontamento salvo, mas o ID retornado é inválido para a fila TOTVS: {apontamento_id}"

        ok_fila, erro_fila = criar_item_fila_totvs(
            apontamento_id=apontamento_id,
            numero_serie=numero_serie,
            op=op,
            tipo_producao=tipo_producao,
            usuario=usuario,
            data_hora=agora
        )

        st.cache_data.clear()

        if not ok_fila:
            return True, None, f"⚠️ Apontamento salvo, mas falhou ao criar item na fila TOTVS: {erro_fila}"

        return True, None, None

    except Exception as e:
        return False, str(e), None


def carregar_apontamentos(limit=10):
    data = supabase.table("apontamentos_manga_pnm") \
        .select("*") \
        .order("data_hora", desc=True) \
        .limit(limit) \
        .execute()

    df = pd.DataFrame(data.data)
    df = _converter_datas_df(df, ["data_hora"])
    return df


# ==============================
# CALLBACK LEITOR
# ==============================
def processar_leitura():
    leitura = _normaliza_codigo(st.session_state.get("input_leitor", ""))
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
            sucesso, erro, aviso = salvar_apontamento(
                st.session_state["numero_serie"],
                st.session_state["op"],
                st.session_state.get("tipo_producao"),
                st.session_state.get("usuario")
            )

            if sucesso:
                st.session_state["sucesso"] = "✅ Apontamento realizado e enviado para a fila"
                st.session_state["aviso"] = aviso
                st.session_state["numero_serie"] = ""
                st.session_state["op"] = ""
            else:
                st.session_state["erro"] = erro

    st.session_state["input_leitor"] = ""


# ==============================
# CHECKLIST
# ==============================
def checklist_qualidade_manga_pnm(numero_serie, tipo_producao, usuario, op):
    numero_serie = _normaliza_codigo(numero_serie)
    op = _normaliza_codigo(op)
    tipo_producao = _normaliza_codigo(tipo_producao)
    usuario = _normaliza_codigo(usuario) or st.session_state.get("usuario") or "Operador_Logado"

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
        "Etiqueta pede Sem Suporte da Bolsa (S/AP)?",
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
        12: "FALTA_SUSPENSOR",
        13: "FALTA_SPT_BOLSA",
        14: "FALTA_MAO_FRANCESA",
        15: "GRAU_DIVERGENTE"
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
        st.markdown("### 📷 Foto do Checklist (tablet)")

        st.markdown("#### 📷 Vista superior do produto (opcional)")
        foto_vista_superior = st.file_uploader(
            "📎 Enviar foto da vista superior (opcional)",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=False,
            key=f"foto_superior_{numero_serie}"
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
                    "data_hora": _agora_utc_iso()
                })

            supabase.table("checklists_manga_pnm_detalhes").insert(registros).execute()

            urls = []
            paths = []

            if foto_vista_superior is not None:
                url, storage_path, _ = upload_foto_para_supabase_storage(
                    numero_serie=numero_serie,
                    tipo_producao=tipo_producao,
                    op=op,
                    usuario=usuario,
                    arquivo=foto_vista_superior,
                    origem="vista_superior"
                )
                if storage_path:
                    paths.append(storage_path)
                if url:
                    urls.append(url)

            if paths:
                st.success(f"✅ {len(paths)} foto enviada para o Storage.")
                st.code("\n".join(paths))

            if urls:
                st.success("✅ Checklist salvo + foto ok.")
            else:
                st.success("✅ Checklist salvo (sem foto).")

            st.session_state["checklist_salvo"] = True
            st.rerun()

    st.divider()
    st.markdown(f"### 🔎 Debug — Série **{numero_serie}**")

    st.markdown("**Tabela `checklists_manga_pnm_fotos` (últimas 50):**")
    df_fotos = listar_fotos_da_serie(numero_serie, tipo_producao=tipo_producao)
    if df_fotos.empty:
        st.caption("Nenhum registro na tabela ainda.")
    else:
        cols_show = [c for c in [
            "data_hora", "numero_serie", "tipo_producao", "op",
            "usuario", "origem", "nome_arquivo", "storage_path", "url"
        ] if c in df_fotos.columns]
        st.dataframe(df_fotos[cols_show], use_container_width=True)

    st.markdown("**Storage (prefixo do bucket):**")
    prefixo = f"{_sanitize(tipo_producao)}/{_sanitize(numero_serie)}/"
    arquivos = listar_arquivos_no_storage(prefixo)
    if not arquivos:
        st.caption(f"Nenhum arquivo encontrado no Storage com prefixo: {prefixo}")
    else:
        st.success(f"✅ Achei {len(arquivos)} arquivo(s) no Storage com prefixo: {prefixo}")
        st.write([a.get("name") for a in arquivos if isinstance(a, dict)])


# ==============================
# EXIBIÇÃO RESULTADO TOTVS
# ==============================
def mostrar_resultado_totvs_visual(retorno, sucesso):
    if not retorno:
        return

    if retorno.get("erro"):
        st.error(retorno["erro"])
        return

    status_code = retorno.get("status_code")

    if sucesso:
        st.success(retorno.get("mensagem_amigavel") or "✅ API respondeu sem erro de negócio aparente.")
    else:
        st.error("❌ A API respondeu com erro ou rejeição de negócio.")

        if retorno.get("mensagem_tela"):
            st.markdown("### Retorno")
            st.code(retorno["mensagem_tela"], language=None)

        itens_estoque = retorno.get("itens_estoque", [])
        if itens_estoque:
            st.markdown("### Itens identificados")
            df_itens = pd.DataFrame(itens_estoque)
            st.dataframe(df_itens, use_container_width=True)

    col1, col2 = st.columns(2)
    col1.metric("HTTP Status", status_code if status_code is not None else "-")
    col2.write(f"**URL:** `{retorno.get('url', '-')}`")

    st.markdown("### Payload enviado")
    st.json(retorno.get("payload", {}))

    with st.expander("Resposta bruta da API"):
        st.code(retorno.get("body", "Sem conteúdo"), language="json")

    if retorno.get("body_json") is not None:
        with st.expander("Resposta JSON da API"):
            st.json(retorno["body_json"])

    with st.expander("JSON tratado para futuro Pareto"):
        st.json({
            "mensagem_amigavel": retorno.get("mensagem_amigavel"),
            "mensagem_tela": retorno.get("mensagem_tela"),
            "itens_estoque": retorno.get("itens_estoque", [])
        })

    with st.expander("Headers da resposta"):
        st.json(retorno.get("headers", {}))


# ==============================
# VISUAL CLEAN / FUTURISTA FILA
# ==============================
def aplicar_css_fila_clean():
    st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
        }

        .fila-box {
            border: 1px solid rgba(20, 73, 98, 0.35);
            border-radius: 22px;
            padding: 18px 22px;
            background:
                linear-gradient(180deg, rgba(248,250,252,0.98), rgba(240,246,250,0.98));
            box-shadow:
                0 12px 30px rgba(15, 45, 61, 0.08),
                inset 0 1px 0 rgba(255,255,255,0.80);
            margin-bottom: 14px;
        }

        .fila-box-titulo {
            font-size: 1.00rem;
            font-weight: 800;
            letter-spacing: 0.02em;
            color: #0b3142;
            margin-bottom: 8px;
        }

        .fila-box-valor {
            font-size: 1.00rem;
            color: #12222b;
            min-height: 28px;
            white-space: pre-wrap;
            line-height: 1.45;
        }

        .fila-box-valor-retorno {
            min-height: 60px;
        }

        .fila-secao-titulo {
            font-size: 1.02rem;
            font-weight: 800;
            margin: 22px 0 12px 0;
            color: #0b3142;
            letter-spacing: 0.02em;
        }

        .fila-card-wrap {
            margin-bottom: 18px;
        }

        .fila-card {
            border-radius: 22px;
            padding: 18px 20px;
            color: white;
            background:
                radial-gradient(circle at top right, rgba(86,173,220,0.22), transparent 28%),
                linear-gradient(135deg, #0a5b77 0%, #0d6a8c 55%, #0b4f68 100%);
            border: 1px solid rgba(121, 201, 255, 0.22);
            box-shadow:
                0 14px 28px rgba(7, 50, 68, 0.20),
                inset 0 1px 0 rgba(255,255,255,0.10);
        }

        .fila-card-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 16px;
        }

        .fila-card-left {
            min-width: 0;
            flex: 1;
        }

        .fila-card-indice {
            display: inline-block;
            font-size: 0.84rem;
            font-weight: 800;
            padding: 5px 10px;
            border-radius: 999px;
            background: rgba(255,255,255,0.12);
            border: 1px solid rgba(255,255,255,0.14);
            margin-bottom: 10px;
        }

        .fila-card-main {
            font-size: 1.12rem;
            font-weight: 800;
            line-height: 1.35;
            word-break: break-word;
        }

        .fila-card-meta {
            margin-top: 10px;
            font-size: 0.90rem;
            color: rgba(255,255,255,0.92);
            display: flex;
            gap: 14px;
            flex-wrap: wrap;
        }

        .fila-status {
            flex-shrink: 0;
            border-radius: 999px;
            padding: 8px 14px;
            font-size: 0.74rem;
            font-weight: 900;
            letter-spacing: 0.05em;
            border: 1px solid rgba(255,255,255,0.16);
            text-transform: uppercase;
            margin-top: 2px;
        }

        .fila-status-pendente {
            background: rgba(255,255,255,0.16);
            color: #ffffff;
        }

        .fila-status-erro {
            background: rgba(215, 75, 92, 0.32);
            color: #ffffff;
        }

        .fila-status-enviado {
            background: rgba(47, 182, 123, 0.30);
            color: #ffffff;
        }

        .fila-acao-info {
            font-size: 0.85rem;
            color: #5b6a72;
            padding: 10px 0 0 4px;
        }

        .fila-ok-pill {
            display: inline-block;
            margin-top: 12px;
            padding: 8px 12px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 800;
            color: #0f5132;
            background: #d1fae5;
            border: 1px solid #a7f3d0;
        }

        .stButton > button {
            width: 100%;
            min-height: 48px;
            border-radius: 14px;
            border: 1px solid rgba(9, 61, 82, 0.20);
            background: linear-gradient(135deg, #0c6c8e 0%, #0b5470 100%);
            color: white;
            font-weight: 800;
            letter-spacing: 0.03em;
            box-shadow: 0 8px 18px rgba(10, 70, 94, 0.18);
        }

        .stButton > button:hover {
            border: 1px solid rgba(9, 61, 82, 0.28);
            background: linear-gradient(135deg, #12779b 0%, #0d617f 100%);
            color: white;
        }

        .stButton > button:focus {
            color: white !important;
            box-shadow: 0 0 0 0.2rem rgba(18, 119, 155, 0.20);
        }
    </style>
    """, unsafe_allow_html=True)


def _ordenar_fila_visual(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    coluna_ordem = "criado_em" if "criado_em" in df.columns else "data_hora"

    try:
        return df.sort_values(coluna_ordem, ascending=True, na_position="last").reset_index(drop=True)
    except Exception:
        return df.reset_index(drop=True)


def _status_visual(status):
    status = str(status or "").strip().lower()

    if status == "enviado":
        return "ENVIADO", "fila-status-enviado"
    if status == "erro":
        return "ERRO", "fila-status-erro"
    return "PENDENTE", "fila-status-pendente"


def _texto_curto(valor, tamanho=800):
    if valor is None:
        return ""

    txt = str(valor).replace("\r", "").strip()
    linhas = [
        re.sub(r"\s+", " ", linha).strip()
        for linha in txt.split("\n")
        if linha.strip()
    ]
    txt = "\n".join(linhas)

    if len(txt) <= tamanho:
        return txt
    return txt[:tamanho - 3].rstrip() + "..."


def _resumo_boxes_fila(df: pd.DataFrame):
    if df.empty:
        return "-", "-", "Pendentes: 0 | Erros: 0 | Enviados: 0"

    pendentes = df[df["status"].astype(str).str.lower() == "pendente"] if "status" in df.columns else pd.DataFrame()
    base = _ordenar_fila_visual(pendentes if not pendentes.empty else df)
    linha = base.iloc[0]

    em_processo = (
        f"OP {_normaliza_codigo(linha.get('op')) or '-'} | "
        f"Série {_normaliza_codigo(linha.get('numero_serie')) or '-'} | "
        f"{_normaliza_codigo(linha.get('tipo_producao')) or '-'}"
    )

    retorno = "-"
    df_recente = df.copy()
    coluna_ordem = "criado_em" if "criado_em" in df_recente.columns else "data_hora"
    try:
        df_recente = df_recente.sort_values(coluna_ordem, ascending=False, na_position="last")
    except Exception:
        pass

    for _, row in df_recente.iterrows():
        resposta_api = _parse_resposta_api(row.get("resposta_api"))
        if isinstance(resposta_api, dict):
            retorno = (
                resposta_api.get("mensagem_tela")
                or resposta_api.get("mensagem_amigavel")
                or resposta_api.get("body")
                or "-"
            )
            retorno = _texto_curto(retorno, 800)
            if retorno and retorno != "-":
                break

        ultimo_erro = row.get("ultimo_erro")
        if ultimo_erro:
            retorno = _texto_curto(ultimo_erro, 800)
            break

    qtd_pendente = int((df["status"] == "pendente").sum()) if "status" in df.columns else 0
    qtd_erro = int((df["status"] == "erro").sum()) if "status" in df.columns else 0
    qtd_enviado = int((df["status"] == "enviado").sum()) if "status" in df.columns else 0

    tabela = f"Pendentes: {qtd_pendente} | Erros: {qtd_erro} | Enviados: {qtd_enviado}"
    return em_processo, retorno, tabela


def _render_box_fila(titulo, valor, retorno=False):
    classe = "fila-box-valor fila-box-valor-retorno" if retorno else "fila-box-valor"
    st.markdown(
        f"""
        <div class="fila-box">
            <div class="fila-box-titulo">{escape(titulo)}</div>
            <div class="{classe}">{escape(valor or "-")}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def _render_cards_fila(df: pd.DataFrame):
    if df.empty:
        st.info("Nenhum item na fila.")
        return

    df = _ordenar_fila_visual(df)

    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        fila_id = int(row["id"])
        status = str(row.get("status", ""))
        numero_serie = _normaliza_codigo(row.get("numero_serie"))
        op = _normaliza_codigo(row.get("op"))
        tipo = _normaliza_codigo(row.get("tipo_producao"))
        dt = _fmt_data(row.get("data_hora"))
        tentativas = int(row.get("tentativas") or 0)

        status_label, status_class = _status_visual(status)

        card_html = f"""
        <div class="fila-card-wrap">
            <div class="fila-card">
                <div class="fila-card-top">
                    <div class="fila-card-left">
                        <div class="fila-card-indice">ITEM {idx}</div>
                        <div class="fila-card-main">
                            OP: {escape(op or '-')} | NÚMERO DE SÉRIE: {escape(numero_serie or '-')}
                        </div>
                        <div class="fila-card-meta">
                            <span><b>Tipo:</b> {escape(tipo or '-')}</span>
                            <span><b>Data:</b> {escape(dt)}</span>
                            <span><b>Tentativas:</b> {tentativas}</span>
                        </div>
                    </div>
                    <div class="fila-status {status_class}">{escape(status_label)}</div>
                </div>
            </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)

        if status == "enviado":
            st.markdown(
                '<div class="fila-ok-pill">Enviado com sucesso</div>',
                unsafe_allow_html=True
            )
        else:
            c1, c2 = st.columns([8, 2])
            with c1:
                st.markdown(
                    '<div class="fila-acao-info">Pronto para execução manual no TOTVS.</div>',
                    unsafe_allow_html=True
                )
            with c2:
                rotulo = "APONTAR" if status == "pendente" else "REENVIAR"
                if st.button(rotulo, key=f"btn_apontar_clean_{fila_id}", use_container_width=True):
                    ok, msg = executar_apontamento_totvs(fila_id)
                    st.session_state["fila_feedback"] = ("success", msg) if ok else ("error", msg)
                    st.rerun()

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)


# ==============================
# PÁGINAS
# ==============================
def pagina_apontamento():
    st.title(APP_NAME)
    st.caption("Apontamento de produção")

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

    if st.session_state.get("aviso"):
        st.warning(st.session_state["aviso"])
        st.session_state["aviso"] = None

    df = carregar_apontamentos()
    if not df.empty:
        st.dataframe(df, use_container_width=True)


def pagina_fila():
    aplicar_css_fila_clean()

    st.title("📮 Fila de Apontamento TOTVS")
    st.caption("O apontamento no TOTVS só acontece ao clicar em 'Apontar'. O histórico antigo não é enviado sozinho.")

    _mostrar_feedback_fila()

    mapa_status = {
        "Pendentes": "pendente",
        "Erros": "erro",
        "Enviados": "enviado",
        "Todos": None
    }

    col1, col2 = st.columns([2, 2])
    with col1:
        filtro = st.radio(
            "Status",
            ["Pendentes", "Erros", "Enviados", "Todos"],
            horizontal=True
        )
    with col2:
        busca = st.text_input("Filtrar por número de série ou OP", "")

    df = carregar_fila_totvs(status=mapa_status[filtro], limit=300)

    if not df.empty and busca.strip():
        termo = busca.strip().lower()
        df = df[
            df["numero_serie"].astype(str).str.lower().str.contains(termo, na=False) |
            df["op"].astype(str).str.lower().str.contains(termo, na=False)
        ]

    if df.empty:
        st.info("Nenhum item na fila para o filtro selecionado.")
        return

    df_topo = df.copy()
    try:
        df_topo = df_topo.sort_values("criado_em", ascending=False, na_position="last").head(5)
        df_topo = df_topo.iloc[::-1].reset_index(drop=True)
    except Exception:
        df_topo = df_topo.head(5).iloc[::-1].reset_index(drop=True)

    em_processo, retorno, tabela = _resumo_boxes_fila(df_topo)

    _render_box_fila("EM PROCESSO:", em_processo)
    _render_box_fila("RETORNO:", retorno, retorno=True)

    st.markdown('<div class="fila-secao-titulo">FILA VISUAL</div>', unsafe_allow_html=True)
    _render_cards_fila(df)

    st.markdown('<div class="fila-secao-titulo">TABELA</div>', unsafe_allow_html=True)
    _render_box_fila("TABELA:", tabela)


def pagina_checklist():
    st.title("🧾 Checklist de Qualidade")

    df_apont = carregar_apontamentos(limit=300)
    hoje = datetime.datetime.now(TZ).date()

    if df_apont.empty:
        st.info("Nenhum apontamento hoje")
        return

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

    opcoes_series = [_normaliza_codigo(x) for x in df_pendentes["numero_serie"].unique()]

    numero_serie = st.selectbox(
        "Selecione a série",
        opcoes_series,
        key="serie_selecionada"
    )

    df_pendentes = df_pendentes.copy()
    df_pendentes["numero_serie"] = df_pendentes["numero_serie"].apply(_normaliza_codigo)

    df_sel = df_pendentes[df_pendentes["numero_serie"] == numero_serie]
    if df_sel.empty:
        st.warning("Série já inspecionada")
        return

    linha = df_sel.iloc[0]

    checklist_qualidade_manga_pnm(
        numero_serie,
        linha["tipo_producao"],
        st.session_state.get("usuario"),
        linha["op"]
    )


def pagina_teste_totvs():
    st.title("🧪 Teste de Apontamento TOTVS")
    st.caption("Teste direto do POST /NEW, com checagem prévia da série no GET.")

    with st.form("form_teste_apontamento"):
        numero_serie = st.text_input("Número de série", placeholder="Ex.: 260319859")
        op = st.text_input("OP", placeholder="Ex.: 95252501001")
        quant = st.text_input("Quantidade", value="1", placeholder="Ex.: 1")
        lotectl = st.text_input(
            "Lote / Número de Série",
            value=numero_serie,
            placeholder="Ex.: 260319859"
        )

        submit_verificar = st.form_submit_button("Verificar série", use_container_width=True)
        submit_apontar = st.form_submit_button("Apontar", use_container_width=True)

    if submit_verificar:
        retorno = consultar_numero_serie_totvs(numero_serie)
        if retorno["ok"]:
            if retorno["existe"]:
                st.warning(retorno["mensagem"])
            else:
                st.success(retorno["mensagem"])
        else:
            st.error(retorno["mensagem"])

    if submit_apontar:
        retorno_check = consultar_numero_serie_totvs(numero_serie)
        if not retorno_check["ok"]:
            st.error(retorno_check["mensagem"])
        elif retorno_check["existe"]:
            st.warning(f"Série {numero_serie} já está apontada no TOTVS.")
        else:
            sucesso, retorno = apontar_op_totvs(op, quant, lotectl or numero_serie)
            mostrar_resultado_totvs_visual(retorno=retorno, sucesso=sucesso)

    st.divider()

    with st.expander("Configuração carregada"):
        st.write("**TOTVS_API_BASE:**", TOTVS_API_BASE)
        st.write("**TOTVS_TIMEOUT:**", TOTVS_TIMEOUT)
        st.write("**TOTVS_USERNAME:**", TOTVS_USERNAME if TOTVS_USERNAME else "(vazio)")
        st.write("**TOTVS_TENANT_ID:**", TOTVS_TENANT_ID if TOTVS_TENANT_ID else "(vazio)")
        st.write("**Usuário logado:**", st.session_state.get("usuario", "-"))


# ==============================
# APP
# ==============================
def app():
    inicializar_estado()
    exigir_login()

    with st.sidebar:
        st.markdown(f"### {APP_NAME}")
        st.write(f"👤 **{st.session_state.get('usuario', '-')}**")
        if st.button("Sair", use_container_width=True):
            logout_app()
            st.rerun()

    menu = st.sidebar.radio(
        "Menu",
        ["Apontamento", "Fila", "Checklist", "Teste TOTVS"]
    )

    if menu == "Apontamento":
        pagina_apontamento()
    elif menu == "Fila":
        pagina_fila()
    elif menu == "Checklist":
        pagina_checklist()
    else:
        pagina_teste_totvs()


if __name__ == "__main__":
    app()

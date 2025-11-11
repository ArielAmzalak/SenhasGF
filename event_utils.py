
# event_utils.py — utilitários para o "Distribuidor de Senhas" (Streamlit + Google Sheets + PDF)
from __future__ import annotations

import io
import os
import re
import json
import unicodedata
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo

import qrcode
from fpdf import FPDF
from barcode import Code128
from barcode.writer import ImageWriter

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.service_account import Credentials as SACredentials
from google.oauth2.credentials import Credentials as UserCredentials
from google.auth.transport.requests import Request

try:
    import streamlit as st
except ModuleNotFoundError:
    st = None

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DEFAULT_TIMEZONE = os.getenv("APP_TZ", "America/Manaus")

HEADERS = [
    "Senha",
    "Nome",
    "Telefone",
    "Bairro",
    "Data e Hora de Registro",
    "Data e Hora de Atendimento",
]

# Aba com as áreas/setores
NOMES_SHEET = os.getenv("NOMES_SHEET", "Nomes")

# Aba com a lista de bairros
BAIRROS_SHEET = os.getenv("BAIRROS_SHEET", "Bairro")

# ✅ Pedido do usuário: Spreadsheet ID definido **no código** (não em secrets)
HARDCODED_SPREADSHEET_ID = "1eEvF5c8rTXwWKqgmyCMXU5OPJKqBk5XPt4Yry5B4x5c"


def _normalize(s: str) -> str:
    s = s or ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.strip().lower()


def format_phone_number(telefone: str) -> str:
    """Normaliza números para o padrão local `(92) 98123-1234`."""

    telefone = (telefone or "").strip()
    if not telefone:
        return ""

    digits = re.sub(r"\D", "", telefone)
    if not digits:
        return ""

    # Remove código do país (55) se presente
    if digits.startswith("55") and len(digits) > 11:
        digits = digits[2:]

    # Mantém apenas os últimos 11 dígitos, caso haja sobras
    if len(digits) > 11:
        digits = digits[-11:]

    # Remove DDD original e força o DDD 92
    if len(digits) >= 11:
        digits = digits[-9:]
    elif len(digits) >= 9:
        digits = digits[-9:]
    else:
        # Completa com zeros à esquerda para manter o formato solicitado
        digits = digits.rjust(9, "0")

    return f"(92) {digits[:5]}-{digits[5:]}"


def format_name_upper(nome: str) -> str:
    """Garante nome em caixa alta, preservando espaços externos."""

    return (nome or "").strip().upper()


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = _normalize(str(v))
    return s in {"sim", "s", "true", "1", "y", "yes", "ativo", "ativa", "on", "ok"}


def _authorize_google_sheets():
    # Prefer service account (GOOGLE_SERVICE_ACCOUNT_JSON) quando rodar na nuvem
    sa_json = None
    if st:
        sa_json = st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON", None)
    if not sa_json:
        sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    if sa_json:
        try:
            info = json.loads(sa_json)
            creds = SACredentials.from_service_account_info(info, scopes=SCOPES)
            return creds
        except Exception as exc:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON inválido.") from exc

    # Fallback: OAuth de usuário (GOOGLE_CLIENT_SECRET) — compatível com apps antigos
    client_json = None
    if st:
        client_json = st.secrets.get("GOOGLE_CLIENT_SECRET", None)
    if not client_json:
        client_json = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_json:
        raise RuntimeError("Credenciais Google ausentes. Defina GOOGLE_SERVICE_ACCOUNT_JSON (preferível) ou GOOGLE_CLIENT_SECRET.")

    token_path = "token.json"
    creds = None
    if os.path.exists(token_path):
        creds = UserCredentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow
            conf = json.loads(client_json)
            flow = InstalledAppFlow.from_client_config(conf, SCOPES)
            # Em ambiente headless, utiliza run_console()
            creds = flow.run_console()
        with open(token_path, "w", encoding="utf-8") as fp:
            fp.write(creds.to_json())
    return creds


def _sheets_service():
    return build("sheets", "v4", credentials=_authorize_google_sheets(), cache_discovery=False)


def _get_spreadsheet_id() -> str:
    # ✅ Preferir ID definido no código (não em secrets) — pedido do usuário
    sid = (HARDCODED_SPREADSHEET_ID or "").strip()
    if sid:
        return sid
    # Fallback para compatibilidade (caso remova o hardcoded)
    sid = None
    if st:
        sid = st.secrets.get("SPREADSHEET_ID")
    if not sid:
        sid = os.getenv("SPREADSHEET_ID", "")
    if not sid:
        raise RuntimeError("SPREADSHEET_ID não configurado (defina no código, secrets ou variável de ambiente).")
    return sid


def _find_col_indexes(header_row: List[str], candidates: List[str]) -> Optional[int]:
    norm = [_normalize(h) for h in header_row]
    for want in candidates:
        want_n = _normalize(want)
        for idx, col in enumerate(norm):
            if col == want_n:
                return idx
    return None


def _get_sheet_metadata(service, spreadsheet_id: str) -> Dict[str, Any]:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    return meta


def _sheet_exists(meta: Dict[str, Any], title: str) -> Tuple[bool, Optional[int]]:
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == title:
            return True, int(props.get("sheetId"))
    return False, None


def ensure_area_sheet(service, spreadsheet_id: str, title: str) -> None:
    """Garante que a aba da área existe e tem os cabeçalhos esperados."""
    meta = _get_sheet_metadata(service, spreadsheet_id)
    exists, _ = _sheet_exists(meta, title)
    if not exists:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
        ).execute()
        # escreve cabeçalho
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{title}!A1:F1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ).execute()
        return
    # se já existe, valida cabeçalho (não falha se estiver diferente; apenas atualiza se vazio)
    rng = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{title}!1:1",
    ).execute()
    row1 = rng.get("values", [[]])
    if not row1 or not row1[0]:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{title}!A1:F1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ).execute()


def read_active_areas(service, spreadsheet_id: str) -> List[Dict[str, Any]]:
    """
    Lê a aba NOMES (por padrão 'Nomes') e retorna apenas as áreas ativas.
    Campos aceitos (case/acento-insensitive):
      - Área (ou Area, Setor, Mesa)
      - Aba (ou Sheet, AbaDestino, Destino) — se ausente, usa o mesmo texto da Área
      - Ativa (ou Status) — valores: Sim/Nao, True/False, 1/0, Ativo/Inativo
    """
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{NOMES_SHEET}!A:Z",
        ).execute()
    except HttpError as exc:
        raise RuntimeError(f"Erro ao ler a aba '{NOMES_SHEET}': {exc}") from exc

    rows = result.get("values", [])
    if not rows:
        return []

    header = rows[0]
    area_idx = _find_col_indexes(header, ["Área", "Area", "Setor", "Mesa", "Área/Setor"])
    aba_idx = _find_col_indexes(header, ["Aba", "Sheet", "AbaDestino", "Aba Destino", "Destino", "Guia", "Tab"])
    ativa_idx = _find_col_indexes(header, ["Ativa", "Ativo", "Status", "Habilitada", "Disponível"])

    if area_idx is None:
        raise RuntimeError("Coluna 'Área' (ou equivalente) não encontrada na aba 'Nomes'.")

    areas: List[Dict[str, Any]] = []
    for row in rows[1:]:
        area = (row[area_idx] if area_idx < len(row) else "").strip()
        if not area:
            continue
        sheet_title = (row[aba_idx] if (aba_idx is not None and aba_idx < len(row)) else area).strip() or area
        ativa_val = (row[ativa_idx] if (ativa_idx is not None and ativa_idx < len(row)) else "Sim")
        ativa = _truthy(ativa_val)
        if ativa:
            areas.append({"area": area, "sheet": sheet_title, "ativa": True})
    return areas


def read_neighborhoods(service, spreadsheet_id: str) -> List[str]:
    """Lê a aba de bairros e devolve uma lista com os nomes válidos."""
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{BAIRROS_SHEET}!A:A",
        ).execute()
    except HttpError as exc:
        raise RuntimeError(f"Erro ao ler a aba '{BAIRROS_SHEET}': {exc}") from exc

    rows = result.get("values", [])
    if not rows:
        return []

    bairros: List[str] = []
    for idx, row in enumerate(rows):
        nome = (row[0] if row else "").strip()
        if not nome:
            continue
        if idx == 0 and _normalize(nome) in {"nome do bairro", "bairro"}:
            # ignora o cabeçalho
            continue
        bairros.append(nome)
    return bairros


def append_ticket_and_get_number(service, spreadsheet_id: str, sheet_title: str, row_values: List[str]) -> int:
    """
    Faz append da linha (com Senha vazia) e retorna o número da senha atribuído com base no índice da linha.
    Estratégia: append → extrair 'updatedRange' → calcular row_idx → Senha = row_idx - 1 → update célula A{row_idx}
    """
    # Garante a aba e cabeçalhos
    ensure_area_sheet(service, spreadsheet_id, sheet_title)

    # Append sem a coluna Senha (deixa vazio em A); gravar B..F
    body = {"values": [[
        "",  # Senha (será preenchida em seguida)
        row_values[1],  # Nome
        row_values[2],  # Telefone
        row_values[3],  # Bairro
        row_values[4],  # Data e Hora de Registro
        row_values[5],  # Data e Hora de Atendimento
    ]]}
    append_result = service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_title}!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()

    updated_range = (append_result or {}).get("updates", {}).get("updatedRange", "")
    # extrai o número da última linha gravada (mesma técnica usada em utilidades similares)
    m = re.search(r"!.*?(\d+):", updated_range) or re.search(r"!.*?(\d+)$", updated_range)
    if not m:
        raise RuntimeError(f"Não foi possível detectar a linha inserida: {updated_range}")
    row_idx_int = int(m.group(1))

    # Cabeçalho está na linha 1 → senha = row_idx - 1
    senha_num = max(1, row_idx_int - 1)

    # Atualiza a célula A{row_idx} com o número da senha
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_title}!A{row_idx_int}",
        valueInputOption="RAW",
        body={"values": [[str(senha_num)]]},
    ).execute()

    return senha_num


def now_str(tz_name: str = DEFAULT_TIMEZONE) -> str:
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = None
    dt = datetime.now(tz=tz)
    return dt.strftime("%d/%m/%Y %H:%M:%S")


def generate_ticket_pdf(data: Dict[str, str]) -> bytes:
    """
    Gera um PDF estilo "ticket" (80x120mm) com QR e Code128 da Senha.
    Campos esperados em data: area, senha, nome, telefone, bairro, ts_registro
    """
    area = str(data.get("area", "Área")).strip()
    senha = str(data.get("senha", "0")).strip()
    nome  = format_name_upper(data.get("nome", ""))
    tel   = format_phone_number(data.get("telefone", ""))
    bairro= str(data.get("bairro", "")).strip()
    ts    = str(data.get("ts_registro", "")).strip()

    # QR (conteúdo: "AREA|SENHA|NOME")
    qr_payload = f"{area}|{senha}|{nome}"
    qr_img = qrcode.make(qr_payload)
    buf_qr = io.BytesIO()
    qr_img.save(buf_qr, format="PNG")
    buf_qr.seek(0)

    # Code128 com a senha
    buf_bar = io.BytesIO()
    Code128(senha, writer=ImageWriter()).write(buf_bar, options={
        "module_width": 0.3,
        "module_height": 12,
        "font_size": 8,
    })
    buf_bar.seek(0)

    pdf = FPDF(unit="mm", format=(80, 120))  # ticket
    pdf.set_auto_page_break(False)
    pdf.add_page()
    pdf.set_left_margin(6)
    pdf.set_right_margin(6)
    pdf.set_top_margin(6)

    # Cabeçalho
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, "Distribuidor de Senhas", ln=True, align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 6, area, ln=True, align="C")
    pdf.ln(2)

    # Senha grande
    pdf.set_font("Helvetica", "B", 40)
    pdf.cell(0, 18, f"{senha}", ln=True, align="C")
    pdf.ln(1)

    # Barra + QR
    x = pdf.get_x()
    y = pdf.get_y()
    pdf.image(buf_bar, x=x+10, y=y, w=50)
    pdf.ln(16)
    pdf.image(buf_qr, x=(80-30)/2, y=pdf.get_y()+2, w=30)
    pdf.ln(34)

    # Dados do participante
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Nome: {nome}", ln=True)
    pdf.cell(0, 6, f"Telefone: {tel}", ln=True)
    pdf.cell(0, 6, f"Bairro: {bairro}", ln=True)
    pdf.cell(0, 6, f"Registro: {ts}", ln=True)
    pdf.ln(2)

    # Rodapé
    pdf.set_font("Helvetica", "I", 8)
    pdf.cell(0, 6, "Guarde este ticket até o atendimento.", ln=True, align="C")

    raw = pdf.output(dest="S")
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else str(raw).encode("latin-1")


def submit_ticket(area: str, nome: str, telefone: str, bairro: str) -> Tuple[int, bytes]:
    """
    Faz toda a operação:
      1) Determina aba de destino a partir de 'Nomes' (usa 'area' -> sheet)
      2) Gera timestamp de registro
      3) Faz append na aba e atribui a Senha (sequencial da planilha)
      4) Gera PDF e devolve (senha_num, pdf_bytes)
    """
    service = _sheets_service()
    spreadsheet_id = _get_spreadsheet_id()

    # Consulta áreas ativas e mapeamento area->sheet
    areas = read_active_areas(service, spreadsheet_id)
    map_area_sheet = {a["area"]: a["sheet"] for a in areas}
    sheet_title = map_area_sheet.get(area) or area  # fallback: nome da área == nome da aba

    nome_fmt = format_name_upper(nome)
    telefone_fmt = format_phone_number(telefone)

    ts = now_str()
    row = ["", nome_fmt, telefone_fmt, bairro, ts, ""]  # Senha vazia; Atendimento em branco
    senha_num = append_ticket_and_get_number(service, spreadsheet_id, sheet_title, row)

    pdf_bytes = generate_ticket_pdf({
        "area": area,
        "senha": str(senha_num),
        "nome": nome_fmt,
        "telefone": telefone_fmt,
        "bairro": bairro,
        "ts_registro": ts,
    })
    return senha_num, pdf_bytes

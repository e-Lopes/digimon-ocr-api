import base64
import json
import os
import re
from datetime import datetime

# Carrega .env local se existir (desenvolvimento)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_MODEL = "qwen/qwen3.6-27b"
MODEL = os.getenv("GROQ_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "1200"))

PROMPT = """
Analise esta imagem de ranking do aplicativo Digimon TCG (BANDAI).
Extraia os dados do evento e todos os jogadores visiveis na tabela.
Retorne SOMENTE um JSON valido, sem texto adicional, sem markdown.

Formato esperado:
{
  "store_name": "Meruru Curitiba",
  "tournament_datetime": "Fri. February 20, 2026 07:00 PM~",
  "players": [{"rank": 1, "name": "Edu", "member_id": "0000238403", "points": "12", "omw": "47.1"}, ...]
}

Regras:
- store_name: nome da loja em azul (link clicavel logo abaixo do titulo do evento), ex: "Meruru Curitiba". NUNCA retorne endereco (ex: "Parana Curitiba...", "Rua...", "Avenida...", "Loja ..."). Se nao visivel, use ""
- tournament_datetime: texto completo da data/hora do evento (faixa vermelha). Se nao visivel, use ""
- rank: numero inteiro da posicao (1, 2, 3...)
- name: nome/nick do jogador exatamente como aparece na coluna User Name. Se nao visivel, use ""
- member_id: exatamente 10 digitos numericos OU comeca com GUEST seguido de digitos
- points: apenas o numero inteiro de Win Points (ex: "12"). Se nao visivel, use ""
- omw: apenas o numero do OMW% sem o simbolo % (ex: "47.1" ou "37"). Se nao visivel, use ""
- Ignore cabecalhos, rodapes, status bar e navegacao do celular
- Retorne SOMENTE o JSON
"""

def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        candidates = []
        for match in re.finditer(r"\{", text):
            try:
                value, _ = decoder.raw_decode(text[match.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                candidates.append(value)
        if candidates:
            return candidates[-1]
        raise


def normalize_event_date(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text

    clean = re.sub(r"^\w{3}\.\s*", "", text)
    clean = clean.replace("~", "").strip()

    match_en = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", clean)
    if match_en:
        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        month = month_map.get(match_en.group(1).lower())
        day = int(match_en.group(2))
        year = int(match_en.group(3))
        if month:
            try:
                return datetime(year=year, month=month, day=day).strftime("%Y-%m-%d")
            except ValueError:
                return ""

    match_br = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", clean)
    if match_br:
        try:
            return datetime(
                year=int(match_br.group(3)),
                month=int(match_br.group(2)),
                day=int(match_br.group(1)),
            ).strftime("%Y-%m-%d")
        except ValueError:
            return ""

    return ""


def looks_like_address(text: str) -> bool:
    value = str(text or "").strip().lower()
    if not value:
        return False
    address_terms = [
        "parana", "paraná", "curitiba", "avenida", "av ", " av.",
        "rua", "alameda", "travessa", "loja", "numero", "nº", "cep",
    ]
    return any(term in value for term in address_terms) and bool(re.search(r"\d{2,}", value))


_client: Groq | None = None
_selected_model: str | None = None

def get_client() -> Groq:
    global _client
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY nao configurada")
    if _client is None:
        _client = Groq(api_key=api_key)
    return _client


def model_candidates() -> list[str]:
    configured_fallbacks = os.getenv("GROQ_FALLBACK_MODELS", "")
    values = [MODEL, *configured_fallbacks.split(","), DEFAULT_MODEL]
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def resolve_vision_model(force_refresh: bool = False) -> str:
    """Seleciona um modelo visual ativo e disponível para a chave atual."""
    global _selected_model
    if _selected_model and not force_refresh:
        return _selected_model

    models = get_client().models.list().data
    visual_models = {
        model.id
        for model in models
        if getattr(model, "active", True)
        and "image" in (getattr(model, "input_modalities", None) or [])
        and "text" in (getattr(model, "output_modalities", None) or [])
    }
    for candidate in model_candidates():
        if candidate in visual_models:
            _selected_model = candidate
            return candidate

    if visual_models:
        _selected_model = sorted(visual_models)[0]
        return _selected_model
    raise RuntimeError("Nenhum modelo visual disponivel na conta Groq")


def is_missing_model_error(error: Exception) -> bool:
    return getattr(error, "status_code", None) == 404 or "model_not_found" in str(error)


def classify_error(error: Exception) -> str:
    status_code = getattr(error, "status_code", None)
    message = str(error).lower()
    if status_code == 401:
        return "groq_authentication_error"
    if status_code == 404 or "model_not_found" in message:
        return "groq_model_not_found"
    if status_code == 413:
        return "groq_request_too_large"
    if status_code == 429:
        return "groq_rate_limit"
    if "json" in message:
        return "invalid_model_json"
    return "ocr_processing_error"


def run_vision_prompt(b64_image: str, mime_type: str) -> str:
    global _selected_model
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64_image}"},
                },
            ],
        }
    ]

    for attempt in range(2):
        model = resolve_vision_model(force_refresh=attempt > 0)
        options = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": MAX_TOKENS,
            "response_format": {"type": "json_object"},
        }
        if model.startswith("qwen/"):
            options["reasoning_effort"] = "none"
        try:
            response = get_client().chat.completions.create(**options)
            return str(response.choices[0].message.content or "")
        except Exception as error:
            if attempt == 0 and is_missing_model_error(error):
                _selected_model = None
                continue
            raise
    raise RuntimeError("Nao foi possivel selecionar um modelo visual")


@app.get("/health")
async def healthcheck():
    selected_model = ""
    model_available = False
    model_error = ""
    try:
        selected_model = resolve_vision_model()
        model_available = True
    except Exception as error:
        model_error = str(error)
    return {
        "status": "ok" if model_available else "degraded",
        "configured_model": MODEL,
        "selected_model": selected_model,
        "model_available": model_available,
        "model_error": model_error,
        "groq_api_key_configured": bool(os.getenv("GROQ_API_KEY", "").strip()),
    }


@app.post("/process")
async def process_ocr(file: UploadFile = File(...)):
    contents = await file.read()
    b64_image = base64.b64encode(contents).decode("utf-8")
    mime_type = file.content_type or "image/jpeg"
    raw_text = ""

    try:
        raw_text = run_vision_prompt(b64_image=b64_image, mime_type=mime_type)

        data = extract_json(raw_text)
        store_name = str(data.get("store_name", "")).strip()
        if looks_like_address(store_name):
            store_name = ""
        tournament_datetime = str(data.get("tournament_datetime", "")).strip()
        tournament_date = normalize_event_date(tournament_datetime)

        result = []
        for p in data.get("players", []):
            member_id = str(p.get("member_id", "")).strip()
            if not re.match(r"^\d{10}$|^GUEST\d+$", member_id, re.IGNORECASE):
                continue
            try:
                rank = int(p.get("rank", 0))
            except (ValueError, TypeError):
                rank = 0
            result.append({
                "rank": rank,
                "name": str(p.get("name", "")).strip(),
                "member_id": member_id.upper(),
                "points": str(p.get("points", "")),
                "omw": str(p.get("omw", "")),
            })

        return {
            "store_name": store_name,
            "tournament_datetime": tournament_datetime,
            "tournament_date": tournament_date,
            "model": _selected_model or MODEL,
            "players": result,
        }

    except Exception as e:
        return {
            "store_name": "",
            "tournament_datetime": "",
            "tournament_date": "",
            "players": [],
            "model": _selected_model or MODEL,
            "error_code": classify_error(e),
            "error": str(e),
            "raw": raw_text or "sem resposta",
        }


@app.post("/debug")
async def debug_ocr(file: UploadFile = File(...)):
    contents = await file.read()
    b64_image = base64.b64encode(contents).decode("utf-8")
    mime_type = file.content_type or "image/jpeg"
    try:
        raw = run_vision_prompt(b64_image=b64_image, mime_type=mime_type)
        return {"raw": raw}
    except Exception as e:
        return {"error": str(e)}

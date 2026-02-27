import base64
import json
import os
import re
from datetime import datetime

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

client = None
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

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
- store_name: nome da loja do evento (ex: "Meruru Curitiba"). Se nao visivel, use ""
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
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
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
        month_name = match_en.group(1).lower()
        month_map = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }
        month = month_map.get(month_name)
        day = int(match_en.group(2))
        year = int(match_en.group(3))
        if month:
            try:
                dt = datetime(year=year, month=month, day=day)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                return ""

    match_br = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", clean)
    if match_br:
        day = int(match_br.group(1))
        month = int(match_br.group(2))
        year = int(match_br.group(3))
        try:
            dt = datetime(year=year, month=month, day=day)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return ""

    return ""


def get_client() -> Groq:
    global client
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY nao configurada")
    if client is None:
        client = Groq(api_key=api_key)
    return client


def run_vision_prompt(b64_image: str, mime_type: str) -> str:
    response = get_client().chat.completions.create(
        model=MODEL,
        messages=[
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
        ],
        max_tokens=1200,
    )
    return response.choices[0].message.content


@app.get("/health")
async def healthcheck():
    return {
        "status": "ok",
        "model": MODEL,
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
        players = data.get("players", [])
        store_name = str(data.get("store_name", "")).strip()
        tournament_datetime = str(data.get("tournament_datetime", "")).strip()
        tournament_date = normalize_event_date(tournament_datetime)

        result = []
        for p in players:
            member_id = str(p.get("member_id", "")).strip()
            if not re.match(r"^\d{10}$|^GUEST\d+$", member_id, re.IGNORECASE):
                continue
            try:
                rank = int(p.get("rank", 0))
            except (ValueError, TypeError):
                rank = 0
            result.append(
                {
                    "rank": rank,
                    "name": str(p.get("name", "")).strip(),
                    "member_id": member_id.upper(),
                    "points": str(p.get("points", "")),
                    "omw": str(p.get("omw", "")),
                }
            )

        return {
            "store_name": store_name,
            "tournament_datetime": tournament_datetime,
            "tournament_date": tournament_date,
            "players": result,
        }

    except Exception as e:
        return {
            "store_name": "",
            "tournament_datetime": "",
            "tournament_date": "",
            "players": [],
            "error": str(e),
            "raw": raw_text or "sem resposta",
        }


@app.post("/debug")
async def debug_ocr(file: UploadFile = File(...)):
    contents = await file.read()
    b64_image = base64.b64encode(contents).decode("utf-8")
    mime_type = file.content_type or "image/jpeg"
    try:
        return {"raw": run_vision_prompt(b64_image=b64_image, mime_type=mime_type)}
    except Exception as e:
        return {"error": str(e)}

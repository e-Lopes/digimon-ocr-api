import os
import json
import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL  = "gemini-1.5-flash"

PROMPT = """
Analise esta imagem de ranking do aplicativo Digimon TCG (BANDAI).
Extraia TODOS os jogadores visíveis na tabela e retorne SOMENTE um JSON válido, sem texto adicional, sem markdown, sem bloco de código.

Formato esperado:
{"players": [{"rank": 1, "member_id": "0000238403", "points": "12", "omw": "47.1"}, ...]}

Regras:
- rank: número inteiro da posição (1, 2, 3...)
- member_id: exatamente 10 dígitos numéricos OU começa com GUEST seguido de dígitos
- points: apenas o número inteiro de Win Points (ex: "12"). Se não visível, use ""
- omw: apenas o número do OMW% sem o símbolo % (ex: "47.1" ou "37"). Se não visível, use ""
- Ignore cabeçalhos, rodapés, status bar e navegação do celular
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


@app.post("/process")
async def process_ocr(file: UploadFile = File(...)):
    contents = await file.read()
    raw_text = ""
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                PROMPT,
                types.Part.from_bytes(data=contents, mime_type=file.content_type or "image/jpeg")
            ]
        )
        raw_text = response.text

        data    = extract_json(raw_text)
        players = data.get("players", [])

        result = []
        for p in players:
            member_id = str(p.get("member_id", "")).strip()
            if not re.match(r"^\d{10}$|^GUEST\d+$", member_id, re.IGNORECASE):
                continue
            result.append({
                "rank":      int(p.get("rank", 0)),
                "member_id": member_id.upper(),
                "points":    str(p.get("points", "")),
                "omw":       str(p.get("omw", "")),
            })

        return {"players": result}

    except Exception as e:
        return {"players": [], "error": str(e), "raw": raw_text or "sem resposta"}


@app.post("/debug")
async def debug_ocr(file: UploadFile = File(...)):
    contents = await file.read()
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                PROMPT,
                types.Part.from_bytes(data=contents, mime_type=file.content_type or "image/jpeg")
            ]
        )
        return {"raw": response.text}
    except Exception as e:
        return {"error": str(e)}


@app.get("/models")
async def list_models():
    """Lista modelos disponíveis para debug."""
    try:
        models = [m.name for m in client.models.list()]
        return {"models": models}
    except Exception as e:
        return {"error": str(e)}
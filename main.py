import os
import json
import re
import base64
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL  = "meta-llama/llama-4-scout-17b-16e-instruct"

PROMPT = """
Analise esta imagem de ranking do aplicativo Digimon TCG (BANDAI).
Extraia TODOS os jogadores visíveis na tabela e retorne SOMENTE um JSON válido, sem texto adicional, sem markdown, sem bloco de código.

Formato esperado:
{"players": [{"rank": 1, "name": "Edu", "member_id": "0000238403", "points": "12", "omw": "47.1"}, ...]}

Regras:
- rank: número inteiro da posição (1, 2, 3...)
- name: nome/nick do jogador exatamente como aparece na coluna User Name. Se não visível, use ""
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
    contents  = await file.read()
    b64_image = base64.b64encode(contents).decode("utf-8")
    mime_type = file.content_type or "image/jpeg"
    raw_text  = ""

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}}
                ]
            }],
            max_tokens=1024,
        )
        raw_text = response.choices[0].message.content

        data    = extract_json(raw_text)
        players = data.get("players", [])

        result = []
        for p in players:
            member_id = str(p.get("member_id", "")).strip()
            if not re.match(r"^\d{10}$|^GUEST\d+$", member_id, re.IGNORECASE):
                continue
            result.append({
                "rank":      int(p.get("rank", 0)),
                "name":      str(p.get("name", "")).strip(),
                "member_id": member_id.upper(),
                "points":    str(p.get("points", "")),
                "omw":       str(p.get("omw", "")),
            })

        return {"players": result}

    except Exception as e:
        return {"players": [], "error": str(e), "raw": raw_text or "sem resposta"}


@app.post("/debug")
async def debug_ocr(file: UploadFile = File(...)):
    contents  = await file.read()
    b64_image = base64.b64encode(contents).decode("utf-8")
    mime_type = file.content_type or "image/jpeg"
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_image}"}}
                ]
            }],
            max_tokens=1024,
        )
        return {"raw": response.choices[0].message.content}
    except Exception as e:
        return {"error": str(e)}
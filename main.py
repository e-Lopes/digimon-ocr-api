import os
import json
import re
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from PIL import Image
import io

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

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
    """Extrai JSON mesmo se o modelo retornar texto extra."""
    text = text.strip()
    # Remove blocos de markdown se existirem
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Tenta parse direto
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Tenta extrair o primeiro objeto JSON encontrado
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


@app.post("/process")
async def process_ocr(file: UploadFile = File(...)):
    contents = await file.read()
    image    = Image.open(io.BytesIO(contents))

    try:
        response = model.generate_content([PROMPT, image])
        data     = extract_json(response.text)
        players  = data.get("players", [])

        # Sanitiza e valida cada player
        result = []
        for p in players:
            member_id = str(p.get("member_id", "")).strip()
            # Valida: 10 dígitos ou GUEST+dígitos
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
        return {"players": [], "error": str(e)}
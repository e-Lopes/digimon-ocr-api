from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import pytesseract
import re

app = FastAPI()

# Permite acesso do seu GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MEMBER_RE = re.compile(r"\b(\d{10}|GUEST\d{3,})\b", re.IGNORECASE)

@app.post("/process")
async def process_ocr(file: UploadFile = File(...)):
    # Lê a imagem
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Pré-processamento (Cinza + Contraste)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Extração de dados com Tesseract
    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
    
    h_img, w_img = gray.shape
    tokens = []
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        if text:
            tokens.append({
                "text": text,
                "x_pct": (data['left'][i] / w_img) * 100,
                "y_pct": (data['top'][i] / h_img) * 100,
                "h_pct": (data['height'][i] / h_img) * 100
            })

    # Agrupar por Member Number (Âncora)
    players = []
    anchors = [t for t in tokens if MEMBER_RE.search(t['text'])]
    
    for a in anchors:
        m_id = MEMBER_RE.search(a['text']).group(1)
        y_ref = a['y_pct']
        
        # Busca Nick: Na mesma coluna (14-65%) e levemente acima do ID
        nick_tokens = [t for t in tokens if 14 < t['x_pct'] < 65 and abs(t['y_pct'] - (y_ref - 2.5)) < 3.5]
        nick_tokens.sort(key=lambda t: t['x_pct'])
        nick = " ".join([t['text'] for t in nick_tokens if not MEMBER_RE.search(t['text'])])

        # Busca Win Points (coluna 65-80%)
        pts_tokens = [t for t in tokens if 65 < t['x_pct'] < 80 and abs(t['y_pct'] - (y_ref - 2.5)) < 4]
        pts = "".join(filter(str.isdigit, "".join([t['text'] for t in pts_tokens])))

        players.append({
            "rank": "?", # Será inferido pela ordem no JS
            "name": nick or "Não lido",
            "member_id": m_id,
            "points": pts or "0",
            "y": y_ref
        })

    # Ordena por Y (posição vertical) para garantir o ranking correto
    players.sort(key=lambda p: p['y'])
    
    return {"players": players}
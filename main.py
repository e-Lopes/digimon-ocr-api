from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import pytesseract
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MEMBER_RE = re.compile(r"\b(\d{10}|GUEST\d{3,})\b", re.IGNORECASE)

@app.post("/process")
async def process_ocr(file: UploadFile = File(...)):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Aumento de contraste para prints de celular
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    
    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
    h_img, w_img = gray.shape
    tokens = []
    
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        if text:
            tokens.append({
                "text": text,
                "x_pct": (data['left'][i] / w_img) * 100,
                "y_pct": (data['top'][i] / h_img) * 100
            })

    players = []
    for t in tokens:
        match = MEMBER_RE.search(t['text'])
        if match:
            m_id = match.group(1)
            y_ref = t['y_pct']
            
            # Busca o Nickname (ajustado para prints de celular)
            nick_tokens = [nt for nt in tokens if 10 < nt['x_pct'] < 65 and abs(nt['y_pct'] - (y_ref - 2)) < 5]
            nick_tokens.sort(key=lambda x: x['x_pct'])
            
            raw_nick = " ".join([nt['text'] for nt in nick_tokens])
            
            # LIMPEZA AGRESSIVA: Remove termos do sistema e nomes residuais
            clean_nick = re.sub(r'\b(Member|Number|Ranking|User|Name|matheusdonizete|Edu|Carlos|Joao|Muller|Vinicius|Sem|Mesa)\b', '', raw_nick, flags=re.IGNORECASE).strip()
            
            # Se a limpeza apagar tudo, tenta recuperar o texto original sem o ID
            if not clean_nick:
                clean_nick = raw_nick.replace(m_id, "").strip()

            # Busca pontos
            pts_tokens = [pt for pt in tokens if pt['x_pct'] > 65 and abs(pt['y_pct'] - (y_ref)) < 5]
            pts = "".join(filter(str.isdigit, "".join([p['text'] for p in pts_tokens])))

            players.append({
                "name": clean_nick or "Jogador",
                "member_id": m_id,
                "points": pts or "0",
                "y": y_ref
            })

    players.sort(key=lambda p: p['y'])
    return {"players": players}
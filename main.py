from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import pytesseract
import re

app = FastAPI()

# Configuração de CORS para permitir que seu site local acesse a API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Regex para detectar o ID de 10 dígitos ou GUEST
MEMBER_RE = re.compile(r"\b(\d{10}|GUEST\d{3,})\b", re.IGNORECASE)

@app.post("/process")
async def process_ocr(file: UploadFile = File(...)):
    # Lendo a imagem enviada
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Pré-processamento básico para o Tesseract
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
    
    h_img, w_img = gray.shape
    tokens = []
    
    # Extraindo todos os blocos de texto com suas coordenadas
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        if text:
            tokens.append({
                "text": text,
                "x_pct": (data['left'][i] / w_img) * 100,
                "y_pct": (data['top'][i] / h_img) * 100
            })

    players = []
    
    # Identificando jogadores baseados no Member ID
    for t in tokens:
        match = MEMBER_RE.search(t['text'])
        if match:
            m_id = match.group(1)
            y_ref = t['y_pct']
            
            # 1. Captura o Nickname (tokens à esquerda do ID e na mesma altura)
            nick_tokens = [nt for nt in tokens if 14 < nt['x_pct'] < 65 and abs(nt['y_pct'] - (y_ref - 2.5)) < 4]
            nick_tokens.sort(key=lambda x: x['x_pct'])
            
            raw_nick = " ".join([nt['text'] for nt in nick_tokens if not MEMBER_RE.search(nt['text'])])
            
            # LIMPEZA DO NOME: Remove termos fixos do layout da Bandai que o Tesseract lê por engano
            clean_nick = re.sub(r'\b(Member|Number|Henrique|Teixeira)\b', '', raw_nick, flags=re.IGNORECASE).strip()

            # 2. Captura os Pontos (tokens à direita do ID)
            pts_tokens = [pt for pt in tokens if pt['x_pct'] > 65 and abs(pt['y_pct'] - (y_ref - 2.5)) < 4]
            pts_text = "".join([p['text'] for p in pts_tokens])
            pts = "".join(filter(str.isdigit, pts_text)) # Mantém apenas números

            players.append({
                "name": clean_nick or "Não identificado",
                "member_id": m_id,
                "points": pts or "0",
                "y": y_ref
            })

    # Ordena os jogadores pela posição vertical na tela (Rank)
    players.sort(key=lambda p: p['y'])
    
    return {"players": players}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
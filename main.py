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

# Regex flexível para IDs de 10 dígitos ou GUEST
MEMBER_RE = re.compile(r"(\d{10}|GUEST\d+)", re.IGNORECASE)

@app.post("/process")
async def process_ocr(file: UploadFile = File(...)):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Conversão para escala de cinza e redimensionamento para melhorar precisão em celular
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    
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
        # Pula textos muito no topo ou rodapé (áreas de sistema do celular)
        if t['y_pct'] < 10 or t['y_pct'] > 90:
            continue

        match = MEMBER_RE.search(t['text'])
        if match:
            m_id = match.group(1)
            y_ref = t['y_pct']
            
            # Captura o Nickname (procura tokens na mesma linha y_ref)
            # A margem de altura (y) foi aumentada para 6% para compensar inclinações no print
            nick_tokens = [nt for nt in tokens if 10 < nt['x_pct'] < 70 and abs(nt['y_pct'] - (y_ref - 2.5)) < 6]
            nick_tokens.sort(key=lambda x: x['x_pct'])
            
            raw_nick = " ".join([nt['text'] for nt in nick_tokens])
            
            # Limpeza total de palavras do sistema
            clean_nick = re.sub(r'\b(Member|Number|Ranking|User|Name|Win|Points|OMW|Ranking|ng)\b', '', raw_nick, flags=re.IGNORECASE).strip()

            # Captura Pontos (tokens à direita do ID na mesma linha)
            pts_tokens = [pt for pt in tokens if pt['x_pct'] > 65 and abs(pt['y_pct'] - y_ref) < 6]
            pts = "".join(filter(str.isdigit, "".join([p['text'] for p in pts_tokens])))

            players.append({
                "name": clean_nick or "Jogador Desconhecido",
                "member_id": m_id,
                "points": pts or "0",
                "y": y_ref
            })

    # Remove duplicatas internas do mesmo print e ordena por Rank vertical
    vistos = set()
    players_unicos = []
    for p in sorted(players, key=lambda x: x['y']):
        if p['member_id'] not in vistos:
            vistos.add(p['member_id'])
            players_unicos.append(p)
            
    return {"players": players_unicos}
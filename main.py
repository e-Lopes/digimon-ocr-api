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

MEMBER_RE = re.compile(r"(\d{10}|GUEST\d+)", re.IGNORECASE)
OMW_RE    = re.compile(r"(\d{1,3}[.,]\d)%?")

# ---------------------------------------------------------------------------
# Pre-processing
# ---------------------------------------------------------------------------

def _preprocess(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    orig_h, orig_w = gray.shape

    crop_top    = 0
    crop_bottom = orig_h

    if orig_h > orig_w:  # portrait phone screenshot
        top_search   = gray[:int(orig_h * 0.50), :]
        _, bw        = cv2.threshold(top_search, 110, 255, cv2.THRESH_BINARY_INV)
        row_darkness = bw.mean(axis=1)
        dark_rows    = np.where(row_darkness > 25)[0]
        crop_top     = max(0, int(dark_rows[0]) - 5) if len(dark_rows) > 0 else int(orig_h * 0.12)
        crop_bottom  = int(orig_h * 0.87)

    gray = gray[crop_top:crop_bottom, :]
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    gray = cv2.medianBlur(gray, 3)
    gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10)
    return gray


def _get_tokens(gray: np.ndarray) -> list:
    data = pytesseract.image_to_data(gray, config=r"--oem 3 --psm 6", output_type=pytesseract.Output.DICT)
    h, w = gray.shape
    tokens = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])
        if text and conf > 25:
            tokens.append({
                "text":  text,
                "x_pct": (data["left"][i] / w) * 100,
                "y_pct": (data["top"][i]  / h) * 100,
            })
    return tokens


def _near(tokens, y_ref, x_min=None, x_max=None, y_tol=3.0):
    return sorted(
        [t for t in tokens
         if abs(t["y_pct"] - y_ref) < y_tol
         and (x_min is None or t["x_pct"] >= x_min)
         and (x_max is None or t["x_pct"] <= x_max)],
        key=lambda t: t["x_pct"]
    )


def _find_points(tokens, y_ref):
    """Win Points: 1-3 digit integer, column x 55-76%."""
    for t in _near(tokens, y_ref, x_min=55, x_max=76, y_tol=3.0):
        d = re.sub(r"[^\d]", "", t["text"])
        if d and re.match(r"^\d{1,3}$", d):
            return d
    return ""


def _find_omw(tokens, y_ref):
    """OMW%: pattern like 47.1%, column x > 70%."""
    for t in _near(tokens, y_ref, x_min=70, y_tol=3.5):
        m = OMW_RE.search(t["text"].replace(",", "."))
        if m:
            val = m.group(1).replace(",", ".")
            try:
                if 0 <= float(val) <= 100:
                    return val
            except ValueError:
                pass
    return ""


# ---------------------------------------------------------------------------
# Main parse — prioridade: member_id > points > omw
# ---------------------------------------------------------------------------

def parse_image(img: np.ndarray) -> list:
    processed = _preprocess(img)
    tokens    = _get_tokens(processed)

    players  = []
    seen_ids = set()

    for t in tokens:
        match = MEMBER_RE.search(t["text"])
        if not match:
            continue

        m_id = match.group(1).upper()
        if m_id in seen_ids:
            continue
        seen_ids.add(m_id)

        y_ref  = t["y_pct"]
        points = _find_points(tokens, y_ref)
        omw    = _find_omw(tokens, y_ref)

        players.append({
            "member_id": m_id,
            "points":    points,
            "omw":       omw,
            "y":         y_ref,
        })

    # Sort by vertical position = ranking order on screen
    players.sort(key=lambda p: p["y"])

    # Rank = position in this sorted list (autopreenchido)
    for i, p in enumerate(players):
        p["rank"] = i + 1
        p.pop("y", None)

    return players


@app.post("/process")
async def process_ocr(file: UploadFile = File(...)):
    contents = await file.read()
    nparr    = np.frombuffer(contents, np.uint8)
    img      = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {"players": [], "error": "Não foi possível decodificar a imagem."}

    return {"players": parse_image(img)}
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

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
MEMBER_RE  = re.compile(r"(\d{10}|GUEST\d+)", re.IGNORECASE)
RANK_RE    = re.compile(r"^\d{1,3}$")
POINTS_RE  = re.compile(r"^\d{1,3}$")
OMW_RE     = re.compile(r"(\d{1,3}[\.,]\d)%?")   # 66.6%  or  66,6


# ---------------------------------------------------------------------------
# Image pre-processing helpers
# ---------------------------------------------------------------------------

def _to_gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _crop_content_area(gray: np.ndarray) -> np.ndarray:
    """
    Remove status bar (top ~8%) and bottom nav bar (bottom ~15%) that are
    common in full-screen Android screenshots.  Uses a heuristic: if the
    image is taller than it is wide (portrait phone screenshot) we crop.
    """
    h, w = gray.shape
    if h > w:                        # portrait → likely a phone screenshot
        top    = int(h * 0.08)       # skip status bar
        bottom = int(h * 0.88)       # skip bottom nav  (keeps ~80 % of height)
        return gray[top:bottom, :]
    return gray


def _preprocess(img: np.ndarray) -> np.ndarray:
    gray = _to_gray(img)
    gray = _crop_content_area(gray)
    # Upscale for better OCR
    gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    # Mild denoise
    gray = cv2.medianBlur(gray, 3)
    # Adaptive threshold makes text pop on any background colour
    gray = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 10
    )
    return gray


# ---------------------------------------------------------------------------
# Token extraction via Tesseract
# ---------------------------------------------------------------------------

def _get_tokens(gray: np.ndarray) -> list[dict]:
    """Return list of {text, x_pct, y_pct, w_pct, h_pct, conf}."""
    cfg = r"--oem 3 --psm 6"
    data = pytesseract.image_to_data(gray, config=cfg, output_type=pytesseract.Output.DICT)
    h_img, w_img = gray.shape
    tokens = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])
        if text and conf > 20:        # discard very low-confidence noise
            tokens.append({
                "text":  text,
                "x_pct": (data["left"][i] / w_img) * 100,
                "y_pct": (data["top"][i] / h_img) * 100,
                "w_pct": (data["width"][i] / w_img) * 100,
                "conf":  conf,
            })
    return tokens


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

STOP_WORDS = re.compile(
    r"\b(Member|Number|Ranking|User|Name|Win|Points|OMW|ng|Ranki)\b",
    re.IGNORECASE,
)

def _tokens_near_y(tokens, y_ref, x_min=None, x_max=None, y_tol=3.5):
    result = [
        t for t in tokens
        if abs(t["y_pct"] - y_ref) < y_tol
        and (x_min is None or t["x_pct"] >= x_min)
        and (x_max is None or t["x_pct"] <= x_max)
    ]
    return sorted(result, key=lambda t: t["x_pct"])


def _build_name(tokens, y_ref, y_tol=4.0):
    """
    Name lives in the 2nd column (roughly x 15-75 %).
    It appears on the SAME row as the rank badge or one row above the member id.
    We search a small y window above y_ref (member-id row) and at y_ref itself.
    """
    candidates = [
        t for t in tokens
        if 12 < t["x_pct"] < 78
        and (abs(t["y_pct"] - y_ref) < y_tol or abs(t["y_pct"] - (y_ref - 4)) < y_tol)
    ]
    candidates.sort(key=lambda t: t["x_pct"])
    raw = " ".join(t["text"] for t in candidates)
    clean = STOP_WORDS.sub("", raw)
    # Remove digit-only tokens and stray %
    clean = re.sub(r"\b\d+[\.,]?\d*%?\b", "", clean)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    return clean or "Desconhecido"


def _find_omw(tokens, y_ref, y_tol=4.0):
    """OMW% column is roughly x > 70%."""
    candidates = _tokens_near_y(tokens, y_ref, x_min=68, y_tol=y_tol)
    for t in candidates:
        m = OMW_RE.search(t["text"].replace(",", "."))
        if m:
            return m.group(1).replace(",", ".")
    return ""


def _find_points(tokens, y_ref, y_tol=4.0):
    """Win Points column is roughly x 58-72%."""
    candidates = _tokens_near_y(tokens, y_ref, x_min=52, x_max=72, y_tol=y_tol)
    for t in candidates:
        cleaned = re.sub(r"[^\d]", "", t["text"])
        if cleaned and POINTS_RE.match(cleaned):
            return cleaned
    return "0"


def _find_rank(tokens, y_ref, y_tol=4.5):
    """Rank badge is in leftmost column, x < 15%."""
    candidates = _tokens_near_y(tokens, y_ref, x_min=0, x_max=15, y_tol=y_tol)
    for t in sorted(candidates, key=lambda t: abs(t["y_pct"] - y_ref)):
        cleaned = re.sub(r"[^\d]", "", t["text"])
        if cleaned and RANK_RE.match(cleaned):
            return int(cleaned)
    return None


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse_image(img: np.ndarray) -> list[dict]:
    processed = _preprocess(img)
    tokens = _get_tokens(processed)

    players = []
    seen_ids = set()

    for t in tokens:
        match = MEMBER_RE.search(t["text"])
        if not match:
            continue

        m_id  = match.group(1)
        y_ref = t["y_pct"]

        if m_id in seen_ids:
            continue
        seen_ids.add(m_id)

        rank   = _find_rank(tokens, y_ref)
        name   = _build_name(tokens, y_ref)
        points = _find_points(tokens, y_ref)
        omw    = _find_omw(tokens, y_ref)

        players.append({
            "rank":      rank,
            "name":      name,
            "member_id": m_id,
            "points":    points,
            "omw":       omw,
            "y":         y_ref,        # used for ordering, not returned to client
        })

    # Sort by rank (if found) then by vertical position
    players.sort(key=lambda p: (p["rank"] if p["rank"] is not None else 9999, p["y"]))

    # Remove internal key before returning
    for p in players:
        p.pop("y", None)

    return players


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/process")
async def process_ocr(file: UploadFile = File(...)):
    """
    Process a single screenshot and return the players found.
    The frontend is responsible for merging multiple prints (dedup by member_id).
    """
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {"players": [], "error": "Não foi possível decodificar a imagem."}

    players = parse_image(img)
    return {"players": players}
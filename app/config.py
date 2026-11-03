"""Paths, ports, model profiles, and region. Edit this file to change models."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Internal disk holds what must work with the external drive unplugged:
# the default chat model, the helper models, and the index (it stores passage text).
MODELS = ROOT / "models"
# ./data (often a link to an external drive) holds archives, PDFs, and extra models.
DATA = ROOT / "data"
DATA_MODELS = DATA / "models"
ZIM_DIR = ROOT / "library" / "zim"
PDF_DIR = ROOT / "library" / "pdf"
DB_PATH = ROOT / "index" / "index.sqlite"


def model_path(name):
    """Find a model file on the internal disk first, then on the external drive."""
    for d in (MODELS, DATA_MODELS):
        if (d / name).exists():
            return d / name
    return MODELS / name


def data_online():
    return DATA.exists() and ZIM_DIR.exists()


def _region():
    """region.json (yours, not in git) names your area, its hazards, and its local PDFs."""
    p = ROOT / "region.json"
    r = json.loads(p.read_text()) if p.exists() else {}
    return {"name": "", "short": "", "hazards": "", "test_question": None, "pdfs": [], **r}


REGION = _region()


def pdf_items():
    """Every PDF to fetch and index: the shared list plus the region's local guides."""
    p = ROOT / "sources_pdf.json"
    items = json.loads(p.read_text())["items"] if p.exists() else []
    out = []
    for it in items + REGION["pdfs"]:
        it = dict(it)
        it.setdefault("group", "4-pdf")
        it.setdefault("dest", f"library/pdf/{it['id']}.pdf")
        out.append(it)
    return out
LOGS = ROOT / "logs"
LLAMA = ROOT / "bin" / "llama-server"

HOST = "127.0.0.1"          # laptop only. Never bind 0.0.0.0 without a password.
APP_PORT = 9110
CHAT_PORT = 9120
EMBED_PORT = 9121
RERANK_PORT = 9122

EMBED_MODEL = MODELS / "Qwen3-Embedding-0.6B-Q8_0.gguf"
EMBED_DIM = 1024
RERANK_MODEL = MODELS / "bge-reranker-v2-m3-Q8_0.gguf"
QUERY_INSTRUCT = "Instruct: Given a practical question, retrieve passages that answer it\nQuery: "

# Chat models. 'ctx' is the context window. Bigger costs memory, not speed.
PROFILES = {
    "battery": {
        "label": "Battery saver: Qwen3.6 35B-A3B (fast, low power)",
        "file": "Qwen3.6-35B-A3B-UD-Q6_K.gguf", "ctx": 32768,
    },
    "best": {
        "label": "Best answers: Qwen3.8 27B (slower, more careful)",
        "file": "Qwen3.8-27B-Q8_0.gguf", "ctx": 32768,
    },
    "tiny": {
        "label": "Emergency low power: Gemma 4 E4B (small, least accurate)",
        "file": "gemma-4-E4B_q4_0-it.gguf", "ctx": 16384,
    },
}
DEFAULT_PROFILE = "battery"

# Retrieval
TOP_K_VEC = 60
TOP_K_FTS = 60
TOP_K_WIKI = 6          # articles pulled live from the full Wikipedia archive
RERANK_POOL = 48
FINAL_PASSAGES = 8

"""Hybrid retrieval: keyword (FTS5) + meaning (1-bit vectors) + live Wikipedia, then rerank."""
import re, threading, time

from . import config as C
from . import index as I
from . import library as L
from . import llm
from .embedder import pack_bits

_local = threading.local()


def db():
    if not hasattr(_local, "db"):
        _local.db = I.connect()
    return _local.db


# Everyday words -> the words the library uses. Added to the keyword and vector search only;
# the reranker still judges passages against the question as asked.
EXPAND = [
    (r"\bsmall engines?\b", "lawn mower chainsaw generator carburetor two-stroke"),
    (r"\bepi-?pens?\b", "epinephrine auto-injector anaphylaxis"),
    (r"\bheart attack\b", "myocardial infarction chest pain"),
    (r"\bheat ?stroke\b", "hyperthermia heat illness"),
    (r"\bnose ?bleeds?\b", "epistaxis"),
    (r"\bpoison (oak|ivy|sumac)\b", "urushiol rash"),
    (r"\b(boil|boiled) water (notice|advisory)\b", "drinking water disinfection"),
    (r"\bpower (outage|cut|is out)\b", "blackout generator refrigerator food safety"),
]


def expand(q):
    extra = [words for pat, words in EXPAND if re.search(pat, q, re.I)]
    return " ".join([q, *extra])


def _fts_query(q):
    words = [w for w in re.findall(r"[A-Za-z0-9]+", q.lower()) if w not in L.STOP and len(w) > 1]
    return " OR ".join(f'"{w}"' for w in words[:24])


def _rows(ids):
    if not ids:
        return {}
    qs = ",".join("?" * len(ids))
    sql = f"""SELECT c.id, c.doc_id, c.ord, c.section, c.page, d.path, d.title, s.key, s.title, s.kind, f.body
              FROM chunks c JOIN docs d ON d.id=c.doc_id JOIN sources s ON s.id=d.source_id
              JOIN fts f ON f.rowid=c.id WHERE c.id IN ({qs})"""
    out = {}
    for r in db().execute(sql, ids):
        out[r[0]] = {"chunk_id": r[0], "doc_id": r[1], "ord": r[2], "section": r[3], "page": r[4],
                     "path": r[5], "title": r[6], "source": r[7], "source_title": r[8],
                     "kind": r[9], "text": r[10]}
    return out


def neighbors(p, n=1):
    """Add the passages just before and after, so steps are not cut in half."""
    if not p.get("chunk_id"):
        return p["text"]
    rows = db().execute("""SELECT f.body FROM chunks c JOIN fts f ON f.rowid=c.id
                           WHERE c.doc_id=? AND c.ord BETWEEN ? AND ? ORDER BY c.ord""",
                        (p["doc_id"], p["ord"] - n, p["ord"] + n)).fetchall()
    return "\n".join(r[0] for r in rows)


def search(question, final=C.FINAL_PASSAGES):
    t = {}
    t0 = time.time()
    cands = {}
    wide = expand(question)
    fq = _fts_query(wide)
    if fq:
        for (cid,) in db().execute("SELECT rowid FROM fts WHERE fts MATCH ? ORDER BY bm25(fts, 4.0, 2.0, 1.0) LIMIT ?",
                                   (fq, C.TOP_K_FTS)):
            cands.setdefault(cid, 0)
    t["fts"] = time.time() - t0
    t1 = time.time()
    try:
        qv = pack_bits(llm.embed([wide], query=True)[0])
        for cid, dist in db().execute("SELECT rowid, distance FROM vec WHERE emb MATCH vec_bit(?) AND k=?",
                                      (qv, C.TOP_K_VEC)):
            cands.setdefault(cid, 0)
    except Exception as e:
        print("vector search unavailable:", e)
    t["vec"] = time.time() - t1
    pool = list(_rows(list(cands)).values())
    t2 = time.time()
    if L.live_books():
        pool += L.search_live(question)
    t["wiki"] = time.time() - t2
    # dedupe near-identical text
    seen, uniq = set(), []
    for p in pool:
        k = p["text"][:200]
        if k not in seen:
            seen.add(k); uniq.append(p)
    t3 = time.time()
    try:
        scores = llm.rerank(question, [f"{p['title']} — {p['section']}\n{p['text']}" for p in uniq])
    except Exception as e:
        print("rerank unavailable:", e)
        scores = {i: -i for i in range(len(uniq))}
    t["rerank"] = time.time() - t3
    ranked = sorted(range(len(uniq)), key=lambda i: -scores.get(i, -99))
    out, per_doc = [], {}
    for i in ranked:
        p = uniq[i]
        d = (p["source"], p["path"])
        if per_doc.get(d, 0) >= 2:            # at most two passages from one page
            continue
        per_doc[d] = per_doc.get(d, 0) + 1
        p["score"] = round(scores.get(i, 0), 3)
        out.append(p)
        if len(out) >= final:
            break
    for p in out:
        p["context"] = neighbors(p)
        p["link"] = link(p)
    t["total"] = time.time() - t0
    return out, {k: round(v, 3) for k, v in t.items()}, len(uniq)


def link(p):
    if p.get("kind") == "pdf" or (p["source"] == "pdf:manuals"):
        return f"/pdf/{p['path']}" + (f"#page={p['page']}" if p.get("page") else "")
    url = f"/zim/{p['source']}/{p['path']}"
    return url + (f"#page={p['page']}" if p.get("page") else "")

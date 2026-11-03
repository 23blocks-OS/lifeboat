"""Lifeboat web server: chat UI, model load/unload, retrieval, and the offline library reader."""
import json, re, subprocess, threading, time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config as C
from . import household as H
from . import library as L
from . import llm
from . import retrieve as R

app = FastAPI(title="Lifeboat", docs_url=None, redoc_url=None, openapi_url=None)
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

state = {"loading": None, "error": None}

_R = C.REGION
_WHERE = (f" The user is in {_R['name']}." if _R["name"] else "") + \
         (f" Main local hazards: {_R['hazards']}." if _R["hazards"] else "")
SYSTEM = """You are Lifeboat, an offline emergency assistant. The power grid, internet, phones and
emergency services may be down.""" + _WHERE + """

Rules:
1. Answer from the numbered SOURCES below. Cite every factual claim like [1] or [2][5].
2. If the sources do not cover something, say "My sources don't cover this" and then give only
   general, clearly labeled common knowledge. Never invent doses, dilutions, wire sizes, torque
   values, or plant identifications. Copy any number exactly from a source and cite it.
3. Lead with what to do now, as short numbered steps. Then explain. Keep it plain and calm.
4. Safety: for medical problems, name the danger signs that mean the person needs a higher level of
   care if any can be reached. For wild plants and mushrooms, say a positive identification by an
   expert is required and name deadly look-alikes. For electrical work, generators, fuel, stoves
   and heaters, warn about shock, fire and carbon monoxide.
5. If sources disagree, say so and prefer military medical, government, or Hesperian sources.
6. Be honest about uncertainty. A wrong confident answer can kill someone."""

HOUSEHOLD_RULES = """
7. Tailor the answer to the HOUSEHOLD below. If the question names a person, or says "my son",
   "my wife", and so on, match it to the household and use that person's age, weight, conditions,
   and medicines. If you can't tell who it is about, ask.
8. Check every treatment, medicine, and food you suggest against the allergies, conditions, and
   daily medicines of the person involved. Put any conflict first, in bold. If the sources don't
   say whether it is safe with their condition or medicine, say so.
9. For children, pregnancy, and older adults, give only doses the sources state for that age or
   weight, and show the arithmetic with their weight. Never scale an adult dose yourself.
10. Point out supplies on hand and training in the household that help (for example, an
    epinephrine auto-injector, or a member trained in CPR)."""


def _battery():
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=3).stdout
        pct = re.search(r"(\d+)%", out)
        return {"percent": int(pct.group(1)) if pct else None,
                "on_ac": "AC Power" in out, "status": out.splitlines()[-1].split(";", 1)[-1].strip()}
    except Exception:
        return {}


def _model_gb(name):
    # The weights are memory-mapped into the GPU, so ps undercounts. File size is the honest figure.
    p = C.model_path(name) if name else None
    return round(p.stat().st_size / 1e9, 1) if p and p.exists() else None


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    pid = llm.running_pid("chat")
    loaded = llm.loaded_chat_model() if pid else None
    profiles = [{"id": k, "label": v["label"], "available": C.model_path(v["file"]).exists(),
                 "loaded": loaded == v["file"]} for k, v in C.PROFILES.items()]
    try:
        db = R.db()
        idx = db.execute("SELECT count(*), coalesce(sum(n_chunks),0), coalesce(sum(n_vec),0) FROM sources WHERE done=1").fetchone()
    except Exception:
        idx = (0, 0, 0)
    return {"chat_loaded": bool(pid), "chat_model": loaded, "chat_mem_gb": _model_gb(loaded),
            "loading": state["loading"], "error": state["error"], "profiles": profiles,
            "helpers": {"embed": bool(llm.running_pid("embed")), "rerank": bool(llm.running_pid("rerank"))},
            "battery": _battery(), "drive_online": C.data_online(), "live_books": L.live_books(),
            "index": {"sources": idx[0], "passages": idx[1], "vectors": idx[2]},
            "household": len(hh["people"]) if (hh := H.load()) else None}


@app.post("/api/load")
async def load(req: Request):
    body = await req.json()
    profile = body.get("profile", C.DEFAULT_PROFILE)
    if profile not in C.PROFILES:
        raise HTTPException(400, "unknown profile")
    if state["loading"]:
        return {"ok": False, "msg": "already loading"}

    def run():
        state.update(loading=profile, error=None)
        try:
            llm.start_helpers()
            llm.start_chat(profile)
        except Exception as e:
            state["error"] = str(e)
        finally:
            state["loading"] = None
    threading.Thread(target=run, daemon=True).start()
    return {"ok": True}


@app.post("/api/unload")
def unload():
    return {"ok": llm.stop("chat")}


@app.get("/api/search")
def search(q: str):
    passages, timing, pool = R.search(q)
    return {"passages": [_public(p) for p in passages], "timing": timing, "pool": pool}


def _public(p):
    return {k: p.get(k) for k in ("title", "section", "source", "source_title", "page", "link", "score", "context")}


def _query_for(messages):
    users = [m["content"] for m in messages if m["role"] == "user"]
    q = users[-1]
    if len(q.split()) < 7 and len(users) > 1:      # short follow-up: carry the earlier topic
        q = users[-2] + " " + q
    return q


@app.post("/api/chat")
async def chat(req: Request):
    body = await req.json()
    messages = body["messages"][-8:]
    think = bool(body.get("think"))

    def gen():
        t0 = time.time()
        q = (_query_for(messages) + " " + H.search_hint(messages[-1]["content"])).strip()
        passages, timing, pool = R.search(q)
        yield _sse("sources", {"passages": [_public(p) for p in passages], "timing": timing, "pool": pool})
        if not llm.running_pid("chat"):
            yield _sse("error", {"msg": "No chat model loaded. Showing library results only."})
            yield _sse("done", {}); return
        src = "\n\n".join(
            f"[{i}] {p['title']} — {p['section'] or ''} ({p['source_title']}"
            + (f", page {p['page']}" if p.get("page") else "") + f")\n{p['context'][:3500]}"
            for i, p in enumerate(passages, 1))
        hh = H.prompt()
        system = SYSTEM + (HOUSEHOLD_RULES + "\n\n" + hh if hh else "")
        msgs = [{"role": "system", "content": system + "\n\nSOURCES:\n\n" + src}]
        msgs += [{"role": m["role"], "content": m["content"]} for m in messages]
        n, t1 = 0, time.time()
        try:
            for kind, piece in llm.chat_stream(msgs, think=think):
                n += 1
                yield _sse(kind, {"t": piece})
        except Exception as e:
            yield _sse("error", {"msg": f"chat model error: {e}"})
        dt = time.time() - t1
        yield _sse("done", {"tokens": n, "tok_s": round(n / dt, 1) if dt else None,
                            "seconds": round(time.time() - t0, 1), "retrieval": timing})
    return StreamingResponse(gen(), media_type="text/event-stream")


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/api/household")
def household_get():
    return H.load() or {}


@app.put("/api/household")
async def household_put(req: Request):
    return H.save(await req.json())


@app.get("/zim/{book}/{path:path}")
def zim(book: str, path: str):
    got = L.get(book, path)
    if got is None:
        if not C.data_online():
            raise HTTPException(503, "The external drive (Data) is not connected. Plug it in to open full articles.")
        raise HTTPException(404, "not found")
    content, mime = got
    return Response(content, media_type=mime)


@app.get("/pdf/{name}")
def pdf(name: str):
    p = (C.PDF_DIR / name).resolve()
    if p.parent != C.PDF_DIR.resolve() or not p.exists():
        raise HTTPException(404 if C.data_online() else 503, "PDF not available")
    return FileResponse(p, media_type="application/pdf")


@app.get("/api/sources")
def sources():
    rows = R.db().execute("SELECT key,title,kind,license,n_docs,n_chunks,n_vec,done FROM sources ORDER BY id").fetchall()
    return [dict(zip(("key", "title", "kind", "license", "docs", "passages", "vectors", "done"), r)) for r in rows]

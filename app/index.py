"""Build index/index.sqlite from library/zim and library/pdf.

  .venv/bin/python -m app.index                         # embed on this laptop
  .venv/bin/python -m app.index --embed ssh:user@gpu-box   # setup: embed on a helper GPU machine
  .venv/bin/python -m app.index --only ifixit_en_all_2025-12 --force

Every passage goes into the keyword index (FTS5). Passages are also embedded (1-bit vectors,
sqlite-vec) for meaning search. A source is indexed in one transaction-ish pass; if the run
stops, that source is redone from scratch next time. Finished sources are skipped.
The full Wikipedia archive is not indexed here; it is searched live through its own index.
"""
import argparse, json, logging, multiprocessing as mp, sqlite3, sys, time
from collections import deque
from pathlib import Path

import sqlite_vec

from . import config as C
from . import extract as X

logging.getLogger("pypdf").setLevel(logging.ERROR)

# Indexed first = usable first.
PRIORITY = ["pdf:", "zimgit-", "wikipedia_en_medicine", "medicalsciences", "appropedia",
            "energypedia", "ifixit", "outdoors", "mechanics", "ham.", "sustainability",
            "gardening", "cooking", "diy.", "electronics", "wikibooks"]
SKIP_LIVE = ("wikipedia_en_all",)       # searched live, too big to index
EMBED_BATCH = 64
BLOCK = 400                             # ZIM entries per worker task


def connect(path=C.DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=60, check_same_thread=False)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.executescript(f"""
      PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;
      CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY, key TEXT UNIQUE, title TEXT,
        kind TEXT, file TEXT, bytes INT, license TEXT, n_docs INT DEFAULT 0, n_chunks INT DEFAULT 0,
        n_vec INT DEFAULT 0, done INT DEFAULT 0, indexed_at TEXT);
      CREATE TABLE IF NOT EXISTS docs(id INTEGER PRIMARY KEY, source_id INT, path TEXT, title TEXT);
      CREATE INDEX IF NOT EXISTS docs_src ON docs(source_id);
      CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, doc_id INT, ord INT, section TEXT, page INT);
      CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc_id, ord);
      CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(title, section, body,
        tokenize='porter unicode61 remove_diacritics 2');
      CREATE VIRTUAL TABLE IF NOT EXISTS vec USING vec0(emb bit[{C.EMBED_DIM}]);
    """)
    return db


# ---------- extraction workers (run in separate processes) ----------

_arch, _titles, _se = None, {}, False


def _init(zim_path):
    global _arch, _titles, _se
    from libzim.reader import Archive
    _arch = Archive(zim_path)
    _se = "stackexchange" in Path(zim_path).name
    try:
        js = bytes(_arch.get_entry_by_path("database.js").get_item().content).decode("utf-8", "replace")
        _titles = X.nautilus_titles(js)
    except Exception:
        _titles = {}


def _extract_block(rng):
    out = []
    for i in range(*rng):
        try:
            e = _arch.get_entry_by_id(i)
            if e.is_redirect:
                continue
            it = e.get_item()
            mt = it.mimetype
            if mt.startswith("text/html"):
                if _se and not X.is_se_question(e.path):
                    continue
                html = bytes(it.content).decode("utf-8", "replace")
                secs = X.stackexchange(html) if _se else X.html_page(html)
                chunks = [(s, t, None) for s, t in X.chunk(secs)]
                title = e.title
            elif mt == "application/pdf":
                data = bytes(it.content)
                title, author = _titles.get(e.path, (None, ""))
                title = title or X.pdf_title(data, Path(e.path).stem)
                chunks = [(f"Page {p}", t, p) for p, txt in X.pdf_pages(data)
                          for _, t in X.chunk([("", txt)])]
            else:
                continue
            if chunks and sum(len(c[1]) for c in chunks) > 200:
                out.append((e.path, title, chunks))
        except Exception as ex:                    # one bad page must not stop the run
            print(f"  skip entry {i}: {ex}", file=sys.stderr)
    return out


def _extract_pdf(arg):
    path, title = arg
    data = Path(path).read_bytes()
    title = title or X.pdf_title(data, Path(path).stem)
    chunks = [(f"Page {p}", t, p) for p, txt in X.pdf_pages(data) for _, t in X.chunk([("", txt)])]
    return [(Path(path).name, title, chunks)] if chunks else []


# ---------- main loop ----------

def list_sources():
    meta = {}
    for it in json.loads((C.ROOT / "sources.json").read_text())["items"] + C.pdf_items():
        meta[Path(it["dest"]).name] = it
    out = []
    for z in sorted(C.ZIM_DIR.glob("*.zim")):
        if Path(f"{z}.aria2").exists():          # still downloading
            continue
        if not z.name.startswith(SKIP_LIVE):
            out.append(("zim", z.stem, z, meta.get(z.name, {})))
    pdfs = sorted(C.PDF_DIR.glob("*.pdf"))
    if pdfs:
        out.append(("pdf", "pdf:manuals", pdfs, {"title": "Manuals and guides (PDF)", "license": "see MANIFEST.json",
                                                 "titles": {n: m.get("title") for n, m in meta.items()}}))

    def rank(s):
        key = s[1]
        return next((i for i, p in enumerate(PRIORITY) if key.startswith(p)), len(PRIORITY))
    return sorted(out, key=rank)


def zim_title(path):
    from libzim.reader import Archive
    try:
        return Archive(str(path)).get_metadata("Title").decode()
    except Exception:
        return path.stem


def wipe(db, sid):
    ids = "SELECT c.id FROM chunks c JOIN docs d ON c.doc_id=d.id WHERE d.source_id=?"
    db.execute(f"DELETE FROM fts WHERE rowid IN ({ids})", (sid,))
    db.execute(f"DELETE FROM vec WHERE rowid IN ({ids})", (sid,))
    db.execute("DELETE FROM chunks WHERE doc_id IN (SELECT id FROM docs WHERE source_id=?)", (sid,))
    db.execute("DELETE FROM docs WHERE source_id=?", (sid,))


def index_source(db, emb, kind, key, path, meta, workers):
    size = sum(p.stat().st_size for p in path) if kind == "pdf" else path.stat().st_size
    row = db.execute("SELECT id, done, bytes FROM sources WHERE key=?", (key,)).fetchone()
    if row and row[1] and row[2] == size:
        print(f"= {key} (done)"); return
    title = meta.get("title") or (zim_title(path) if kind == "zim" else key)
    if row:
        sid = row[0]; wipe(db, sid)
        db.execute("UPDATE sources SET done=0, bytes=?, title=? WHERE id=?", (size, title, sid))
    else:
        sid = db.execute("INSERT INTO sources(key,title,kind,file,bytes,license) VALUES(?,?,?,?,?,?)",
                         (key, title, kind, "" if kind == "pdf" else path.name, size,
                          meta.get("license", ""))).lastrowid
    db.commit()
    print(f"> {key}: {title}", flush=True)

    if kind == "pdf":
        pool = mp.Pool(workers)
        titles = meta.get("titles", {})
        results = pool.imap(_extract_pdf, [(str(p), titles.get(p.name)) for p in path])
    else:
        from libzim.reader import Archive
        n = Archive(str(path)).entry_count
        pool = mp.Pool(workers, initializer=_init, initargs=(str(path),))
        results = pool.imap(_extract_block, [(i, min(i + BLOCK, n)) for i in range(0, n, BLOCK)])

    t0, n_docs, n_chunks, n_vec = time.time(), 0, 0, 0
    batch_ids, batch_txt, inflight = [], [], deque()

    def flush_embed(final=False):
        nonlocal n_vec
        if batch_ids:
            inflight.append((list(batch_ids), emb.submit(list(batch_txt))))
            batch_ids.clear(); batch_txt.clear()
        while inflight and (final or len(inflight) > 48 or _ready(inflight[0][1])):
            ids, fut = inflight.popleft()
            vecs = fut.result()
            db.executemany("INSERT INTO vec(rowid, emb) VALUES (?, vec_bit(?))", zip(ids, vecs))
            n_vec += len(ids)

    for docs in results:
        for dpath, dtitle, chunks in docs:
            did = db.execute("INSERT INTO docs(source_id,path,title) VALUES(?,?,?)",
                             (sid, dpath, dtitle)).lastrowid
            n_docs += 1
            for o, (sec, text, page) in enumerate(chunks):
                cid = db.execute("INSERT INTO chunks(doc_id,ord,section,page) VALUES(?,?,?,?)",
                                 (did, o, sec, page)).lastrowid
                db.execute("INSERT INTO fts(rowid,title,section,body) VALUES(?,?,?,?)",
                           (cid, dtitle, sec, text))
                n_chunks += 1
                batch_ids.append(cid)
                batch_txt.append(f"{dtitle} — {sec}\n{text}" if sec else f"{dtitle}\n{text}")
                if len(batch_ids) >= EMBED_BATCH:
                    flush_embed()
        if n_docs and n_docs % 2000 < len(docs):
            db.commit()
            rate = n_chunks / max(time.time() - t0, 1)
            print(f"  {n_docs:,} docs  {n_chunks:,} chunks  {n_vec:,} vectors  {rate:,.0f} chunks/s", flush=True)
    flush_embed(final=True)
    pool.close(); pool.join()
    db.execute("UPDATE sources SET n_docs=?, n_chunks=?, n_vec=?, done=1, indexed_at=datetime('now') WHERE id=?",
               (n_docs, n_chunks, n_vec, sid))
    db.commit()
    print(f"  ok {key}: {n_docs:,} docs, {n_chunks:,} chunks in {time.time()-t0:,.0f}s", flush=True)


def _ready(fut):
    done = getattr(fut, "done", None)
    return done() if done else fut.ev.is_set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed", default="local", help="local | ssh:user@host")
    ap.add_argument("--only", nargs="*", help="source keys to (re)index")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=max(mp.cpu_count() - 4, 2))
    a = ap.parse_args()
    sources = list(list_sources())
    if not sources:
        sys.exit("Lifeboat: no archives or PDFs in library/. Run ./lifeboat fetch first.")
    from . import embedder, llm
    if a.embed == "local":
        llm.start_helpers()
    emb = embedder.make(a.embed)
    db = connect()
    for kind, key, path, meta in sources:
        if a.only and key not in a.only:
            continue
        if a.force:
            db.execute("UPDATE sources SET done=0 WHERE key=?", (key,)); db.commit()
        index_source(db, emb, kind, key, path, meta, a.workers)
    emb.close()
    db.execute("INSERT INTO fts(fts) VALUES('optimize')"); db.commit()
    print("INDEX DONE")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        sys.exit(f"Lifeboat: {e}")

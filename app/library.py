"""Read ZIM archives: serve pages, and search the big archives live (Wikipedia)."""
import re, threading
from functools import lru_cache
from pathlib import Path

from . import config as C
from . import extract as X

_lock = threading.Lock()
_open = {}


def archive(key):
    """Open a ZIM by its file stem. Returns None if the drive is unplugged or the file is missing."""
    from libzim.reader import Archive
    with _lock:
        if key not in _open:
            p = C.ZIM_DIR / f"{key}.zim"
            if not p.exists() or Path(f"{p}.aria2").exists():
                return None
            _open[key] = Archive(str(p))
        return _open[key]


def books():
    if not C.ZIM_DIR.exists():
        return []
    return sorted(p.stem for p in C.ZIM_DIR.glob("*.zim") if not Path(f"{p}.aria2").exists())


def live_books():
    return [b for b in books() if b.startswith("wikipedia_en_all")]


def get(key, path):
    a = archive(key)
    if a is None:
        return None
    try:
        e = a.get_entry_by_path(path)
    except KeyError:
        return None
    it = e.get_item()
    return bytes(it.content), it.mimetype


STOP = set("a an and are as at be by can do does for from how i if in is it my of on or should "
           "the to what when where which who why will with without you your me we our this that "
           "there their they than then so".split())


def keywords(q):
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]+", q.lower())
    return " ".join(w for w in words if w not in STOP) or q


def search_live(query, limit=C.TOP_K_WIKI):
    """Full-text search inside Wikipedia's own index. Returns candidate passages."""
    from libzim.search import Query, Searcher
    out = []
    for key in live_books():
        a = archive(key)
        if a is None or not a.has_fulltext_index:
            continue
        try:
            paths = list(Searcher(a).search(Query().set_query(keywords(query))).get_results(0, limit))
        except Exception:
            continue
        for sr in paths:
            path = sr if isinstance(sr, str) else getattr(sr, "path", str(sr))
            out.extend(_article_passages(key, path))
    return out


@lru_cache(maxsize=256)
def _article_passages_cached(key, path):
    a = archive(key)
    e = a.get_entry_by_path(path)
    html = bytes(e.get_item().content).decode("utf-8", "replace")
    title = e.title
    chunks = X.chunk(X.html_page(html))[:12]          # lead + first sections are enough
    return tuple((title, sec, text) for sec, text in chunks)


def _article_passages(key, path):
    try:
        rows = _article_passages_cached(key, path)
    except Exception:
        return []
    return [{"source": key, "source_title": "Wikipedia", "path": path, "title": t,
             "section": s, "text": x, "page": None, "chunk_id": None} for t, s, x in rows]

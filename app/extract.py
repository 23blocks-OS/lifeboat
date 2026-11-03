"""Turn ZIM HTML pages and PDFs into clean text sections, then chunks."""
import ast, io, re

from selectolax.lexbor import LexborHTMLParser

DROP = ("script, style, noscript, nav, header, footer, form, button, svg, "
        ".kiwix-topbar-fill, .s-topbar, .left-sidebar, #sidebar, .sidebar, .navbox, "
        ".mw-references-wrap, .reflist, .references, .mw-editsection, .metadata, "
        ".comments, .post-signature, .js-voting-container, .post-taglist, "
        ".noprint, .hatnote, .catlinks, .mw-jump-link")
BLOCK_CLOSE = re.compile(r"</(p|li|div|tr|pre|blockquote|dd|dt|table|ul|ol|section|figcaption)>", re.I)
CELL_CLOSE = re.compile(r"</(td|th)>", re.I)
HEADING = re.compile(r"<h([1-4])\b[^>]*>", re.I)
BR = re.compile(r"<br\s*/?>", re.I)
SE_QUESTION = re.compile(r"^questions/\d+/")


def _prep(html):
    html = HEADING.sub(lambda m: f"\n\n<h{m.group(1)}>§H ", html)
    html = BLOCK_CLOSE.sub(lambda m: f"\n</{m.group(1)}>", html)
    html = CELL_CLOSE.sub(lambda m: f" | </{m.group(1)}>", html)
    return BR.sub("\n", html)


def _text(node):
    node.strip_tags(["img"]) if hasattr(node, "strip_tags") else None
    return node.text(separator="")


def sections_from_text(raw, default="Overview"):
    """Split text marked with §H heading lines into [(section, text)]."""
    out, cur, buf = [], default, []
    for line in raw.splitlines():
        line = re.sub(r"[ \t ]+", " ", line).strip()
        if not line:
            if buf and buf[-1] != "":
                buf.append("")
            continue
        if line.startswith("§H "):
            if any(buf):
                out.append((cur, "\n".join(buf).strip()))
            cur, buf = line[3:].strip() or default, []
        else:
            buf.append(line)
    if any(buf):
        out.append((cur, "\n".join(buf).strip()))
    return [(s, t) for s, t in out if len(t) > 40]


def stackexchange(html, max_answers=3):
    t = LexborHTMLParser(html)
    q = t.css_first(".question .s-prose") or t.css_first(".question .post-text")
    if not q:
        return []
    secs = [("Question", _clean(q))]
    answers = t.css(".answer")
    answers.sort(key=lambda a: ("accepted-answer" not in (a.attributes.get("class") or ""), 0))
    for i, a in enumerate(answers[:max_answers]):
        body = a.css_first(".s-prose") or a.css_first(".post-text")
        if not body:
            continue
        votes = a.css_first(".js-vote-count")
        v = votes.text(strip=True) if votes else "?"
        tag = "Accepted answer" if "accepted-answer" in (a.attributes.get("class") or "") else "Answer"
        secs.append((f"{tag} ({v} votes)", _clean(body)))
    return [(s, x) for s, x in secs if x]


def _clean(node):
    for n in node.css("script, style"):
        n.decompose()
    raw = LexborHTMLParser(_prep(node.html)).body.text(separator="")
    return "\n".join(t for _, t in sections_from_text(raw, ""))


def html_page(html):
    t = LexborHTMLParser(_prep(html))
    for n in t.css(DROP):
        n.decompose()
    root = (t.css_first("#mw-content-text") or t.css_first("main") or t.css_first("article")
            or t.css_first("#content") or t.body)
    if root is None:
        return []
    return sections_from_text(root.text(separator=""))


def pdf_pages(data):
    """Yield (page_number, text) from PDF bytes. Skips pages with no text layer."""
    from pypdf import PdfReader
    try:
        r = PdfReader(io.BytesIO(data))
    except Exception:
        return
    for i, p in enumerate(r.pages, 1):
        try:
            txt = p.extract_text() or ""
        except Exception:
            continue
        txt = re.sub(r"[ \t]+", " ", txt)
        txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
        if len(txt) > 80:
            yield i, txt


def pdf_title(data, fallback):
    from pypdf import PdfReader
    try:
        t = (PdfReader(io.BytesIO(data)).metadata or {}).get("/Title")
        if t and len(str(t).strip()) > 3:
            return str(t).strip()
    except Exception:
        pass
    return fallback


def nautilus_titles(js_text):
    """zimgit archives list their PDFs in database.js. Map file -> (title, author)."""
    m = re.search(r"=\s*(\[.*\])\s*;?\s*$", js_text, re.S)
    if not m:
        return {}
    try:
        rows = ast.literal_eval(m.group(1))
    except Exception:
        return {}
    out = {}
    for r in rows:
        for fp in r.get("fp", []):
            out["files/" + fp] = (r.get("ti", fp), r.get("aut", ""))
    return out


def chunk(sections, size=1400, overlap=150):
    """Pack [(section, text)] into ~size-char chunks. Never mixes two sections."""
    out = []
    for sec, text in sections:
        paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=[-*•\d]+[.)]?\s)", text) if p.strip()]
        buf = ""
        for p in paras:
            while len(p) > size:                       # very long paragraph: cut on sentences
                cut = p.rfind(". ", 0, size)
                cut = cut + 1 if cut > size // 2 else size
                if buf:
                    out.append((sec, buf)); buf = ""
                out.append((sec, p[:cut].strip()))
                p = p[max(cut - overlap, 0):].strip() if cut == size else p[cut:].strip()
            if len(buf) + len(p) + 1 > size and buf:
                out.append((sec, buf))
                buf = buf[-overlap:].split(" ", 1)[-1] + "\n" + p if overlap else p
            else:
                buf = f"{buf}\n{p}" if buf else p
        if buf.strip():
            out.append((sec, buf.strip()))
    return out


def is_se_question(path):
    return bool(SE_QUESTION.match(path))

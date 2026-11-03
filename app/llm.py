"""Start and stop llama-server processes, and talk to them."""
import json, os, signal, subprocess, time
from pathlib import Path

import httpx

from . import config as C

PIDS = C.ROOT / "logs" / "pids"


def _pidfile(name):
    PIDS.mkdir(parents=True, exist_ok=True)
    return PIDS / f"{name}.pid"


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def running_pid(name):
    f = _pidfile(name)
    if f.exists():
        pid = int(f.read_text().split()[0])
        if _alive(pid):
            return pid
        f.unlink()
    return None


def start(name, model, port, extra, wait=True):
    """Start one llama-server. Returns its pid. No-op if it already runs."""
    if pid := running_pid(name):
        return pid
    if not Path(model).exists():
        raise FileNotFoundError(f"model not on disk: {model}")
    cmd = [str(C.LLAMA), "-m", str(model), "--host", C.HOST, "--port", str(port),
           "--offline", "--no-webui", "-ngl", "999", *extra]
    log = open(C.LOGS / f"{name}.log", "ab")
    p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    _pidfile(name).write_text(f"{p.pid} {Path(model).name}")
    if wait:
        wait_ready(port, p)
    return p.pid


def wait_ready(port, proc=None, timeout=600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(f"llama-server on port {port} exited. See logs/.")
        try:
            if httpx.get(f"http://{C.HOST}:{port}/health", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"llama-server on port {port} did not become ready")


def stop(name):
    pid = running_pid(name)
    if not pid:
        return False
    os.killpg(pid, signal.SIGTERM)
    for _ in range(50):
        if not _alive(pid):
            break
        time.sleep(0.1)
    else:
        os.killpg(pid, signal.SIGKILL)
    _pidfile(name).unlink(missing_ok=True)
    return True


def loaded_chat_model():
    f = _pidfile("chat")
    if running_pid("chat") and f.exists():
        parts = f.read_text().split()
        return parts[1] if len(parts) > 1 else None
    return None


# ---- helper servers (always on while Lifeboat runs) ----

def start_helpers():
    start("embed", C.EMBED_MODEL, C.EMBED_PORT,
          ["--embedding", "--pooling", "last", "-c", "32768", "-np", "16",
           "-b", "8192", "-ub", "8192"])
    start("rerank", C.RERANK_MODEL, C.RERANK_PORT,
          ["--reranking", "-c", "32768", "-np", "8", "-b", "8192", "-ub", "8192"])


def start_chat(profile):
    p = C.PROFILES[profile]
    if loaded_chat_model() and loaded_chat_model() != p["file"]:
        stop("chat")
    return start("chat", C.model_path(p["file"]), C.CHAT_PORT,
                 ["-c", str(p["ctx"]), "-np", "1", "-fa", "on", "--jinja",
                  "--reasoning-format", "deepseek"])


def embed(texts, query=False, client=None):
    if query:
        texts = [C.QUERY_INSTRUCT + t for t in texts]
    texts = [t[:2400] for t in texts]
    cl = client or httpx
    r = cl.post(f"http://{C.HOST}:{C.EMBED_PORT}/v1/embeddings",
                json={"input": texts}, timeout=600)
    r.raise_for_status()
    data = sorted(r.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]


def rerank(query, docs):
    r = httpx.post(f"http://{C.HOST}:{C.RERANK_PORT}/v1/rerank",
                   json={"query": query, "documents": [d[:2000] for d in docs]}, timeout=120)
    r.raise_for_status()
    return {x["index"]: x["relevance_score"] for x in r.json()["results"]}


def chat_stream(messages, think=False, max_tokens=2048):
    """Yield ('reasoning'|'content', text) pieces from the chat model."""
    body = {"messages": messages, "stream": True, "max_tokens": max_tokens,
            "temperature": 0.3, "top_p": 0.9,
            "chat_template_kwargs": {"enable_thinking": bool(think)}}
    with httpx.stream("POST", f"http://{C.HOST}:{C.CHAT_PORT}/v1/chat/completions",
                      json=body, timeout=httpx.Timeout(600, connect=5)) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            delta = json.loads(line[6:])["choices"][0].get("delta", {})
            if delta.get("reasoning_content"):
                yield "reasoning", delta["reasoning_content"]
            if delta.get("content"):
                yield "content", delta["content"]

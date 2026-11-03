#!/usr/bin/env python3
"""Setup-only embedding worker. Runs on a helper GPU machine next to an embedding server
(vLLM or llama-server) on 127.0.0.1:9121.

Talks over ssh stdin/stdout, so it needs no open ports and no TCP forwarding:
  in : one JSON line per batch  {"id": 7, "texts": ["...", ...]}
  out: one JSON line per batch  {"id": 7, "bits": ["<base64 128 bytes>", ...]}
Vectors come back already binary-quantized (1 bit per dim), the form the index stores.
Standard library only.
"""
import array, base64, json, sys, threading, urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = "http://127.0.0.1:9121/v1/embeddings"
lock = threading.Lock()


def pack(vec):
    out = bytearray((len(vec) + 7) // 8)
    for i, x in enumerate(vec):
        if x > 0:
            out[i >> 3] |= 1 << (i & 7)
    return base64.b64encode(bytes(out)).decode()


def _vec(e):
    if isinstance(e, str):                      # base64 float32, much cheaper to parse than JSON
        a = array.array("f"); a.frombytes(base64.b64decode(e)); return a
    return e


def embed(texts, tokens=1024, timeout=120):
    body = json.dumps({"input": texts, "encoding_format": "base64",
                       "truncate_prompt_tokens": tokens}).encode()
    r = urllib.request.urlopen(urllib.request.Request(
        URL, body, {"Content-Type": "application/json"}), timeout=timeout)
    return [pack(_vec(d["embedding"])) for d in sorted(json.load(r)["data"], key=lambda d: d["index"])]


def one(text):
    # A single input can stall the server. Shrink it until it goes through.
    for t, tokens in ((text, 1024), (text[:600], 256)):
        try:
            return embed([t], tokens, timeout=60)[0]
        except Exception:
            pass
    return embed([text[:200]], 64, timeout=60)[0]


def work(line):
    req = json.loads(line)
    try:
        for attempt in range(2):
            try:
                res = {"id": req["id"], "bits": embed(req["texts"])}
                break
            except Exception:
                if attempt:
                    res = {"id": req["id"], "bits": [one(t) for t in req["texts"]]}
    except Exception as e:
        res = {"id": req["id"], "error": str(e)}
    with lock:
        sys.stdout.write(json.dumps(res) + "\n")
        sys.stdout.flush()


with ThreadPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 8) as ex:
    for line in sys.stdin:
        if line.strip():
            ex.submit(work, line)

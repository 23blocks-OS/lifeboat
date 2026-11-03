"""Document embedding for the indexer. Returns 1-bit-per-dim packed vectors (bytes).

backend "local"        : the laptop's own embed server (always works, ~60 chunks/s)
backend "ssh:<host>"   : remote_embed_worker.py on a helper box over ssh stdio (prep only)
"""
import base64, json, queue, subprocess, threading
from concurrent.futures import ThreadPoolExecutor

import httpx

from . import config as C


def pack_bits(vec):
    out = bytearray((len(vec) + 7) // 8)
    for i, x in enumerate(vec):
        if x > 0:
            out[i >> 3] |= 1 << (i & 7)
    return bytes(out)


class LocalEmbedder:
    def __init__(self, threads=4):
        self.cl = httpx.Client(timeout=600, limits=httpx.Limits(max_connections=threads))
        self.pool = ThreadPoolExecutor(threads)

    def submit(self, texts):
        """Returns a future that yields a list of packed vectors."""
        def run():
            r = self.cl.post(f"http://{C.HOST}:{C.EMBED_PORT}/v1/embeddings",
                             json={"input": [t[:2400] for t in texts]})
            r.raise_for_status()
            return [pack_bits(d["embedding"]) for d in sorted(r.json()["data"], key=lambda d: d["index"])]
        return self.pool.submit(run)

    def close(self):
        self.pool.shutdown()


class _Fut:
    def __init__(self):
        self.ev, self.val, self.err = threading.Event(), None, None

    def result(self):
        self.ev.wait()
        if self.err:
            raise RuntimeError(self.err)
        return self.val


class SshEmbedder:
    def __init__(self, host, threads=16):
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", "-T", host,
               f"python3 -u ~/lifeboat-prep/remote_embed_worker.py {threads}"]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.pending, self.next_id, self.lock = {}, 0, threading.Lock()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for line in self.p.stdout:
            msg = json.loads(line)
            f = self.pending.pop(msg["id"])
            if "error" in msg:
                f.err = msg["error"]
            else:
                f.val = [base64.b64decode(b) for b in msg["bits"]]
            f.ev.set()
        for f in list(self.pending.values()):   # ssh died: fail everything still waiting
            f.err = "ssh worker exited"; f.ev.set()

    def submit(self, texts):
        f = _Fut()
        with self.lock:
            i = self.next_id; self.next_id += 1
            self.pending[i] = f
            self.p.stdin.write(json.dumps({"id": i, "texts": [t[:2400] for t in texts]}) + "\n")
        return f

    def close(self):
        try:
            self.p.stdin.close(); self.p.wait(timeout=30)
        except Exception:
            self.p.kill()


def make(backend):
    if backend.startswith("ssh:"):
        return SshEmbedder(backend[4:])
    return LocalEmbedder()

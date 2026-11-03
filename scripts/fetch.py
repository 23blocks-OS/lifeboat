#!/usr/bin/env python3
"""Download everything in sources.json, sources_pdf.json and region.json, check sha256, write MANIFEST.json.

Uses only the standard library plus curl, so it runs before the venv exists.
Safe to re-run: finished files are skipped, partial files resume.

Usage: scripts/fetch.py [group-prefix ...]     e.g.  scripts/fetch.py 1 2
"""
import hashlib, json, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import config as C  # noqa: E402  (standard library only)

MANIFEST = ROOT / "MANIFEST.json"
KIWIX = "https://download.kiwix.org/zim"


def load_items():
    items = json.loads((ROOT / "sources.json").read_text())["items"]
    items += C.pdf_items()
    for it in items:
        if "kiwix" in it:
            name = Path(it["dest"]).name
            it["url"] = f"{KIWIX}/{it['kiwix']}/{name}"
            it["sha256_url"] = it["url"] + ".sha256"
    return items


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(16 << 20):
            h.update(chunk)
    return h.hexdigest()


def expected_sha(it):
    if it.get("sha256"):
        return it["sha256"]
    if it.get("sha256_url"):
        try:
            with urllib.request.urlopen(it["sha256_url"], timeout=30) as r:
                return r.read().decode().split()[0]
        except Exception as e:
            print(f"  ! no checksum file: {e}")
    return None


def main(prefixes):
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    items = sorted(load_items(), key=lambda i: i["group"])
    if prefixes:
        items = [i for i in items if any(i["group"].startswith(p) for p in prefixes)]
    failed, manual = [], []
    for it in items:
        dest = ROOT / it["dest"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        done = manifest.get(it["id"])
        if done and dest.exists() and dest.stat().st_size == done["bytes"]:
            print(f"= {it['id']} (already done)")
            continue
        if it.get("manual") and dest.exists():
            record(manifest, it, dest, dest, False)   # saved by hand
            print(f"= {it['id']} (saved by hand)")
            continue
        want = expected_sha(it)
        part = dest.with_name(dest.name + ".part")
        print(f"> {it['id']}  {it['url']}", flush=True)
        t0 = time.time()
        if it.get("kiwix") and shutil.which("aria2c"):
            # Many connections across all Kiwix mirrors; the metalink checks every 4 MB piece.
            rc = subprocess.call(["aria2c", "--follow-metalink=mem", "--metalink-preferred-protocol=https",
                                  "-x", "8", "-s", "24", "-k", "4M", "--continue=true",
                                  "--file-allocation=none", "--summary-interval=30", "--console-log-level=warn",
                                  "--max-tries=20", "--retry-wait=5", "-d", str(part.parent),
                                  "-o", part.name, it["url"] + ".meta4"])
        elif it.get("manual"):
            # These sites block scripted downloads. Try once; don't retry a 403.
            rc = subprocess.call(["curl", "-fsL", "--max-time", "120", "-o", str(part),
                                  "-A", "Mozilla/5.0 lifeboat", it["url"]])
        else:
            rc = subprocess.call(["curl", "-fL", "--retry", "10", "--retry-delay", "5",
                              "--retry-all-errors", "-C", "-", "-o", str(part),
                              "-A", "Mozilla/5.0 lifeboat", "--progress-bar", it["url"]])
        if rc == 0 and not part.exists() and dest.exists():
            part = dest                           # aria2 keeps the metalink's file name
        if rc != 0 and it.get("manual"):
            part.unlink(missing_ok=True)
            print("  - the site blocked the download; save it by hand (listed at the end)")
            manual.append(it); continue
        if rc != 0:
            print(f"  ! download failed ({rc})"); failed.append(it["id"]); continue
        got = sha256(part)
        if want and got != want:
            print(f"  ! sha256 mismatch: want {want} got {got}. Deleting partial file.")
            part.unlink(); failed.append(it["id"]); continue
        record(manifest, it, part, dest, bool(want), got)
        mb = dest.stat().st_size / 1e6
        print(f"  ok {mb:,.0f} MB in {time.time()-t0:,.0f}s  verified={bool(want)}", flush=True)
    if manual:
        print("\nSAVE BY HAND: open each link in a browser, save the PDF to the path shown, then re-run fetch.")
        for it in manual:
            print(f"  {it['url']}\n    -> {it['dest']}")
    print("FAILED: " + ", ".join(failed) if failed else
          "ALL DONE" + (" (except the files to save by hand)" if manual else ""))
    return 1 if failed else 0


def record(manifest, it, src, dest, verified, got=None):
    got = got or sha256(src)
    if src != dest:
        src.rename(dest)
    manifest[it["id"]] = {"dest": it["dest"], "url": it["url"], "sha256": got,
                          "verified": verified, "bytes": dest.stat().st_size,
                          "license": it.get("license", ""), "title": it.get("title", ""),
                          "fetched": time.strftime("%Y-%m-%d")}
    MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

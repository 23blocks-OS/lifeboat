#!/usr/bin/env python3
"""Prove Lifeboat works with no network, and measure it.

  ./lifeboat verify-offline              checks + test questions (Wi-Fi may stay on)
  ./lifeboat verify-offline --wifi-off   also turns Wi-Fi off for the test, then back on

Checks:
  1. Every Lifeboat process listens on 127.0.0.1 only.
  2. No Lifeboat process opens a connection to any other address while answering questions.
  3. The web page references no outside URLs (no CDNs, fonts, or scripts).
  4. Test questions across every topic get cited answers. Results go to logs/verify-<date>.md
"""
import json, re, subprocess, sys, time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
APP = "http://127.0.0.1:9110"
QUESTIONS = [
    ("medical", "How do I treat a deep laceration on the forearm without medical care?"),
    ("medical", "What are the signs of shock and how do I treat it?"),
    ("medical", "Someone was bitten by a rattlesnake on the ankle. What do I do and what should I not do?"),
    ("medical", "How do I make oral rehydration solution for diarrhea?"),
    ("foraging", "Is this mushroom safe? It is white with a ring on the stem, found under an oak tree."),
    ("foraging", "How do I prepare acorns so they are safe to eat?"),
    ("water", "How do I disinfect water with household bleach? How much per gallon?"),
    ("repair", "My generator won't start. What should I check?"),
    ("repair", "My small engine runs rough and surges. What causes that?"),
    ("power", "How do I safely run a generator during a power outage?"),
    ("fire", "Wildfire smoke is heavy outside. How do I protect my family indoors?"),
    ("food", "How do I can green beans safely? Can I use a water bath?"),
    ("navigation", "How do I find north without a compass?"),
    ("comms", "Which ham radio frequencies are used for emergency communication?"),
]
sys.path.insert(0, str(ROOT))
from app import config as C  # noqa: E402
QUESTIONS.append(tuple(C.REGION["test_question"] or
                       ("hazards", "What should I do in the first hour after a major earthquake?")))


def our_pids():
    pids = []
    for f in (ROOT / "logs" / "pids").glob("*.pid"):
        try:
            pids.append(int(f.read_text().split()[0]))
        except Exception:
            pass
    # include children (pool workers, etc.)
    out = []
    for p in pids:
        out.append(p)
        kids = subprocess.run(["pgrep", "-P", str(p)], capture_output=True, text=True).stdout.split()
        out += [int(k) for k in kids]
    return out


def sockets(pids):
    if not pids:
        return []
    r = subprocess.run(["lsof", "-nP", "-a", "-i", "-p", ",".join(map(str, pids))],
                       capture_output=True, text=True)
    return r.stdout.splitlines()[1:]


def outside(lines):
    bad = []
    for l in lines:
        if "LISTEN" in l:
            if not re.search(r"(127\.0\.0\.1|\[::1\]|localhost):\d+ \(LISTEN\)", l):
                bad.append("listens beyond this laptop: " + l)
        else:
            addrs = re.findall(r"->(\S+)", l)
            for a in addrs:
                if not a.startswith(("127.0.0.1", "[::1]", "localhost")):
                    bad.append("outside connection: " + l)
    return bad


def wifi(on):
    ports = subprocess.run(["networksetup", "-listallhardwareports"], capture_output=True, text=True).stdout
    m = re.search(r"Hardware Port: Wi-Fi\nDevice: (\S+)", ports)
    subprocess.run(["networksetup", "-setairportpower", m[1] if m else "en0", "on" if on else "off"])


def main():
    wifi_off = "--wifi-off" in sys.argv
    fails = []
    try:
        httpx.get(APP + "/api/status", timeout=3)
    except Exception:
        print("Lifeboat is not running. Run ./lifeboat start first."); return 1
    st = httpx.get(APP + "/api/status").json()
    if not st["chat_loaded"]:
        print("Note: no chat model loaded. Testing library search only.")

    # 3. static assets
    for f in (ROOT / "app" / "static").iterdir():
        for url in re.findall(r"https?://[^\s\"')]+", f.read_text(errors="ignore")):
            fails.append(f"{f.name} references {url}")

    if wifi_off:
        print("Turning Wi-Fi off for the test...")
        wifi(False); time.sleep(3)

    report = [f"# Lifeboat offline verification — {time.strftime('%Y-%m-%d %H:%M')}", "",
              f"Model: {st['chat_model'] or 'none (library only)'}  ·  Wi-Fi off: {wifi_off}", ""]
    seen_bad = set()
    try:
        for topic, q in QUESTIONS:
            t0 = time.time()
            answer, passages, done = "", [], {}
            if st["chat_loaded"]:
                with httpx.stream("POST", APP + "/api/chat", json={"messages": [{"role": "user", "content": q}]},
                                  timeout=600) as r:
                    ev = None
                    for line in r.iter_lines():
                        if line.startswith("event: "):
                            ev = line[7:]
                        elif line.startswith("data: "):
                            d = json.loads(line[6:])
                            if ev == "sources": passages = d["passages"]
                            elif ev == "content": answer += d["t"]
                            elif ev == "done": done = d
                            elif ev == "error": answer += f"\n[ERROR] {d['msg']}"
                    for b in outside(sockets(our_pids())):
                        seen_bad.add(b)
            else:
                passages = httpx.get(APP + "/api/search", params={"q": q}, timeout=120).json()["passages"]
            dt = time.time() - t0
            cites = sorted(set(int(n) for n in re.findall(r"\[(\d{1,2})\]", answer)))
            ok = bool(passages) and (not st["chat_loaded"] or bool(cites))
            print(f"{'ok ' if ok else 'BAD'} {dt:5.1f}s  {len(cites)} cites  [{topic}] {q[:60]}")
            if not ok:
                fails.append(f"no grounded answer: {q}")
            report += [f"## [{topic}] {q}", "",
                       f"*{dt:.1f}s · {done.get('tok_s', '-')} tok/s · search {done.get('retrieval', {}).get('total', '-')}s "
                       f"· cited {cites}*", "", answer or "(library only)", "", "Sources:"]
            report += [f"{i}. {p['title']} — {p['source_title']}" + (f" p.{p['page']}" if p.get('page') else "")
                       for i, p in enumerate(passages, 1)]
            report.append("")
    finally:
        if wifi_off:
            wifi(True); print("Wi-Fi back on.")

    for b in outside(sockets(our_pids())):
        seen_bad.add(b)
    fails += sorted(seen_bad)
    report += ["## Network check", "", "\n".join(f"- FAIL {f}" for f in fails) or "- PASS: no outside connections, loopback only, no remote assets"]
    out = ROOT / "logs" / f"verify-{time.strftime('%Y%m%d-%H%M')}.md"
    out.write_text("\n".join(report))
    print("\n" + ("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails)))
    print(f"Full answers: {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

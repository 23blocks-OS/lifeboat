#!/usr/bin/env python3
"""Build print/binder.html: a paper backup of the most critical procedures.

It prints verbatim source passages only, never model-written text, so a printed page cannot
carry a model mistake. Open the file in a browser and print it (Cmd-P). Needs the index and
the search helpers (./lifeboat start --no-model is enough).
"""
import html, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config as C, llm, retrieve as R  # noqa: E402

CHAPTERS = {
    "1. Life threats": [
        "Stop severe bleeding: direct pressure, packing, and tourniquet",
        "CPR for adults", "Choking adult: abdominal thrusts", "Recognize and treat shock",
        "Recovery position for an unconscious breathing person",
        "Open airway and rescue breathing",
    ],
    "2. Injuries": [
        "Clean and close a deep wound without stitches", "Signs of wound infection and what to do",
        "Splint a broken arm or leg", "Treat burns", "Head injury danger signs",
        "Sprains and strains", "Remove a splinter or fish hook",
    ],
    "3. Illness": [
        "Oral rehydration solution recipe for diarrhea and dehydration", "Fever care in adults and children",
        "Heat stroke and heat exhaustion", "Hypothermia treatment", "Frostbite treatment",
        "Allergic reaction and anaphylaxis", "Carbon monoxide poisoning signs and treatment",
        "Smoke inhalation", "Toothache and dental abscess care",
    ],
    "4. Bites, stings, poisons": [
        "Rattlesnake bite first aid: what to do and not do", "Poison oak rash treatment",
        "Spider bite black widow", "Tick removal", "Mushroom poisoning symptoms death cap",
    ],
    "5. Water and sanitation": [
        "Disinfect drinking water with household bleach amounts", "Boil water to make it safe",
        "Emergency water sources in the home", "Build an emergency latrine and handle human waste",
        "Hand washing without running water",
    ],
    "6. Food": [
        "Keep food safe when the power is out refrigerator freezer", "Pressure canning low-acid vegetables",
        "Signs of botulism in canned food", "Prepare acorns to eat leaching tannins",
        "Edibility test for unknown plants and its risks",
    ],
    "7. Fire, smoke, shelter, heat": [
        "Wildfire evacuation checklist go bag", "Protect people indoors from wildfire smoke",
        "Make a box fan air filter", "Stay warm without power safe indoor heating",
        "Build an emergency shelter",
    ],
    "8. Power and fuel": [
        "Run a portable generator safely carbon monoxide", "Generator will not start troubleshooting",
        "Store gasoline safely", "Connect a generator to a house transfer switch backfeed danger",
    ],
    "9. Navigation and signals": [
        "Find north without a compass", "Use a map and compass to take a bearing",
        "Ground to air emergency signals",
    ],
    "10. Communication": [
        "Emergency ham radio frequencies and calling", "FRS GMRS radio channels for emergencies",
    ],
}
PER_TOPIC = 3


def main():
    llm.start_helpers()
    out = ROOT / "print" / "binder.html"
    out.parent.mkdir(exist_ok=True)
    parts, toc = [], []
    for ch, topics in CHAPTERS.items():
        toc.append(f"<li>{html.escape(ch)}</li>")
        parts.append(f'<h1 class="chapter">{html.escape(ch)}</h1>')
        for t in topics:
            passages, _, _ = R.search(t, final=PER_TOPIC)
            print(f"{t[:60]:60}  {len(passages)} passages", flush=True)
            parts.append(f'<section class="topic"><h2>{html.escape(t)}</h2>')
            for p in passages:
                src = f"{p['title']} — {p['source_title']}" + (f", page {p['page']}" if p.get("page") else "")
                parts.append(f'<div class="p"><div class="src">{html.escape(src)}</div>'
                             f'<div class="txt">{html.escape(p["context"][:2500])}</div></div>')
            parts.append("</section>")
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Lifeboat emergency binder</title>
<style>
body{{font:11pt/1.4 Georgia,serif;margin:0 auto;max-width:7.5in;padding:.4in;color:#000;background:#fff}}
h1.chapter{{page-break-before:always;font:bold 18pt Helvetica,Arial,sans-serif;border-bottom:3px solid #000}}
h2{{font:bold 13pt Helvetica,Arial,sans-serif;margin:14pt 0 4pt}}
.topic{{page-break-inside:auto}} .p{{border-left:3px solid #999;padding-left:8pt;margin:6pt 0}}
.src{{font:bold 9pt Helvetica,Arial,sans-serif;color:#333}} .txt{{white-space:pre-wrap;font-size:10pt}}
.cover h1{{font:bold 28pt Helvetica,Arial,sans-serif}} .warn{{border:2px solid #000;padding:8pt;margin:12pt 0}}
</style></head><body>
<div class="cover"><h1>Lifeboat emergency binder</h1>
<p>Printed {time.strftime('%Y-%m-%d')}. Verbatim extracts from the offline library. No AI-written text.</p>
<div class="warn"><b>Read the whole passage before acting.</b> These are reference extracts, not a doctor.
If any trained help can be reached, get it. Doses and amounts: follow the source exactly.</div>
<h2>Contents</h2><ol>{''.join(toc)}</ol>
<h2>Write in your own information</h2>
<p>Household members, medical conditions, medications and allergies:</p><p>______________________________________________</p>
<p>Meeting points and evacuation routes{(' (' + html.escape(C.REGION['short']) + ')') if C.REGION['short'] else ''}:</p><p>______________________________________________</p>
<p>Radio plan (frequencies, check-in times):</p><p>______________________________________________</p>
</div>
{''.join(parts)}
</body></html>"""
    out.write_text(page)
    print(f"Wrote {out}")


ROOT = Path(__file__).resolve().parent.parent
if __name__ == "__main__":
    main()

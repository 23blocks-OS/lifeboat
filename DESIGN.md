# Lifeboat — Offline Emergency Brain: Research and Design

Written 2026-11-02, during the first build. Sections 1–6 are the original research and plan.
Sections 7–8 record what the build decided and changed.

## 1. Hardware (reference build)

| Item | Value | What it means |
|---|---|---|
| Machine | MacBook Pro (Mac17,6), Apple M5 Max | Top-tier local inference |
| CPU | 18 cores (6 Super + 12 Performance) | Fast indexing and embedding |
| GPU | 40-core, Metal 4 | Fast token generation |
| Memory | 64 GB unified | About 48–52 GB usable by the GPU. A 27–35B model at 8-bit fits, with room for a long context. 70B+ does not fit well. |
| Disk | 1.4 TB free | Room for full Wikipedia, all models, and maps |
| Tools present | Homebrew, uv | Enough to run `./lifeboat setup` |

**Power.** The M5 Max can draw 60–100 W under full GPU load. A ~100 Wh battery gives about 1–1.5 hours of continuous generation. A loaded model that sits idle costs very little. Plan: use a MoE model (only ~3B active parameters per token) as the default on battery. Unload the model when you are not using it. Use macOS Low Power Mode. A 100 W+ solar panel with a USB-C PD power station is the real fix.

## 2. Existing work

| Project | What it is | Fit |
|---|---|---|
| [Project NOMAD](https://github.com/Crosstalk-Solutions/project-nomad) | Docker server: Kiwix + Ollama + Qdrant RAG + Kolibri + offline maps | Closest match. Targets Debian/Ubuntu, not macOS. Docker on a Mac adds memory and power overhead, and Docker gets no GPU access. **Reuse its content list, not its stack.** |
| [AllArkive](https://allarkive.vercel.app/) | ZIM → vector index, citation-enforcing prompt | Good reference for chunking and the citation prompt. Maturity unverified. |
| [civilization_node](https://gh.r-mj.com/emincb/civilization_node) | Ollama + Kiwix, the LLM calls a ZIM search tool | Simple tool-calling pattern. Maturity unverified. |
| Kiwix (`kiwix-serve`, `libzim`) | Offline reader and full-text search for ZIM archives | **Core dependency.** Mature, cross-platform. |
| llama.cpp (`llama-server`) | Single-binary LLM server, Metal GPU, OpenAI-compatible API | **Recommended runtime.** One binary, no Python, runs on any backup machine. |
| MLX / mlx-lm | Apple-native runtime, ~10–20% faster on Apple Silicon | Alternative. Mac only, so it hurts portability. |
| Open WebUI | Full chat UI | Heavy, many dependencies, some features call out to the network. A small custom UI is simpler and fits this need better. |

## 3. Content (sizes checked against download.kiwix.org today)

**Core — always install (~19 GB)**
- Medicine: `wikipedia_en_medicine_maxi` 1.7 G, `zimgit-medicine` 67 M, `medicalsciences.stackexchange` 58 M
- Repair: `ifixit_en_all` 3.3 G (CC BY-NC-SA; fine for personal use), `mechanics.stackexchange` 326 M, `electronics.stackexchange` 4.0 G, `diy.stackexchange` 1.9 G
- Survival and preparedness: `zimgit-post-disaster` 615 M, `zimgit-water` 20 M, `zimgit-knots` 27 M, `zimgit-food-preparation` 93 M, `outdoors.stackexchange` 135 M
- Appropriate technology: `appropedia_en_all_maxi` 555 M, `energypedia_en_all_maxi` 763 M, `sustainability.stackexchange` 26 M
- Farming and food: `gardening.stackexchange` 890 M, `cooking.stackexchange` 227 M
- Radio: `ham.stackexchange` 74 M
- General how-to: `wikibooks_en_all_maxi` 4.4 G

**Large — optional**
- `wikipedia_en_all_maxi` 119 G (with images) or `wikipedia_en_all_nopic` 49 G
- Offline maps (OpenStreetMap / Protomaps): a region is 1–20 GB, the planet is ~120 GB

**Public-domain PDFs (~1–2 GB)** — US Army: ATP 3-50.21 (Survival), TC 4-02.1 (First Aid), FM 3-25.26 (Map Reading and Land Navigation). Also the USDA Complete Guide to Home Canning, FEMA "Are You Ready?", CDC/EPA emergency water disinfection guidance, the ARRL ham band plan, and NOAA celestial navigation tables.

**Free to download, not open-licensed** — Hesperian "Where There Is No Doctor" / "Where There Is No Dentist". Free PDFs for personal use. Good value for austere medical care.

## 4. Architecture

```
            browser (localhost:9110)
                    │
      ┌─────────────┴──────────────┐
      │  Lifeboat server (FastAPI)   │  ← chat UI, Load/Unload button, citations
      │  - retrieval + reranker    │
      │  - controls llama-server   │
      └──┬──────────┬───────────┬──┘
         │          │           │
  llama-server   index.sqlite   kiwix-serve (localhost:9111)
  (GGUF model)   FTS5 + vec     ← "open source article" links, full-text search
```

- **Models** (all GGUF, all on disk):
  - *Battery / default:* Qwen3.6-35B-A3B, Q6 (~28 GB). MoE, fast, low energy per token.
  - *Best quality:* Qwen3.8-27B, Q8 (~29 GB). Dense, slower, more careful.
  - *Emergency low power:* Gemma 4 E4B, Q4 (~5 GB). Runs on 16 GB machines.
- **Retrieval:** hybrid.
  - Dense vectors (Qwen3-Embedding-0.6B, already cached) over the core corpus and the PDFs.
  - BM25 keyword search (SQLite FTS5) over the same chunks.
  - Kiwix's built-in Xapian search over full Wikipedia. Embedding all 6M+ articles is not worth the time.
  - bge-reranker-v2-m3 (already cached) picks the best 6–8 passages.
- **Store:** one SQLite file (FTS5 + sqlite-vec). No database server.
- **Chunks:** ~800 tokens, split on headings, with metadata (source, title, section, license, date, ZIM path) for citations.
- **Prompt rules:** answer from the passages. Cite [n] for every claim. Say "not in my sources" rather than guess. Add fixed safety warnings for medicine, wild food ID, electrical, fuel, and carbon monoxide. Show the verbatim passage under every answer.
- **UI:** one HTML page with vendored JS/CSS (no CDN). Includes a Load/Unload button, model picker, memory/battery readout, persistent safety banner, and a click-through to the full source in Kiwix.
- **Scripts:** `./lifeboat setup` (online, one time), `./lifeboat start`, `./lifeboat stop`, `./lifeboat verify-offline`, `./lifeboat backup /Volumes/X`.
- **Offline proof:** servers bind only to 127.0.0.1 (or the LAN, if you choose). `HF_HUB_OFFLINE=1`. `verify-offline` runs a test suite with Wi-Fi off and lists every open socket with `lsof`.

## 5. Layout and storage budget

```
lifeboat/
  lifeboat            # control script
  app/                # server + UI (in git)
  bin/                # llama-server, kiwix-serve (pinned, not in git)
  models/             # GGUF weights (~62 GB, not in git)
  library/zim/        # Kiwix archives (~19 GB core, +119 GB Wikipedia)
  library/pdf/        # public-domain manuals
  index/              # index.sqlite (~5–10 GB)
  maps/               # optional
  print/              # "paper brain" PDF of critical procedures
  MANIFEST.json       # every file: URL, sha256, size, license
```

Total: ~95 GB core. ~215 GB with full Wikipedia. Add maps on top.

## 6. Risks and limits

- A local model can hallucinate doses, plant IDs, and torque specs. The design shows the source text every time, and the prompt forbids numbers that are not in a source.
- The laptop is a single point of failure. Mitigations: `backup` clones everything to an external SSD, and a printed binder of the top ~50 procedures.
- The first download is ~100–220 GB. It needs a stable connection and AC power.

## 7. Decisions (2026-11-02)

- **Region is a setting.** `region.json` names the area, its main hazards, a test question, and local
  PDFs. The model is told where the user is and what the local hazards are. The repo ships a
  Los Angeles County example: earthquake, wildfire and smoke, heat, post-fire debris flows, tsunami.
- **Household profile.** A web intake writes `household.json` (owner-only, not in git): people's
  ages, weights, conditions, medicines, allergies, and training, plus the home's water, heat, power, and
  supplies. It goes into every prompt with rules to check conflicts and never scale adult doses.
- **Wikipedia:** full, with images (119 GB). Searched live through the archive's own Xapian index.
- **Access:** laptop only. Bind to 127.0.0.1.
- **Paper backup:** `./lifeboat print` builds a binder of verbatim passages for ~50 critical procedures.
- **Power:** profiles assume battery only, with no solar.

## 8. Changes during build (2026-11-02)

- **Storage split.** An external drive (`data/`) can hold the archives, PDFs, and the `best`/`tiny`
  models. The internal disk keeps only what must work with the drive unplugged: the program, the
  default model, the helper models, and the index. The index stores passage text, so answers still
  work without the drive.
- **Helper GPU for setup only.** An NVIDIA DGX Spark embedded passages during the reference build.
  It ran Qwen3-Embedding-0.6B in vLLM (~280 passages/s on real text vs ~60 on the laptop). vLLM
  vectors agree with the laptop's llama.cpp Q8 vectors on 98.7–99.4% of bits. The worker talks over
  ssh stdin/stdout, so it works on hosts that forbid TCP forwarding and needs no open ports. At run
  time Lifeboat never contacts a helper.
- **llama.cpp CUDA embedding was slow on GB10** (~70/s, the same as the laptop), so vLLM replaced it.
  vLLM rejects inputs over its `--max-model-len`, so the worker asks it to truncate at 2,048 tokens.
- **Downloads use aria2 with Kiwix metalinks.** One connection to the Kiwix load balancer gave
  0.6 MB/s (Wikimedia rate-limits it). aria2 pulls from every mirror at once and checks each 4 MB
  piece, at ~17–22 MB/s.
- **Embed everything.** Fast helper embedding means every passage gets a vector, not only the first
  passages of each page.
- **zimgit archives hold PDFs**, not HTML. The indexer reads PDFs inside ZIMs and takes titles
  from each archive's `database.js`.
- **No kiwix-serve.** Kiwix ships macOS tools for Intel only. The app reads ZIMs through libzim directly.

# Lifeboat: offline emergency assistant

Lifeboat is a local AI model plus a large offline library. The library covers medical manuals,
survival guides, repair guides, farming, water, power, radio, and all of Wikipedia. It runs on one
Mac with no internet, no cloud, and no other machine. Every answer cites its sources and shows the
source text.

**It is an aid, not an authority.** Always read the source text before you act. See [Disclaimer](#disclaimer).

---

## What you need

| | Minimum | Reference build |
|---|---|---|
| Computer | Apple Silicon Mac | MacBook Pro, M5 Max, 64 GB |
| Memory | 16 GB (`tiny` model only) | 64 GB (all models) |
| Internal disk | ~40 GB free | |
| Extra disk | ~170 GB more, internal or external | 500 GB external NVMe |
| Software | [Homebrew](https://brew.sh), `brew install uv aria2` | |
| Setup | A fast internet connection for a few hours | |

After setup, Lifeboat needs no network at all.

## Install

```
git clone <this repo> lifeboat && cd lifeboat
./lifeboat setup                       # or: ./lifeboat setup /Volumes/MyDrive/lifeboat  (keep archives on a drive)
nano region.json                  # set your area: see regions/README.md
./lifeboat fetch                       # download models, archives, PDFs (~210 GB, resumable, checksummed)
./lifeboat index                       # build the search index (hours; see "Faster indexing")
./lifeboat start                       # opens http://127.0.0.1:9110
```

`./lifeboat fetch 1 2 4` skips the extra models (group 3) and full Wikipedia (group 5). That needs about 55 GB.

## Daily use

| Command | What it does |
|---|---|
| `./lifeboat start` | Start the app and load the default model (Battery saver) |
| `./lifeboat start best` | Start with the most careful model (slower, more power) |
| `./lifeboat start --no-model` | Library search only. Lowest power use. |
| `./lifeboat load tiny` | Switch to the small emergency model |
| `./lifeboat unload` | Free the model's memory. Search still works. |
| `./lifeboat stop` | Stop everything |
| `./lifeboat status` | Show what is running |
| `./lifeboat verify-offline` | Prove nothing uses the network, and run test questions |
| `./lifeboat backup [dest]` | Copy program, models, and index to a drive |
| `./lifeboat print` | Build the printable emergency binder |

In the web page you can use the **Load model / Unload model** button and the model menu instead.

## Models

| Profile | Model | Size | Use it when |
|---|---|---|---|
| `battery` (default) | Qwen3.6 35B-A3B, Q6_K | 29 GB | Most of the time. Fast (~60 tokens/s), low energy per answer. |
| `best` | Qwen3.8 27B, Q8_0 | 29 GB | Hard medical or technical questions. Slower, uses more power. |
| `tiny` | Gemma 4 E4B, Q4_0 | 5 GB | Very low battery, or a Mac with 16 GB of memory. Least accurate. |

Two small helper models always run while Lifeboat is on: Qwen3-Embedding-0.6B (meaning search)
and bge-reranker-v2-m3 (picks the best passages). Together they use about 1.5 GB.
To change models, edit `app/config.py` and `sources.json`.

## Saving power

- A MacBook draws 60–100 W while it writes an answer. A full battery gives about 1–1.5 hours of
  continuous answers, but many hours of light use.
- Click **Unload model** when you are not asking questions. Unloading frees 29 GB of memory.
- **Search library** (no model) uses very little power and still shows the source passages.
- Turn on macOS Low Power Mode. Dim the screen.
- Leave "Think harder" off unless you need it. It can triple the answer time.

## Your region

`region.json` tells Lifeboat where you are. It holds your area's name, its main hazards, a test
question, and local PDFs such as USGS hazard sheets and your county's evacuation guide. The model
uses it to weigh its advice. Start from `regions/los-angeles.json`. See `regions/README.md`.

## Where things live

| What | Where | Needed for |
|---|---|---|
| Program, Python, llama.cpp | the project folder (internal disk) | Everything |
| Default model + helpers | `models/` | Answers |
| Search index (includes passage text) | `index/index.sqlite` | Answers and search |
| Archives (ZIM) and PDFs | `data/library/` (can be an external drive) | "Open full source", live Wikipedia search |
| Extra models (best, tiny) | `data/models/` | Those profiles only |

If `data` is on an external drive and the drive is unplugged, Lifeboat still answers from the index.
Only "Open full source", full Wikipedia search, and the `best`/`tiny` models need the drive.

## What is in the library

`sources.json`, `sources_pdf.json`, and `region.json` list every file, its source URL, and its
license. After `./lifeboat fetch`, `MANIFEST.json` records each file's sha256 checksum.

- **Medicine:** WikiMed (Wikipedia medicine), US Army ATP 4-02.11 / TC 4-02.1 first aid,
  Special Forces Medical Handbook ST 31-91B, Hesperian *Where There Is No Doctor* and
  *Where There Is No Dentist*, zimgit medicine library, Medical Sciences Stack Exchange.
- **Survival:** ATP 3-50.21, FM 21-76, FM 3-05.70, zimgit post-disaster, water, and knots libraries.
- **Water and food:** CDC and FEMA emergency water guides, USDA Complete Guide to Home Canning,
  zimgit food preparation, Cooking Stack Exchange.
- **Repair and building:** iFixit, DIY, Motor Vehicle Maintenance and Electronics Stack Exchanges,
  Appropedia, Wikibooks.
- **Power:** Energypedia, CDC and CPSC generator and carbon monoxide safety, Ready.gov power outage.
- **Farming:** Gardening Stack Exchange, Appropedia, Sustainability Stack Exchange.
- **Navigation and radio:** TC 3-25.26 map reading and land navigation, CISA NIFOG (emergency
  frequencies), FCC Part 97, Amateur Radio Stack Exchange.
- **Hazards:** wildfire Ready-Set-Go, EPA wildfire smoke guide, Ready.gov earthquake, wildfire,
  and winter storm sheets, plus your region's PDFs.
- **Everything else:** full English Wikipedia with images (searched live).

### Content licenses

This repo contains code only. It holds no archives, models, or PDFs. `./lifeboat fetch` downloads each
file from its publisher, for your own use.

- US government works: public domain.
- Wikipedia, Wikibooks, Stack Exchange, Appropedia, Energypedia: CC BY-SA.
- iFixit: CC BY-NC-SA (no commercial use).
- Hesperian: free for personal use. Do not resell or redistribute.
- Models: see each model's license on Hugging Face (Qwen: Apache-2.0; Gemma: Gemma terms).

If you share a built copy (for example, a drive for a neighbor), follow these licenses. Do not sell it.

## How an answer is made

1. Your question is searched three ways: keywords (SQLite FTS5) over every passage, meaning
   (1-bit vectors in sqlite-vec) over every passage, and Wikipedia's own full-text index.
2. A reranker scores about 100 candidates and keeps the best 8, at most two per page.
3. Each passage is widened with its neighbors so steps are not cut in half.
4. The model answers from those passages only, cites them as [1], [2], and says when
   its sources do not cover something. Click a citation to jump to the exact source text.

## Offline check

```
./lifeboat start
./lifeboat verify-offline            # or: ./lifeboat verify-offline --wifi-off
```

It confirms every server listens on 127.0.0.1 only, no Lifeboat process connects anywhere else,
and the web page loads nothing from the internet. It then asks 15 test questions across all
topics and writes the full answers to `logs/verify-<date>.md`.

## Faster indexing with a helper GPU

On the laptop alone, indexing runs at about 60 passages per second. The core library is several
million passages, so that takes a day or more. A Linux machine with an NVIDIA GPU can embed during
setup instead, at about 280 passages per second on a DGX Spark. Lifeboat never uses it at run time.

On the helper machine:

```
mkdir -p ~/lifeboat-prep/hf && scp scripts/remote_embed_worker.py gpu-box:lifeboat-prep/
docker run -d --name lifeboat-embed --gpus all --ipc host -p 127.0.0.1:9121:8000 \
  -v ~/lifeboat-prep/hf:/root/.cache/huggingface nvcr.io/nvidia/vllm:26.02-py3 \
  vllm serve Qwen/Qwen3-Embedding-0.6B --runner pooling --max-model-len 2048 \
  --gpu-memory-utilization 0.35 --max-num-seqs 512
```

On the Mac:

```
./lifeboat index --embed ssh:user@gpu-box
scripts/index_loop.sh ssh:user@gpu-box     # or: index each archive as its download finishes
```

The worker talks over ssh stdin/stdout. It needs no open ports and no TCP forwarding.
When indexing is done, remove the container: `docker rm -f lifeboat-embed`.

## Backup and moving to another Mac

```
./lifeboat backup /Volumes/MyDrive/lifeboat/system
```

The drive then holds a complete copy: program, Python, models, index, archives, PDFs.
To run on another Apple Silicon Mac, copy the folder to the new Mac. Link `data` to the archives
(`ln -s /Volumes/MyDrive/lifeboat data`), then run `./lifeboat start`. If the Python environment is
broken, `./lifeboat start` rebuilds it from `vendor/wheels` with no internet.

Paper backup: `./lifeboat print` writes `print/binder.html` (verbatim passages, no AI text).
Print it from the browser and keep it with your emergency kit.

## Troubleshooting

| Problem | Fix |
|---|---|
| Page does not open | `./lifeboat status`. If it is not running, `./lifeboat start`. Check `logs/app.log`. |
| "No chat model loaded" | Click **Load model**, or `./lifeboat load`. Search still works without it. |
| Model will not load | Check `logs/chat.log`. Close other large apps. Use `tiny` on 16–32 GB Macs. |
| "Drive missing" | Plug in the data drive. Answers still work from the index. |
| Slow answers | Use `battery`, not `best`. Turn off "Think harder". Plug in power. |
| Search finds nothing | `./lifeboat status` shows the passage count. If it is 0, run `./lifeboat index`. |
| A download fails | Run `./lifeboat fetch` again. It resumes and skips finished files. |

To update the library, edit `sources.json` or `sources_pdf.json` with newer file names. Run
`./lifeboat fetch`, then `./lifeboat index`. The indexer skips sources it already finished.

See `DESIGN.md` for the research and design decisions.

## Contributing

Pull requests are welcome, especially:

- new region files in `regions/`
- new public-domain or openly licensed sources, with the license recorded
- support for Linux and NVIDIA laptops

Keep it offline. No change may add a network call at run time.

## Disclaimer

Lifeboat is not a doctor, an electrician, or an emergency service. A local AI model can be wrong,
even with sources. Read the source passage before you act. If you can reach trained help, get it.
The software comes with no warranty. See `LICENSE` (MIT).

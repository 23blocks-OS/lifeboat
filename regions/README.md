# Regions

Lifeboat tunes itself to one area. `region.json` in the project root holds your area. It is not in git.

Start from the example:

```
cp regions/los-angeles.json region.json
```

Then edit these fields:

| Field | What it does |
|---|---|
| `name` | Full name, for example "Marin County, California". The model is told the user is here. |
| `short` | Short name, used in the printed binder. |
| `hazards` | Main local hazards, in plain words. The model uses this to weigh its advice. |
| `test_question` | `[topic, question]` that `./lifeboat verify-offline` asks about your area. |
| `pdfs` | Local guides to download and index. Same fields as `sources_pdf.json`. |

Good local PDFs: USGS hazard fact sheets for your area, your county's evacuation guide, and your state's
wildfire, flood, or winter storm guides. Use public-domain or free-to-use files only. Record each license.

After you change `pdfs`, run `./lifeboat fetch 4` and then `./lifeboat index`. The PDF set is indexed again.

Pull requests with new region files are welcome.

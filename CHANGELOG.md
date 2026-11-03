# Changelog

## 0.1.0 — 2026-11-03

First public release.

- Local chat model (llama.cpp, Metal) with three profiles: `battery`, `best`, and `tiny`.
- Hybrid search over ~3.8 million passages: keyword (FTS5), meaning (1-bit vectors), and live
  Wikipedia search, then a reranker. Every answer cites its sources.
- 20 Kiwix archives, full English Wikipedia, and ~80 public-domain PDFs, with sha256 checks for
  models and archives.
- Household intake: answers use each person's age, weight, conditions, medicines, and allergies.
- Child-dose guard: a warning on any child's dose, and a stronger one if the answer mentions an
  adult daily maximum.
- Region file, with a Los Angeles County example.
- `verify-offline` checks every socket while it answers 15 test questions, optionally with Wi-Fi off.
- `print` builds a paper binder of verbatim source text.
- `backup` copies the program, models, and index to a drive.

Known limits:

- Apple Silicon macOS only.
- The `battery` model can make dosing mistakes for children. Use `best` for children's doses.
- Some government PDFs must be saved by hand (see the README).

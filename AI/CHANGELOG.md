# Changelog

## v0.8.1 — Public ranking/tokenizer patch

- Added BM25F-style field ranking.
- Added Unicode/Cyrillic-aware tokenization.
- Replaced public-facing coordinate wording with field-ranking wording.
- Renamed the optional C++ ranking helper from coordinate-style wording to `field_ranker.cpp`.
- Kept the simple v0.8 user workflow unchanged.

## v0.8

- Minimal user manual.
- First-run instruction.
- Continue instruction.
- Task specification files.
- Persistent project map and action points.


## v0.8.2 — Public Code Graph / Attention Layer

- Added optional Python AST code graph layer.
- Added function/class/method symbol extraction.
- Added import/call/inheritance edge exports.
- Added `AI_OUT/code_graph.json`.
- Added `AI_OUT/code_symbols.tsv`, `import_edges.tsv`, `call_edges.tsv`, `inherit_edges.tsv`.
- Added `AI_OUT/attention_guide.md` for transformer-friendly routing.
- Added `AI_OUT/graph.html` local viewer.
- Added `py AI\run.py graph` command.
- Kept BM25F-style ranking and Unicode/Cyrillic tokenizer from v0.8.1.

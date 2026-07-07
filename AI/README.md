# AI Drop-In — LACA v0.8.2 Public Patch

This folder is a drop-in context helper for local AI coding agents.

Copy the whole `AI` folder into the root of any project. Then open that project in an AI IDE or local coding agent.

Public v0.8.2 adds:

- BM25F-style field ranking for filename, path, headings, content preview, and status evidence.
- Unicode-aware tokenizer with Ukrainian/Cyrillic support.
- Simpler public terminology: project map, task spec, action points, continue mode.

For users, read:

- `USER_MANUAL.md` — short English manual
- `МАНУАЛ_UA.md` — short Ukrainian manual

Main chat prompts:

First run:

```text
There is an AI folder in the project root. Open it and follow the instruction inside.
```

Continue later:

```text
There is an AI folder in the project root. There is a CONTINUE instruction. Execute it.
```


## v0.8.2 Code Graph Layer

This version adds an optional code graph / attention layer for AI coding agents:

- Python AST symbols: functions, classes, methods.
- Import, call, and inheritance edges.
- `AI_OUT/code_graph.json`.
- `AI_OUT/code_symbols.tsv`.
- `AI_OUT/import_edges.tsv`.
- `AI_OUT/call_edges.tsv`.
- `AI_OUT/attention_guide.md`.
- `AI_OUT/graph.html`.

Default `scan` and `continue` generate a compact seeded graph. For a larger export:

```bat
py AIun.py graph --full --max-files 5000
```

The graph is an attention guide, not a full prompt dump. Use it to choose which files and symbols the AI agent should open first.

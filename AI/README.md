# AI Drop-In — LACA v0.8.1 Public Patch

This folder is a drop-in context helper for local AI coding agents.

Copy the whole `AI` folder into the root of any project. Then open that project in an AI IDE or local coding agent.

Public v0.8.1 adds:

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

# LACA — Local AI Context Accelerator

**LACA** is a local-first context compression tool for AI coding agents.

It scans a project, ranks the most relevant files for a current task, and writes a compact working context that can be given to Codex, Cursor, Claude Code, Continue.dev, Aider, local LLM agents, or any other coding assistant.

LACA is not a chatbot, not a RAG framework, and not an embedding database. It is a lightweight preprocessor that helps an AI agent start from the right files instead of reading an entire repository.

Developer: **Ruben Galstyn**  
Also known as: **Galstyn Ruben Smbatovych**

## Why

Local AI coding agents often waste context on unrelated files. They may scan too much, mix old and new versions, or lose focus when a project has many reports, logs, configs, tests, generated files, and source directories.

LACA creates a small task-focused state:

```text
CENTER|MyProject|focus=fix failing auth tests|top_k=20|coord=x,z,y
POINT|P000001|domain=tests|status=fail|score=0.91|x=0.96|z=0.82|y=0.88|file=...
POINT|P000002|domain=source|status=unknown|score=0.87|x=0.89|z=0.66|y=0.92|file=...
RULE|expand_only_top_points|do_one_action|write_RESULT_vmem_after_action
```

The AI agent reads `context_state.vmem` and `action_points.tsv` first, then expands only the top-ranked files.

## What changed in v0.2

- Better weighted scoring with `Counter`-based domain/status inference.
- Optional `--focus`; without it, LACA ranks by general usefulness, recency, and status evidence.
- `--include-patterns` and `--exclude-patterns`.
- Larger default ignore list for `.git`, `node_modules`, virtual environments, build output, caches, and binary-heavy files.
- Head+tail text sampling for large files, so status lines at the end of logs/reports are not missed.
- Filename/path exact-match bonus for task focus terms.
- `laca result` command to parse `RESULT.vmem` and append it to local result history.
- Additional extensions: `.mdx`, `.vue`, `.svelte`, `.tsx`, `.jsx`, `.toml`, `.yaml`, and more.
- Optional embedding backend flags reserved for future use; v0.2 keeps the default zero-dependency heuristic mode.

## Install locally

From the repository root:

```bash
pip install -e .
```

Or run without install:

```bash
python -m laca.cli scan . --focus "fix failing tests" --out laca_out
```

On Windows with the Python launcher:

```bat
py -m laca.cli scan . --focus "fix failing tests" --out laca_out
```

## Basic usage

```bash
laca scan . --focus "fix failing auth tests" --out laca_out --top-k 25
```

Outputs:

```text
laca_out/project_index.json
laca_out/context_state.vmem
laca_out/action_points.tsv
laca_out/context_report.md
```

Give the last three files to your AI coding agent.

## Usage with multiple roots

```bash
laca scan ./app ./docs ./tests \
  --focus "improve CI test failure reporting" \
  --project-name "MyApp" \
  --out laca_out \
  --top-k 30
```

## Include/exclude control

```bash
laca scan . \
  --focus "frontend build error" \
  --include-patterns "*.ts,*.tsx,*.vue,*.svelte,*.json,*.md" \
  --exclude-patterns "dist,build,.next,node_modules" \
  --out laca_frontend
```

## General scan without focus

```bash
laca scan . --out laca_general
```

When `--focus` is omitted, LACA ranks files using usefulness, status markers, recency, and artifact type.

## Agent loop

After an AI agent acts, ask it to write a simple `RESULT.vmem`:

```text
RESULT|PASS|changed=src/auth.py|tests=passed
EVIDENCE|pytest tests/test_auth.py passed
NEXT|review edge cases
```

Then run:

```bash
laca result RESULT.vmem --out laca_out
```

This appends to:

```text
laca_out/result_history.jsonl
laca_out/context_update_report.md
```

## Recommended prompt for AI agents

See [`docs/PROMPT_FOR_CODEX.md`](docs/PROMPT_FOR_CODEX.md).

Short version:

```text
First read context_state.vmem and action_points.tsv.
Expand only top POINT records.
Do one exact action.
After the action, write RESULT.vmem.
Do not scan the whole project unless the context state requires it.
```

## Coordinate fields

LACA uses a simple neutral coordinate model:

- `x` — closeness to the current task focus.
- `z` — evidence/status strength.
- `y` — local operational usefulness.

The final ranking score combines all three.

## Tests

```bash
pytest
```

## License

MIT License.

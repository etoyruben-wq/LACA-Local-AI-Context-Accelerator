# LACA v0.8.2 Code Graph Layer

This public layer adds a lightweight AST/code-graph map on top of the existing LACA project-map workflow.

It is designed to help AI coding agents route attention without dumping the whole project into the prompt.

## Outputs

After `scan`, `continue`, or `graph`, LACA can generate:

- `AI_OUT/code_graph.json` — structured code graph.
- `AI_OUT/code_symbols.tsv` — functions, classes, methods.
- `AI_OUT/import_edges.tsv` — import/include edges.
- `AI_OUT/call_edges.tsv` — call edges.
- `AI_OUT/inherit_edges.tsv` — inheritance edges.
- `AI_OUT/graph_report.md` — readable graph summary.
- `AI_OUT/attention_guide.md` — compact transformer-friendly routing guide.
- `AI_OUT/code_attention.vmem` — minimal VMEM graph hints for agents.
- `AI_OUT/graph.html` — simple local HTML viewer.

## Important design rule

Do not paste the full graph into an AI prompt by default.

Use the graph as an attention map:

1. Read the task file.
2. Read `action_points.tsv`.
3. Read `attention_guide.md`.
4. Open only the relevant files/symbols.

This keeps the transformer from slowing down on large repositories.

## Default mode

By default, LACA builds a seeded graph from the current action points and a capped number of code files.

For a full graph export, run:

```bat
py AI\run.py graph --full --max-files 5000
```

## Current parser support

- Python: AST parser for functions, classes, methods, imports, calls, inheritance.
- JavaScript/TypeScript: regex fallback for imports and common symbols.
- C/C++: regex fallback for includes, classes/structs, and common function signatures.

The Python layer is the most precise in v0.8.2. Tree-sitter support is planned as a later optional module.

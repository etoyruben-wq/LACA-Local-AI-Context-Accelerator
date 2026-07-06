# Quick Start

```bash
pip install -e .
laca scan . --focus "fix failing tests" --out laca_out --top-k 25
```

Then give the generated files to your local AI coding agent:

```text
laca_out/context_state.vmem
laca_out/action_points.tsv
laca_out/context_report.md
```

After the agent acts:

```bash
laca result RESULT.vmem --out laca_out
```

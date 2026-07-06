# LACA Format Spec

## `context_state.vmem`

Line-oriented compact context format for AI coding agents.

```text
CENTER|ProjectName|focus=...|top_k=25|coord=x,z,y|version=0.2.0
RULE|expand_only_top_points|do_one_action|write_RESULT_vmem_after_action
POINT|P000001|domain=source|status=unknown|score=0.8231|x=0.9000|z=0.5100|y=0.8700|file=/path/to/file.py
NEXT|read_top_points|choose_one_action|write_RESULT.vmem
```

## Coordinates

- `x`: task relevance.
- `z`: evidence/status strength.
- `y`: operational usefulness.

## `action_points.tsv`

Tab-separated top-k table:

```text
rank id score x z y domain status size sha256 path reason
```

## `RESULT.vmem`

Agent result format:

```text
RESULT|PASS|changed=src/module.py|tests=passed
EVIDENCE|pytest tests/test_module.py passed
NEXT|review docs
```

Accepted record types:

- `RESULT`
- `STATUS`
- `BLOCKER`
- `EVIDENCE`
- `NEXT`

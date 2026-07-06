# Prompt for a local AI coding agent

Use this prompt with Codex Local, Cursor, Claude Code, Continue.dev, Aider, or another local AI coding agent.

```text
You are working inside a local repository.

Before reading the full project, read these files first:

- laca_out/context_state.vmem
- laca_out/action_points.tsv
- laca_out/context_report.md

Rules:

1. Treat CENTER as the current task center.
2. Expand only files listed in the top POINT records unless more context is strictly required.
3. Do not scan the whole project by default.
4. Do one exact action related to the current focus.
5. Run the smallest relevant test/validation command.
6. After the action, write RESULT.vmem.
7. Do not claim success without evidence.

RESULT.vmem format:

RESULT|PASS/BLOCKED/FAIL|short_summary
EVIDENCE|test/log/file evidence
NEXT|next precise action
```

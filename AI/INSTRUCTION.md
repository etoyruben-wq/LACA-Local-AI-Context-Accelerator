# First Run Instruction

1. Read `AI/TASK.md`.
2. Run the first scan:

```cmd
py AI\run.py scan
```

If `py` does not work:

```cmd
python AI\run.py scan
```

3. After scanning, read:

```text
AI_OUT/current_task.md
AI_OUT/context_state.vmem
AI_OUT/action_points.tsv
AI_OUT/context_report.md
```

4. Work only from the active action points.
5. After the action, create `RESULT.vmem`.
6. Run:

```cmd
py AI\run.py result
```

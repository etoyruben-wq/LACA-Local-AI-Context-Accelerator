# CONTINUE Instruction

1. Read `AI/TASK.md`.
2. Continue from the saved project map:

```cmd
py AI\run.py continue
```

If `py` does not work:

```cmd
python AI\run.py continue
```

3. Do not start from zero. Use the saved map:

```text
AI_STATE/project_map.json
```

4. After continuing, read:

```text
AI_OUT/current_task.md
AI_OUT/context_state.vmem
AI_OUT/action_points.tsv
AI_OUT/context_report.md
```

5. Work only from the active action points.
6. After the action, create `RESULT.vmem`.
7. Run:

```cmd
py AI\run.py result
```

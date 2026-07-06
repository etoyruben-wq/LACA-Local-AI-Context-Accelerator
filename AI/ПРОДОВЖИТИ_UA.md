# Інструкція ПРОДОВЖИТИ

1. Прочитай `AI/ТЗ_UA.md`.
2. Виконай продовження:

```cmd
py AI\run.py continue
```

Якщо `py` не працює:

```cmd
python AI\run.py continue
```

3. Не починай аналіз з нуля. Використовуй збережену карту:

```text
AI_STATE/project_map.json
```

4. Після продовження прочитай:

```text
AI_OUT/current_task.md
AI_OUT/context_state.vmem
AI_OUT/action_points.tsv
AI_OUT/context_report.md
```

5. Працюй тільки по актуальних action points.
6. Після дії створи `RESULT.vmem`.
7. Виконай:

```cmd
py AI\run.py result
```

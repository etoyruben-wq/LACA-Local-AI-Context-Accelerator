# Інструкція для першого запуску

1. Прочитай `AI/ТЗ_UA.md`.
2. Виконай перше сканування:

```cmd
py AI\run.py scan
```

Якщо `py` не працює:

```cmd
python AI\run.py scan
```

3. Після сканування прочитай:

```text
AI_OUT/current_task.md
AI_OUT/context_state.vmem
AI_OUT/action_points.tsv
AI_OUT/context_report.md
```

4. Працюй тільки по актуальних action points.
5. Після дії створи `RESULT.vmem`.
6. Виконай:

```cmd
py AI\run.py result
```

Після scan агент також може прочитати `AI_OUT/attention_guide.md`, якщо задача стосується коду. Це карта уваги, а не заміна читання коду.

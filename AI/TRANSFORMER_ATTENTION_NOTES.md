# Transformer Attention Notes

LACA does not replace a transformer model and does not modify its internal weights.

The goal is external attention routing:

- keep the full project map locally;
- send only compact task-relevant context to the agent;
- use BM25F-style file ranking for candidate selection;
- use the code graph for symbols, imports, calls, and inheritance;
- provide a small attention guide instead of a huge raw project dump.

This reduces context noise and helps the model focus on the correct files.

For large repositories, the recommended prompt context is:

1. `AI_OUT/current_task.md`
2. `AI_OUT/context_state.vmem`
3. `AI_OUT/action_points.tsv`
4. `AI_OUT/attention_guide.md`
5. only the selected source files required for the current task

If the request is not project-related, project constraints should not be applied.

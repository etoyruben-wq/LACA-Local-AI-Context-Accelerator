# User Manual

## 1. What to do with the ZIP

1. Extract the ZIP.
2. Inside it, there is an `AI` folder.
3. Copy the `AI` folder into the root of your project.

Example:

```text
MyProject/
  AI/
  src/
  README.md
```

## 2. First run

Open the project in Antigravity / Cursor / Codex Local / Claude Code.

Send this message to the agent:

```text
There is an AI folder in the project root. Open it and follow the instruction inside.
```

The agent should open `AI/INSTRUCTION.md`, run the first scan, and create:

```text
AI_OUT/
AI_STATE/
```

## 3. Continue later

When you return to the project later, send this message:

```text
There is an AI folder in the project root. There is a CONTINUE instruction. Execute it.
```

The agent should open `AI/CONTINUE.md`, load the saved map from `AI_STATE/project_map.json`, and continue without starting from zero.

## 4. Task spec

Before the first run or before continuing, open:

```text
AI/TASK.md
```

Write briefly:

```text
1. What you are doing now.
2. What result you want.
3. What the agent must focus on.
4. What the agent must not do.
5. Success criteria.
```

During the first run and during CONTINUE, this task spec is automatically pulled into the agent context.

## 5. v0.8.1 public patch

This version uses BM25F-style field ranking and a Unicode-aware tokenizer. This improves file selection in projects that contain Ukrainian, Cyrillic, mixed-language filenames, Markdown reports, scripts, and status logs.

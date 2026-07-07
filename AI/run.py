from __future__ import annotations

import argparse
import sys
from pathlib import Path
import hashlib
import json
import time

AI_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AI_DIR.parent
LOCAL_SRC = AI_DIR / "src"
OUT_DIR_DEFAULT = PROJECT_ROOT / "AI_OUT"
STATE_DIR_DEFAULT = PROJECT_ROOT / "AI_STATE"

sys.path.insert(0, str(LOCAL_SRC))

from laca.cli import main as laca_main  # noqa: E402

DEFAULT_EXCLUDES = ",".join([
    ".git", ".hg", ".svn", ".idea", ".vscode",
    "node_modules", "bower_components", "dist", "build", "target", "out",
    ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache",
    "AI", "AI_OUT", "AI_STATE", "laca_out",
])


TASK_FILE_CANDIDATES = [
    AI_DIR / "ТЗ_UA.md",
    AI_DIR / "TASK.md",
    AI_DIR / "TASK.txt",
]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def read_task_document() -> dict:
    """Read the user task specification if present.

    The task/TZ file is intentionally simple: the user can open AI/ТЗ_UA.md and write
    what they are doing, what they want to get, and what the agent must focus on.
    Both first scan and continue always pull this file into the context.
    """
    for path in TASK_FILE_CANDIDATES:
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                return {
                    "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "absolute_path": str(path),
                    "text": text,
                    "sha256": sha256_text(text),
                    "mtime": path.stat().st_mtime,
                }
    fallback = "Analyze this project and prepare the next exact development action."
    return {
        "path": "",
        "absolute_path": "",
        "text": fallback,
        "sha256": sha256_text(fallback),
        "mtime": time.time(),
    }


def summarize_task(text: str, max_chars: int = 420) -> str:
    lines = []
    boilerplate_markers = (
        "тз для ai", "task for ai", "цей файл", "this file", "агент має",
        "опиши", "напиши", "приклад", "example", "залиш", "заповнює",
        "що я зараз роблю", "що я хочу отримати", "на чому тримати",
        "що не можна", "важливі файли", "файли або папки", "критерій успіху",
        "що агент має", "what i am doing", "what i want", "what to focus",
        "what not to do", "important files", "success criteria", "final result",
    )
    for raw in text.splitlines():
        line = raw.strip().strip("#").strip()
        if not line or line.startswith("---") or line.startswith("```"):
            continue
        lower = line.lower()
        if any(marker in lower for marker in boilerplate_markers):
            continue
        if lower.startswith("-") and len(lower) < 4:
            continue
        lines.append(line)
        if len(" ".join(lines)) >= max_chars:
            break
    summary = " ".join(lines).strip()
    if not summary:
        summary = "analyze this project and prepare the next exact development action"
    return (summary[:max_chars] + "...") if len(summary) > max_chars else summary


def read_default_focus() -> str:
    task = read_task_document()
    if task["text"]:
        return summarize_task(task["text"], 900)
    return "analyze this project and prepare the next exact development action"


def write_task_state(out_dir: Path, state_dir: Path, mode: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    task = read_task_document()
    previous_path = state_dir / "task_state.json"
    previous = {}
    if previous_path.exists():
        try:
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
        except Exception:
            previous = {}
    changed = previous.get("sha256") != task["sha256"]
    record = {
        "version": "0.8.1",
        "mode": mode,
        "time": time.time(),
        "task_file": task["path"],
        "sha256": task["sha256"],
        "changed_since_last_run": changed,
        "summary": summarize_task(task["text"], 700),
    }
    previous_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    current_task = [
        "# Current Task / ТЗ",
        "",
        f"Task file: `{task['path'] or 'not found; fallback task used'}`",
        f"Task SHA256: `{task['sha256']}`",
        f"Changed since last run: `{changed}`",
        "",
        "## Summary",
        "",
        record["summary"],
        "",
        "## Full task text",
        "",
        task["text"],
        "",
    ]
    (out_dir / "current_task.md").write_text("\n".join(current_task), encoding="utf-8")
    return record


def inject_task_into_outputs(out_dir: Path, state_dir: Path, task_record: dict) -> None:
    """Make the pulled ТЗ visible to the agent in the compact output files."""
    context = out_dir / "context_state.vmem"
    task_line = (
        f"TASK|file={task_record.get('task_file') or 'none'}"
        f"|sha256={task_record.get('sha256')}"
        f"|changed={str(task_record.get('changed_since_last_run')).upper()}"
        f"|summary={str(task_record.get('summary','')).replace('|','/')}"
    )
    rule_line = "RULE|read_AI_OUT_current_task_md|task_spec_is_active_for_this_run"
    if context.exists():
        text = context.read_text(encoding="utf-8", errors="replace")
        if "TASK|file=" not in text:
            parts = text.splitlines()
            insert_at = 1 if parts else 0
            parts[insert_at:insert_at] = [task_line, rule_line]
            new_text = "\n".join(parts) + "\n"
            context.write_text(new_text, encoding="utf-8")
            (state_dir / "last_context_state.vmem").write_text(new_text, encoding="utf-8")
    report = out_dir / "context_report.md"
    if report.exists():
        text = report.read_text(encoding="utf-8", errors="replace")
        if "## Current task / ТЗ" not in text:
            block = (
                "\n## Current task / ТЗ\n\n"
                f"- Task file: `{task_record.get('task_file') or 'not found; fallback task used'}`\n"
                f"- Task changed since last run: **{task_record.get('changed_since_last_run')}**\n"
                f"- Task SHA256: `{task_record.get('sha256')}`\n\n"
                f"{task_record.get('summary','')}\n\n"
                "Agent must read `AI_OUT/current_task.md` together with `context_state.vmem` and `action_points.tsv`.\n"
            )
            report.write_text(text + block, encoding="utf-8")


def cmd_scan(args: argparse.Namespace) -> int:
    focus = args.focus or read_default_focus()
    out_dir = Path(args.out) if args.out else OUT_DIR_DEFAULT
    state_dir = Path(args.state) if args.state else STATE_DIR_DEFAULT
    task_record = write_task_state(out_dir, state_dir, mode="scan")
    laca_args = [
        "scan",
        str(PROJECT_ROOT),
        "--focus", focus,
        "--project-name", args.project_name or PROJECT_ROOT.name,
        "--out", str(out_dir),
        "--state", str(state_dir),
        "--top-k", str(args.top_k),
        "--exclude-patterns", args.exclude_patterns or DEFAULT_EXCLUDES,
    ]
    if args.include_patterns:
        laca_args.extend(["--include-patterns", args.include_patterns])
    if args.progress:
        laca_args.append("--progress")
    rc = laca_main(laca_args)
    if rc == 0:
        inject_task_into_outputs(out_dir, state_dir, task_record)
    return rc


def cmd_continue(args: argparse.Namespace) -> int:
    focus = args.focus or read_default_focus()
    out_dir = Path(args.out) if args.out else OUT_DIR_DEFAULT
    state_dir = Path(args.state) if args.state else STATE_DIR_DEFAULT
    # If no persistent map exists yet, continue automatically falls back to a full scan.
    if not (state_dir / "project_map.json").exists():
        print("AI_STATE/project_map.json not found. Running first full scan instead.")
        return cmd_scan(args)
    task_record = write_task_state(out_dir, state_dir, mode="continue")
    laca_args = [
        "continue",
        str(PROJECT_ROOT),
        "--focus", focus,
        "--project-name", args.project_name or PROJECT_ROOT.name,
        "--out", str(out_dir),
        "--state", str(state_dir),
        "--top-k", str(args.top_k),
        "--exclude-patterns", args.exclude_patterns or DEFAULT_EXCLUDES,
    ]
    if args.include_patterns:
        laca_args.extend(["--include-patterns", args.include_patterns])
    if args.progress:
        laca_args.append("--progress")
    rc = laca_main(laca_args)
    if rc == 0:
        inject_task_into_outputs(out_dir, state_dir, task_record)
    return rc


def cmd_result(args: argparse.Namespace) -> int:
    result_file = Path(args.result_file) if args.result_file else (PROJECT_ROOT / "RESULT.vmem")
    out_dir = Path(args.out) if args.out else OUT_DIR_DEFAULT
    state_dir = Path(args.state) if args.state else STATE_DIR_DEFAULT
    if not result_file.exists():
        print(f"RESULT file not found: {result_file}", file=sys.stderr)
        return 2
    return laca_main(["result", str(result_file), "--out", str(out_dir), "--state", str(state_dir)])


def cmd_status(args: argparse.Namespace) -> int:
    state_dir = Path(args.state) if args.state else STATE_DIR_DEFAULT
    out_dir = Path(args.out) if args.out else OUT_DIR_DEFAULT
    print(f"AI folder: {AI_DIR}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Output folder: {out_dir}")
    print(f"Persistent state: {state_dir}")
    print(f"Map exists: {(state_dir / 'project_map.json').exists()}")
    print(f"Result history exists: {(state_dir / 'result_history.jsonl').exists()}")
    print(f"Change log exists: {(state_dir / 'change_log.jsonl').exists()}")
    return 0


def add_common_scan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--focus", default="", help="Task focus. If omitted, AI/ТЗ_UA.md, AI/TASK.md, or AI/TASK.txt is used.")
    parser.add_argument("--top-k", type=int, default=25, help="Number of top files to export")
    parser.add_argument("--out", default="", help="Output folder. Default: ../AI_OUT")
    parser.add_argument("--state", default="", help="Persistent state folder. Default: ../AI_STATE")
    parser.add_argument("--project-name", default="", help="Human-readable project name")
    parser.add_argument("--include-patterns", default="", help="Comma-separated include patterns")
    parser.add_argument("--exclude-patterns", default="", help="Comma-separated exclude patterns")
    parser.add_argument("--progress", action="store_true", help="Print scan progress")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="AI/run.py",
        description="Drop-in context scanner for local AI coding agents.",
    )
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="First/full scan of the parent project and write AI_OUT + AI_STATE")
    add_common_scan_args(scan)
    scan.set_defaults(func=cmd_scan)

    cont = sub.add_parser("continue", help="Continue from saved AI_STATE map; update changed files only")
    add_common_scan_args(cont)
    cont.set_defaults(func=cmd_continue)

    result = sub.add_parser("result", help="Record RESULT.vmem into AI_STATE history and change log")
    result.add_argument("result_file", nargs="?", default="", help="RESULT.vmem path. Default: ../RESULT.vmem")
    result.add_argument("--out", default="", help="Output folder. Default: ../AI_OUT")
    result.add_argument("--state", default="", help="Persistent state folder. Default: ../AI_STATE")
    result.set_defaults(func=cmd_result)

    status = sub.add_parser("status", help="Show current AI_OUT/AI_STATE status")
    status.add_argument("--out", default="")
    status.add_argument("--state", default="")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    if argv is None and len(sys.argv) == 1:
        # Default behavior for agents: continue if possible, otherwise first scan.
        return cmd_continue(argparse.Namespace(
            focus="", top_k=25, out="", state="", project_name="", include_patterns="",
            exclude_patterns="", progress=False,
        ))
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

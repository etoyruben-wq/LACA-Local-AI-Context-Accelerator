from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import math
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

VERSION = "0.8.1"

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".cache", ".pytest_cache",
    "node_modules", "bower_components", "dist", "build", "target", "out",
    "__pycache__", ".mypy_cache", ".ruff_cache", ".venv", "venv", "env",
    "coverage", ".next", ".nuxt", ".turbo", ".parcel-cache", "AI_OUT", "AI_STATE",
}

DEFAULT_EXCLUDE_PATTERNS = [
    "*.pyc", "*.pyo", "*.pyd", "*.so", "*.dll", "*.exe", "*.obj", "*.o",
    "*.a", "*.lib", "*.dylib", "*.class", "*.jar", "*.war", "*.ear",
    "*.zip", "*.tar", "*.gz", "*.7z", "*.rar", "*.iso", "*.img", "*.bin",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.mp4", "*.mov", "*.avi",
    "*.mp3", "*.wav", "*.flac", "*.pdf", "*.sqlite", "*.db", "*.lock",
]

TEXT_EXTENSIONS = {
    ".txt", ".md", ".mdx", ".rst", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".css", ".scss", ".html",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cs", ".java", ".go", ".rs", ".rb", ".php",
    ".sh", ".bat", ".ps1", ".sql", ".xml", ".csv", ".tsv", ".dockerfile", ".gitignore",
}

DOMAIN_KEYWORDS: dict[str, dict[str, float]] = {
    "source": {"src": 1.2, "code": 1.0, "function": 0.7, "class": 0.8, "def": 0.7, "import": 0.5, "module": 0.9},
    "tests": {"test": 2.0, "pytest": 1.7, "unittest": 1.5, "assert": 1.2, "coverage": 0.8},
    "docs": {"readme": 2.0, "docs": 1.5, "guide": 1.3, "quickstart": 1.4, "manual": 1.2, "usage": 1.1, "instruction": 1.2},
    "config": {"config": 1.4, "pyproject": 2.0, "package": 1.2, "workflow": 1.1, "settings": 1.0, "manifest": 1.0},
    "report": {"report": 1.8, "status": 1.5, "validation": 1.7, "result": 1.4, "summary": 1.2, "log": 1.0},
    "agent": {"agent": 1.7, "cursor": 1.2, "codex": 1.2, "continue": 1.1, "claude": 1.1, "ollama": 1.1, "prompt": 1.2, "antigravity": 1.2},
}

STATUS_KEYWORDS: dict[str, dict[str, float]] = {
    "pass": {"pass": 2.0, "passed": 1.8, "success": 1.4, "ok": 0.8, "complete": 1.0, "done": 0.9},
    "fail": {"fail": 2.0, "failed": 1.8, "error": 1.4, "exception": 1.3, "broken": 1.5},
    "blocked": {"blocked": 2.0, "blocker": 1.8, "todo": 1.0, "missing": 1.0, "not_100": 1.3, "pending": 0.8},
    "draft": {"draft": 1.4, "wip": 1.2, "prototype": 1.0, "experimental": 1.0},
}

TYPE_WEIGHTS = {
    ".md": 0.95, ".mdx": 0.95, ".rst": 0.9,
    ".py": 1.0, ".js": 0.95, ".ts": 0.95, ".tsx": 0.95, ".jsx": 0.95,
    ".json": 0.8, ".yaml": 0.8, ".yml": 0.8, ".toml": 0.85,
    ".bat": 0.75, ".ps1": 0.75, ".sh": 0.75,
}

# Unicode-aware tokenizer: keeps Ukrainian/Cyrillic identifiers and mixed Latin/Cyrillic file names.
# This is intentionally simple and dependency-free for public/local use.
TOKEN_RE = re.compile(r"[\w]+(?:[.+#-][\w]+)*", re.UNICODE)

@dataclass
class FileNode:
    id: str
    path: str
    rel_path: str
    ext: str
    size: int
    mtime: float
    sha256: str
    is_text: bool
    domain: str
    status: str
    x: float
    z: float
    y: float
    score: float
    reason: list[str] = field(default_factory=list)
    sample_chars: int = 0


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_patterns(value: str | None) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in value.split(",") if p.strip()]


def normalize_text(text: str) -> str:
    """Normalize text before tokenization.

    NFKC keeps Unicode text stable across copied filenames, Markdown files, and
    mixed-language projects. Casefold handles Cyrillic/Latin casing better than
    plain lower().
    """
    return unicodedata.normalize("NFKC", text).casefold()


def tokenize(text: str) -> list[str]:
    return [m.group(0) for m in TOKEN_RE.finditer(normalize_text(text))]


def split_identifier_tokens(text: str) -> list[str]:
    """Tokenize paths and identifiers without losing Cyrillic words."""
    text = re.sub(r"([a-zа-яіїєґ])([A-ZА-ЯІЇЄҐ])", r"\1 \2", text)
    text = text.replace("_", " ").replace("/", " ").replace("\\", " ").replace(".", " ")
    return tokenize(text)


def matches_any(path_str: str, patterns: Sequence[str]) -> bool:
    norm = path_str.replace("\\", "/")
    base = Path(norm).name
    return any(fnmatch.fnmatch(norm, pat) or fnmatch.fnmatch(base, pat) for pat in patterns)


def is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    try:
        with path.open("rb") as f:
            sample = f.read(2048)
        if b"\x00" in sample:
            return False
        sample.decode("utf-8")
        return True
    except Exception:
        return False


def safe_read_text(path: Path, max_text_bytes: int = 32768) -> str:
    try:
        size = path.stat().st_size
        if size <= max_text_bytes:
            return path.read_text(encoding="utf-8", errors="replace")
        half = max_text_bytes // 2
        with path.open("rb") as f:
            head = f.read(half)
            f.seek(max(0, size - half))
            tail = f.read(half)
        return head.decode("utf-8", errors="replace") + "\n\n[LACA: middle omitted]\n\n" + tail.decode("utf-8", errors="replace")
    except Exception:
        return ""


def weighted_label(tokens: Iterable[str], groups: dict[str, dict[str, float]], default: str) -> tuple[str, float]:
    counts = Counter(tokens)
    scores: dict[str, float] = {}
    for label, weights in groups.items():
        scores[label] = sum(counts.get(key, 0) * weight for key, weight in weights.items())
    label, score = max(scores.items(), key=lambda kv: kv[1])
    return (label if score > 0 else default, score)


def recency_score(mtime: float, now: float) -> float:
    age_days = max(0.0, (now - mtime) / 86400.0)
    return 1.0 / (1.0 + age_days / 90.0)



def extract_heading_text(sample: str, max_lines: int = 80) -> str:
    """Extract Markdown-like headings and high-signal title lines for field ranking."""
    heads: list[str] = []
    for line in sample.splitlines()[:max_lines]:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#") or s.endswith(":") or s.isupper():
            heads.append(s)
    return "\n".join(heads)


def extract_status_text(sample: str, rel_path: str) -> str:
    """Extract PASS/FAIL/BLOCKED/TODO-like evidence as a separate field."""
    keys = (
        "pass", "passed", "success", "ok", "done", "complete",
        "fail", "failed", "error", "exception", "broken",
        "blocked", "blocker", "todo", "missing", "pending", "not_100",
        "пас", "готово", "помилка", "заблок", "блокер", "треба", "не працює",
    )
    out = [rel_path]
    for line in sample.splitlines()[:220]:
        low = normalize_text(line)
        if any(k in low for k in keys):
            out.append(line)
    return "\n".join(out)


def bm25f_style_relevance_score(focus: str, rel_path: str, sample: str) -> tuple[float, list[str]]:
    """BM25F-style field ranking for local AI project context.

    This is not a search-engine clone. It is a small dependency-free field scorer
    inspired by BM25F: query terms are matched separately against filename, path,
    headings, content preview, and status evidence with different weights and
    term-frequency saturation. It is intentionally public-friendly and avoids
    private/vector terminology.
    """
    focus_tokens = [t for t in split_identifier_tokens(focus) if len(t) > 1]
    if not focus_tokens:
        return 0.0, []
    unique_focus = list(dict.fromkeys(focus_tokens))
    p = Path(rel_path)
    fields: dict[str, tuple[list[str], float]] = {
        "filename": (split_identifier_tokens(p.name), 3.5),
        "path": (split_identifier_tokens(str(p.parent)), 1.8),
        "headings": (tokenize(extract_heading_text(sample)), 2.4),
        "status": (tokenize(extract_status_text(sample, rel_path)), 1.6),
        "content": (tokenize(sample), 1.0),
    }
    counts = {name: Counter(tokens) for name, (tokens, _w) in fields.items()}
    k1 = 1.25
    raw = 0.0
    reasons: list[str] = []
    for q in unique_focus:
        field_tf = 0.0
        hit_fields: list[str] = []
        for name, (_tokens, weight) in fields.items():
            tf = counts[name].get(q, 0)
            if tf:
                # Saturate high counts so one repeated word cannot dominate.
                sat = (tf * (k1 + 1.0)) / (tf + k1)
                field_tf += weight * sat
                hit_fields.append(name)
        if field_tf > 0:
            raw += field_tf
            reasons.append(f"bm25f:{q}@{','.join(hit_fields[:3])}")
    # Normalize to a compact 0..1 range for easy downstream mixing.
    norm = min(1.0, raw / max(4.0, len(unique_focus) * 3.2))
    return norm, reasons[:8]

def exact_path_bonus(rel_path: str, focus_tokens: set[str]) -> tuple[float, list[str]]:
    if not focus_tokens:
        return 0.0, []
    lower = rel_path.lower().replace("\\", "/")
    base = Path(lower).name
    reasons: list[str] = []
    bonus = 0.0
    for token in focus_tokens:
        if len(token) < 3:
            continue
        if token in base:
            bonus += 0.18; reasons.append(f"filename:{token}")
        elif token in lower:
            bonus += 0.08; reasons.append(f"path:{token}")
    return min(0.6, bonus), reasons[:6]


def relevance_score(focus: str, rel_path: str, sample: str) -> tuple[float, list[str]]:
    # Public v0.8.1: use BM25F-style field ranking with Unicode/Cyrillic tokenization.
    return bm25f_style_relevance_score(focus, rel_path, sample)


def artifact_usefulness(ext: str, rel_path: str, domain: str) -> tuple[float, list[str]]:
    lower = rel_path.lower()
    score = TYPE_WEIGHTS.get(ext.lower(), 0.4)
    reasons = [f"type:{ext or 'none'}"]
    if "readme" in lower: score += 0.25; reasons.append("readme")
    if "test" in lower: score += 0.18; reasons.append("test")
    if "report" in lower or "status" in lower: score += 0.18; reasons.append("report/status")
    if "prompt" in lower or "agent" in lower or "instruction" in lower: score += 0.12; reasons.append("agent/instruction")
    if domain in {"source", "tests", "docs", "report"}: score += 0.08
    return min(1.0, score), reasons[:6]


def status_score(status: str) -> float:
    return {"pass": 0.95, "blocked": 0.85, "fail": 0.75, "draft": 0.55, "unknown": 0.35}.get(status, 0.35)


def compute_node(path: Path, root: Path, focus: str, max_text_bytes: int, now: float, idx: int) -> FileNode:
    stat = path.stat()
    rel_path = str(path.relative_to(root)).replace("\\", "/")
    ext = path.suffix.lower()
    text = is_probably_text(path)
    sample = safe_read_text(path, max_text_bytes) if text else ""
    token_source = tokenize(rel_path + "\n" + sample[:max_text_bytes])
    domain, domain_raw = weighted_label(token_source, DOMAIN_KEYWORDS, "unknown")
    status, _status_raw = weighted_label(token_source, STATUS_KEYWORDS, "unknown")
    x, rel_reasons = relevance_score(focus, rel_path, sample)
    y, use_reasons = artifact_usefulness(ext, rel_path, domain)
    z = 0.55 * status_score(status) + 0.25 * min(1.0, domain_raw / 5.0) + 0.20 * recency_score(stat.st_mtime, now)
    if not focus:
        x = 0.35 * y + 0.35 * z + 0.30 * recency_score(stat.st_mtime, now)
    score = 0.52 * x + 0.28 * y + 0.20 * z
    return FileNode(
        id=f"P{idx:06d}", path=str(path), rel_path=rel_path, ext=ext, size=stat.st_size,
        mtime=stat.st_mtime, sha256=sha256_file(path), is_text=text, domain=domain, status=status,
        x=round(x, 4), z=round(z, 4), y=round(y, 4), score=round(score, 4),
        reason=(rel_reasons + use_reasons)[:10], sample_chars=len(sample)
    )


def should_skip(path: Path, root: Path, include_patterns: Sequence[str], full_excludes: Sequence[str], max_file_bytes: int) -> bool:
    rel_path = str(path.relative_to(root)).replace("\\", "/")
    if include_patterns and not matches_any(rel_path, include_patterns):
        return True
    if matches_any(rel_path, full_excludes):
        return True
    try:
        size = path.stat().st_size
    except OSError:
        return True
    if size > max_file_bytes:
        lower = rel_path.lower()
        if not any(key in lower for key in ("readme", "report", "status", "manifest")):
            return True
    return False


def iter_files(root: Path, include_patterns: Sequence[str], full_excludes: Sequence[str], max_file_bytes: int):
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        # keep AI tool folder out of project scanning noise when it is embedded in target repo
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDE_DIRS and not matches_any(d, full_excludes)]
        for name in filenames:
            path = Path(dirpath) / name
            try:
                if not should_skip(path, root, include_patterns, full_excludes, max_file_bytes):
                    yield path
            except Exception:
                continue


def load_map(state_dir: Path) -> dict:
    p = state_dir / "project_map.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_map(state_dir: Path, data: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "project_map.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def scan_files(roots: Sequence[Path], focus: str, include_patterns: Sequence[str], exclude_patterns: Sequence[str], max_file_bytes: int, max_text_bytes: int, show_progress: bool = False) -> list[FileNode]:
    nodes: list[FileNode] = []
    now = time.time()
    full_excludes = list(DEFAULT_EXCLUDE_PATTERNS) + list(exclude_patterns)
    count = 0
    for root in roots:
        root = root.resolve()
        if not root.exists():
            continue
        for path in iter_files(root, include_patterns, full_excludes, max_file_bytes):
            count += 1
            if show_progress and count % 250 == 0:
                print(f"scanned {count} files...", file=sys.stderr)
            try:
                nodes.append(compute_node(path, root, focus, max_text_bytes, now, len(nodes) + 1))
            except Exception as exc:
                print(f"warning: skipped {path}: {exc}", file=sys.stderr)
    nodes.sort(key=lambda n: n.score, reverse=True)
    # Renumber after ranking so ids are stable in priority order for outputs.
    for i, n in enumerate(nodes, 1):
        n.id = f"P{i:06d}"
    return nodes


def incremental_scan(root: Path, focus: str, include_patterns: Sequence[str], exclude_patterns: Sequence[str], max_file_bytes: int, max_text_bytes: int, state_dir: Path, show_progress: bool = False) -> tuple[list[FileNode], dict]:
    """Update persistent project_map.json. Changed/new files are re-read; unchanged entries are reused."""
    state = load_map(state_dir)
    old_files = {item["path"]: item for item in state.get("files", []) if "path" in item}
    seen: set[str] = set()
    nodes: list[FileNode] = []
    added: list[str] = []
    changed: list[str] = []
    reused = 0
    now = time.time()
    full_excludes = list(DEFAULT_EXCLUDE_PATTERNS) + list(exclude_patterns)
    root = root.resolve()
    count = 0
    for path in iter_files(root, include_patterns, full_excludes, max_file_bytes):
        pstr = str(path)
        seen.add(pstr)
        count += 1
        try:
            st = path.stat()
            old = old_files.get(pstr)
            if old and old.get("size") == st.st_size and abs(float(old.get("mtime", 0)) - st.st_mtime) < 0.0001:
                node = FileNode(**{k: old[k] for k in FileNode.__dataclass_fields__.keys() if k in old})
                nodes.append(node)
                reused += 1
            else:
                node = compute_node(path, root, focus, max_text_bytes, len(nodes) + 1 if False else now, len(nodes) + 1)
                nodes.append(node)
                if old: changed.append(pstr)
                else: added.append(pstr)
        except Exception as exc:
            print(f"warning: skipped {path}: {exc}", file=sys.stderr)
        if show_progress and count % 250 == 0:
            print(f"checked {count} files...", file=sys.stderr)
    deleted = sorted(set(old_files.keys()) - seen)
    nodes.sort(key=lambda n: n.score, reverse=True)
    for i, n in enumerate(nodes, 1):
        n.id = f"P{i:06d}"
    return nodes, {"added": added, "changed": changed, "deleted": deleted, "reused": reused, "checked": count}


def write_outputs(nodes: list[FileNode], out_dir: Path, project_name: str, focus: str, top_k: int, state_dir: Path | None = None, mode: str = "scan", delta: dict | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if state_dir:
        state_dir.mkdir(parents=True, exist_ok=True)
    top = nodes[:top_k]
    index_data = {"version": VERSION, "mode": mode, "project_name": project_name, "focus": focus, "files": [asdict(n) for n in nodes], "delta": delta or {}}
    (out_dir / "project_index.json").write_text(json.dumps(index_data, indent=2, ensure_ascii=False), encoding="utf-8")
    if state_dir:
        save_map(state_dir, index_data)
        (state_dir / "last_context_state.vmem").write_text("", encoding="utf-8")  # placeholder overwritten below
    lines = [
        f"CENTER|{project_name}|focus={focus or 'general'}|top_k={top_k}|ranking=bm25f_field|scores=task,status_evidence,artifact_value|version={VERSION}|mode={mode}",
        "RULE|expand_only_top_points|do_one_action|write_RESULT_vmem_after_action",
        "RULE|use_AI/run.py_continue_next_time|do_not_start_from_zero_if_AI_STATE_exists",
    ]
    for n in top:
        lines.append(f"POINT|{n.id}|domain={n.domain}|status={n.status}|score={n.score:.4f}|task={n.x:.4f}|status_evidence={n.z:.4f}|artifact_value={n.y:.4f}|file={n.path}")
    lines.append("NEXT|read_top_points|choose_one_action|write_RESULT.vmem")
    context_text = "\n".join(lines) + "\n"
    (out_dir / "context_state.vmem").write_text(context_text, encoding="utf-8")
    if state_dir:
        (state_dir / "last_context_state.vmem").write_text(context_text, encoding="utf-8")

    with (out_dir / "action_points.tsv").open("w", encoding="utf-8") as f:
        f.write("rank\tid\tscore\ttask\tstatus_evidence\tartifact_value\tdomain\tstatus\tsize\tsha256\tpath\treason\n")
        for i, n in enumerate(top, 1):
            f.write(f"{i}\t{n.id}\t{n.score:.4f}\t{n.x:.4f}\t{n.z:.4f}\t{n.y:.4f}\t{n.domain}\t{n.status}\t{n.size}\t{n.sha256}\t{n.path}\t{';'.join(n.reason)}\n")
    if state_dir:
        (state_dir / "last_action_points.tsv").write_text((out_dir / "action_points.tsv").read_text(encoding="utf-8"), encoding="utf-8")

    report = ["# LACA Context Report", "", f"Project: `{project_name}`", f"Focus: `{focus or 'general'}`", f"Mode: `{mode}`", f"Files indexed: **{len(nodes)}**", f"Top points exported: **{len(top)}**", "Ranking: **BM25F-style field ranking with Unicode/Cyrillic tokenization**", ""]
    if delta:
        report += ["## Incremental update", "", f"- Added: **{len(delta.get('added', []))}**", f"- Changed: **{len(delta.get('changed', []))}**", f"- Deleted: **{len(delta.get('deleted', []))}**", f"- Reused unchanged entries: **{delta.get('reused', 0)}**", ""]
    report += ["## Top points", ""]
    for i, n in enumerate(top[:20], 1):
        report.append(f"{i}. `{n.rel_path}` — score `{n.score:.4f}`, domain `{n.domain}`, status `{n.status}`")
    report += ["", "## Agent instruction", "", "Read `context_state.vmem` and `action_points.tsv` first. Expand only the referenced top points unless the task explicitly requires more context."]
    (out_dir / "context_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def parse_result(path: Path) -> dict[str, list[str] | str]:
    data: dict[str, list[str] | str] = {"CHANGED": [], "EVIDENCE": [], "NEXT": []}
    if not path.exists():
        raise FileNotFoundError(path)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        key = parts[0].upper()
        value = "|".join(parts[1:])
        if key in {"CHANGED", "EVIDENCE", "NEXT"}:
            assert isinstance(data[key], list)
            data[key].append(value)
        elif key in {"RESULT", "STATUS", "BLOCKER", "TASK"}:
            data[key] = value
    return data


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def command_scan(args: argparse.Namespace) -> int:
    roots = [Path(p) for p in args.roots]
    include_patterns = normalize_patterns(args.include_patterns)
    exclude_patterns = normalize_patterns(args.exclude_patterns)
    nodes = scan_files(roots, args.focus or "", include_patterns, exclude_patterns, args.max_file_bytes, args.max_text_bytes, args.progress)
    state_dir = Path(args.state) if args.state else None
    write_outputs(nodes, Path(args.out), args.project_name, args.focus or "", args.top_k, state_dir=state_dir, mode="scan")
    if not args.quiet:
        print(f"LACA v{VERSION}: indexed {len(nodes)} files")
        print(f"Output: {args.out}")
        if state_dir: print(f"Persistent state: {state_dir}")
    return 0


def command_continue(args: argparse.Namespace) -> int:
    root = Path(args.root)
    include_patterns = normalize_patterns(args.include_patterns)
    exclude_patterns = normalize_patterns(args.exclude_patterns)
    nodes, delta = incremental_scan(root, args.focus or "", include_patterns, exclude_patterns, args.max_file_bytes, args.max_text_bytes, Path(args.state), args.progress)
    write_outputs(nodes, Path(args.out), args.project_name or root.name, args.focus or "", args.top_k, state_dir=Path(args.state), mode="continue", delta=delta)
    append_jsonl(Path(args.state) / "map_update_log.jsonl", {"time": time.time(), "type": "continue", "delta": delta, "focus": args.focus or ""})
    if not args.quiet:
        print(f"LACA v{VERSION}: continued from saved map")
        print(f"checked={delta['checked']} reused={delta['reused']} added={len(delta['added'])} changed={len(delta['changed'])} deleted={len(delta['deleted'])}")
        print(f"Output: {args.out}")
    return 0


def command_result(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    state_dir = Path(args.state)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    result_data = parse_result(Path(args.result_file))
    record = {"version": VERSION, "time": time.time(), "source": str(args.result_file), "result": result_data}
    append_jsonl(state_dir / "result_history.jsonl", record)
    append_jsonl(out_dir / "result_history.jsonl", record)
    changed = result_data.get("CHANGED", [])
    if isinstance(changed, list):
        for item in changed:
            append_jsonl(state_dir / "change_log.jsonl", {"time": time.time(), "changed": item, "source": str(args.result_file)})
    report = ["# LACA Result Update", "", f"Source: `{args.result_file}`", ""]
    if not result_data:
        report.append("No RESULT/STATUS/BLOCKER/EVIDENCE/NEXT records were found.")
    else:
        for key, value in result_data.items():
            report.append(f"- **{key}**: `{value}`")
    report.append("")
    report.append("Next time, run `AI/run.py continue` so the saved project map is reused and updated instead of starting from zero.")
    (out_dir / "context_update_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    if not args.quiet:
        print(f"Updated {state_dir / 'result_history.jsonl'}")
        print(f"Updated {state_dir / 'change_log.jsonl'}")
        print(f"Wrote {out_dir / 'context_update_report.md'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="laca", description="Local AI Context Accelerator")
    parser.add_argument("--version", action="version", version=f"LACA {VERSION}")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="Full scan project roots and write compact context files")
    scan.add_argument("roots", nargs="+", help="Project roots to scan")
    scan.add_argument("--focus", default="", help="Optional task focus")
    scan.add_argument("--project-name", default="Project", help="Human-readable project name")
    scan.add_argument("--out", default="AI_OUT", help="Output directory")
    scan.add_argument("--state", default="AI_STATE", help="Persistent state directory")
    scan.add_argument("--top-k", type=int, default=25)
    scan.add_argument("--include-patterns", default="")
    scan.add_argument("--exclude-patterns", default="")
    scan.add_argument("--max-file-bytes", type=int, default=10 * 1024 * 1024)
    scan.add_argument("--max-text-bytes", type=int, default=32768)
    scan.add_argument("--progress", action="store_true")
    scan.add_argument("--quiet", action="store_true")
    scan.set_defaults(func=command_scan)

    cont = sub.add_parser("continue", help="Reuse saved project map, update changed files, and write fresh compact context")
    cont.add_argument("root", nargs="?", default=".", help="Project root to continue scanning")
    cont.add_argument("--focus", default="")
    cont.add_argument("--project-name", default="")
    cont.add_argument("--out", default="AI_OUT")
    cont.add_argument("--state", default="AI_STATE")
    cont.add_argument("--top-k", type=int, default=25)
    cont.add_argument("--include-patterns", default="")
    cont.add_argument("--exclude-patterns", default="")
    cont.add_argument("--max-file-bytes", type=int, default=10 * 1024 * 1024)
    cont.add_argument("--max-text-bytes", type=int, default=32768)
    cont.add_argument("--progress", action="store_true")
    cont.add_argument("--quiet", action="store_true")
    cont.set_defaults(func=command_continue)

    result = sub.add_parser("result", help="Parse RESULT.vmem and append it to local result/change history")
    result.add_argument("result_file", help="Path to RESULT.vmem")
    result.add_argument("--out", default="AI_OUT")
    result.add_argument("--state", default="AI_STATE")
    result.add_argument("--quiet", action="store_true")
    result.set_defaults(func=command_result)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help(); return 2
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())

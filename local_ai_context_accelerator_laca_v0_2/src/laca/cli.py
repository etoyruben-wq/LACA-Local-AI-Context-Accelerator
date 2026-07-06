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
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

VERSION = "0.2.0"

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".cache", ".pytest_cache",
    "node_modules", "bower_components", "dist", "build", "target", "out",
    "__pycache__", ".mypy_cache", ".ruff_cache", ".venv", "venv", "env",
    "coverage", ".next", ".nuxt", ".turbo", ".parcel-cache",
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
    "docs": {"readme": 2.0, "docs": 1.5, "guide": 1.3, "quickstart": 1.4, "manual": 1.2, "usage": 1.1},
    "config": {"config": 1.4, "pyproject": 2.0, "package": 1.2, "workflow": 1.1, "settings": 1.0, "manifest": 1.0},
    "report": {"report": 1.8, "status": 1.5, "validation": 1.7, "result": 1.4, "summary": 1.2, "log": 1.0},
    "agent": {"agent": 1.7, "cursor": 1.2, "codex": 1.2, "continue": 1.1, "claude": 1.1, "ollama": 1.1, "prompt": 1.2},
}

STATUS_KEYWORDS: dict[str, dict[str, float]] = {
    "pass": {"pass": 2.0, "passed": 1.8, "success": 1.4, "ok": 0.8, "complete": 1.0},
    "fail": {"fail": 2.0, "failed": 1.8, "error": 1.4, "exception": 1.3, "broken": 1.5},
    "blocked": {"blocked": 2.0, "blocker": 1.8, "todo": 1.0, "missing": 1.0, "not_100": 1.3},
    "draft": {"draft": 1.4, "wip": 1.2, "prototype": 1.0, "experimental": 1.0},
}

TYPE_WEIGHTS = {
    ".md": 0.95, ".mdx": 0.95, ".rst": 0.9,
    ".py": 1.0, ".js": 0.95, ".ts": 0.95, ".tsx": 0.95, ".jsx": 0.95,
    ".json": 0.8, ".yaml": 0.8, ".yml": 0.8, ".toml": 0.85,
    ".bat": 0.75, ".ps1": 0.75, ".sh": 0.75,
}

TOKEN_RE = re.compile(r"[A-Za-z0-9_+.#/-]+")

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
    parts: list[str] = []
    for piece in value.split(","):
        piece = piece.strip()
        if piece:
            parts.append(piece)
    return parts


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text)]


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
    """Read text safely. For large files, keep head + tail because status often appears at the end."""
    try:
        size = path.stat().st_size
        if size <= max_text_bytes:
            return path.read_text(encoding="utf-8", errors="replace")
        half = max_text_bytes // 2
        with path.open("rb") as f:
            head = f.read(half)
            f.seek(max(0, size - half))
            tail = f.read(half)
        return (
            head.decode("utf-8", errors="replace")
            + "\n\n[LACA: middle of large file omitted]\n\n"
            + tail.decode("utf-8", errors="replace")
        )
    except Exception:
        return ""


def weighted_label(tokens: Iterable[str], groups: dict[str, dict[str, float]], default: str) -> tuple[str, float]:
    counts = Counter(tokens)
    scores: dict[str, float] = {}
    for label, weights in groups.items():
        score = 0.0
        for key, weight in weights.items():
            score += counts.get(key, 0) * weight
        scores[label] = score
    label, score = max(scores.items(), key=lambda kv: kv[1])
    return (label if score > 0 else default, score)


def recency_score(mtime: float, now: float) -> float:
    age_days = max(0.0, (now - mtime) / 86400.0)
    # Smooth decay: 1.0 today, ~0.5 at 90 days, still nonzero for old files.
    return 1.0 / (1.0 + age_days / 90.0)


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
            bonus += 0.18
            reasons.append(f"filename:{token}")
        elif token in lower:
            bonus += 0.08
            reasons.append(f"path:{token}")
    return min(0.6, bonus), reasons[:6]


def relevance_score(focus: str, rel_path: str, sample: str) -> tuple[float, list[str]]:
    focus_tokens = {t for t in tokenize(focus) if len(t) > 2}
    if not focus_tokens:
        return 0.0, []
    content_tokens = Counter(tokenize(rel_path + "\n" + sample))
    overlap = sum(min(content_tokens.get(t, 0), 3) for t in focus_tokens)
    denom = math.sqrt(len(focus_tokens) * max(1, sum(1 for t in focus_tokens if content_tokens.get(t, 0) > 0)))
    base = min(1.0, overlap / max(1.0, denom * 2.5))
    bonus, reasons = exact_path_bonus(rel_path, focus_tokens)
    if base > 0:
        reasons.insert(0, f"token_overlap:{overlap}")
    return min(1.0, base + bonus), reasons


def artifact_usefulness(ext: str, rel_path: str, domain: str) -> tuple[float, list[str]]:
    lower = rel_path.lower()
    score = TYPE_WEIGHTS.get(ext.lower(), 0.4)
    reasons = [f"type:{ext or 'none'}"]
    if "readme" in lower:
        score += 0.25; reasons.append("readme")
    if "test" in lower:
        score += 0.18; reasons.append("test")
    if "report" in lower or "status" in lower:
        score += 0.18; reasons.append("report/status")
    if "prompt" in lower or "agent" in lower:
        score += 0.12; reasons.append("agent/prompt")
    if domain in {"source", "tests", "docs", "report"}:
        score += 0.08
    return min(1.0, score), reasons[:6]


def status_score(status: str) -> float:
    return {
        "pass": 0.95,
        "blocked": 0.85,
        "fail": 0.75,
        "draft": 0.55,
        "unknown": 0.35,
    }.get(status, 0.35)


def scan_files(
    roots: Sequence[Path],
    focus: str,
    include_patterns: Sequence[str],
    exclude_patterns: Sequence[str],
    max_file_bytes: int,
    max_text_bytes: int,
    show_progress: bool = False,
) -> list[FileNode]:
    nodes: list[FileNode] = []
    now = time.time()
    full_excludes = list(DEFAULT_EXCLUDE_PATTERNS) + list(exclude_patterns)
    found = 0
    for root in roots:
        root = root.resolve()
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDE_DIRS and not matches_any(d, full_excludes)]
            for name in filenames:
                path = Path(dirpath) / name
                rel_path = str(path.relative_to(root)).replace("\\", "/")
                if include_patterns and not matches_any(rel_path, include_patterns):
                    continue
                if matches_any(rel_path, full_excludes):
                    continue
                try:
                    stat = path.stat()
                    if stat.st_size > max_file_bytes:
                        # Keep metadata for huge files only when they look important by path.
                        lower = rel_path.lower()
                        if not any(key in lower for key in ("readme", "report", "status", "manifest")):
                            continue
                    found += 1
                    if show_progress and found % 250 == 0:
                        print(f"scanned {found} files...", file=sys.stderr)
                    ext = path.suffix.lower()
                    text = is_probably_text(path)
                    sample = safe_read_text(path, max_text_bytes) if text else ""
                    token_source = tokenize(rel_path + "\n" + sample[:max_text_bytes])
                    domain, domain_raw = weighted_label(token_source, DOMAIN_KEYWORDS, "unknown")
                    status, status_raw = weighted_label(token_source, STATUS_KEYWORDS, "unknown")
                    x, rel_reasons = relevance_score(focus, rel_path, sample)
                    y, use_reasons = artifact_usefulness(ext, rel_path, domain)
                    z = 0.55 * status_score(status) + 0.25 * min(1.0, domain_raw / 5.0) + 0.20 * recency_score(stat.st_mtime, now)
                    if not focus:
                        # No explicit task: rank by general usefulness, status evidence, and freshness.
                        x = 0.35 * y + 0.35 * z + 0.30 * recency_score(stat.st_mtime, now)
                    score = 0.52 * x + 0.28 * y + 0.20 * z
                    node_id = f"P{len(nodes)+1:06d}"
                    nodes.append(FileNode(
                        id=node_id,
                        path=str(path),
                        rel_path=rel_path,
                        ext=ext,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                        sha256=sha256_file(path),
                        is_text=text,
                        domain=domain,
                        status=status,
                        x=round(x, 4),
                        z=round(z, 4),
                        y=round(y, 4),
                        score=round(score, 4),
                        reason=(rel_reasons + use_reasons)[:10],
                        sample_chars=len(sample),
                    ))
                except Exception as exc:
                    print(f"warning: skipped {path}: {exc}", file=sys.stderr)
    nodes.sort(key=lambda n: n.score, reverse=True)
    return nodes


def write_outputs(nodes: list[FileNode], out_dir: Path, project_name: str, focus: str, top_k: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    top = nodes[:top_k]
    (out_dir / "project_index.json").write_text(
        json.dumps({"version": VERSION, "project_name": project_name, "focus": focus, "files": [asdict(n) for n in nodes]}, indent=2),
        encoding="utf-8",
    )
    lines = [
        f"CENTER|{project_name}|focus={focus or 'general'}|top_k={top_k}|coord=x,z,y|version={VERSION}",
        "RULE|expand_only_top_points|do_one_action|write_RESULT_vmem_after_action",
    ]
    for n in top:
        lines.append(
            f"POINT|{n.id}|domain={n.domain}|status={n.status}|score={n.score:.4f}|x={n.x:.4f}|z={n.z:.4f}|y={n.y:.4f}|file={n.path}"
        )
    lines.append("NEXT|read_top_points|choose_one_action|write_RESULT.vmem")
    (out_dir / "context_state.vmem").write_text("\n".join(lines) + "\n", encoding="utf-8")

    with (out_dir / "action_points.tsv").open("w", encoding="utf-8") as f:
        f.write("rank\tid\tscore\tx\tz\ty\tdomain\tstatus\tsize\tsha256\tpath\treason\n")
        for i, n in enumerate(top, 1):
            f.write(
                f"{i}\t{n.id}\t{n.score:.4f}\t{n.x:.4f}\t{n.z:.4f}\t{n.y:.4f}\t{n.domain}\t{n.status}\t{n.size}\t{n.sha256}\t{n.path}\t{';'.join(n.reason)}\n"
            )
    report = [
        f"# LACA Context Report",
        "",
        f"Project: `{project_name}`",
        f"Focus: `{focus or 'general'}`",
        f"Files indexed: **{len(nodes)}**",
        f"Top points exported: **{len(top)}**",
        "",
        "## Top points",
        "",
    ]
    for i, n in enumerate(top[:20], 1):
        report.append(f"{i}. `{n.rel_path}` — score `{n.score:.4f}`, domain `{n.domain}`, status `{n.status}`")
    report += [
        "",
        "## Agent instruction",
        "",
        "Read `context_state.vmem` and `action_points.tsv` first. Expand only the referenced top points unless the task explicitly requires more context.",
    ]
    (out_dir / "context_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def parse_result(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        raise FileNotFoundError(path)
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|")
        if not parts:
            continue
        if parts[0].upper() in {"RESULT", "STATUS", "BLOCKER", "EVIDENCE", "NEXT"}:
            key = parts[0].upper()
            value = "|".join(parts[1:])
            data.setdefault(key, value)
    return data


def command_scan(args: argparse.Namespace) -> int:
    roots = [Path(p) for p in args.roots]
    include_patterns = normalize_patterns(args.include_patterns)
    exclude_patterns = normalize_patterns(args.exclude_patterns)
    nodes = scan_files(
        roots=roots,
        focus=args.focus or "",
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        max_file_bytes=args.max_file_bytes,
        max_text_bytes=args.max_text_bytes,
        show_progress=args.progress,
    )
    write_outputs(nodes, Path(args.out), args.project_name, args.focus or "", args.top_k)
    if not args.quiet:
        print(f"LACA v{VERSION}: indexed {len(nodes)} files")
        print(f"Output: {args.out}")
        print("Next: give context_state.vmem + action_points.tsv to your local AI coding agent")
    return 0


def command_result(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_data = parse_result(Path(args.result_file))
    history_path = out_dir / "result_history.jsonl"
    record = {"version": VERSION, "time": time.time(), "source": str(args.result_file), "result": result_data}
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    report = ["# LACA Result Update", "", f"Source: `{args.result_file}`", ""]
    if not result_data:
        report.append("No RESULT/STATUS/BLOCKER/EVIDENCE/NEXT records were found.")
    else:
        for key, value in result_data.items():
            report.append(f"- **{key}**: `{value}`")
    (out_dir / "context_update_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    if not args.quiet:
        print(f"Updated {history_path}")
        print(f"Wrote {out_dir / 'context_update_report.md'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="laca", description="Local AI Context Accelerator")
    parser.add_argument("--version", action="version", version=f"LACA {VERSION}")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="Scan project roots and write compact context files")
    scan.add_argument("roots", nargs="+", help="Project roots to scan")
    scan.add_argument("--focus", default="", help="Optional task focus. If omitted, LACA ranks by general usefulness and recency.")
    scan.add_argument("--project-name", default="Project", help="Human-readable project name")
    scan.add_argument("--out", default="laca_out", help="Output directory")
    scan.add_argument("--top-k", type=int, default=25, help="Number of top points to export")
    scan.add_argument("--include-patterns", default="", help="Comma-separated fnmatch patterns to include")
    scan.add_argument("--exclude-patterns", default="", help="Comma-separated fnmatch patterns to exclude")
    scan.add_argument("--max-file-bytes", type=int, default=10 * 1024 * 1024, help="Skip most files larger than this")
    scan.add_argument("--max-text-bytes", type=int, default=32768, help="Sample size for text files; large files use head+tail")
    scan.add_argument("--embedding-backend", default="none", choices=["none", "sentence-transformers", "ollama", "llama.cpp"], help="Reserved optional semantic mode; v0.2 falls back to heuristic scoring")
    scan.add_argument("--progress", action="store_true", help="Print progress while scanning")
    scan.add_argument("--quiet", action="store_true", help="Suppress normal output")
    scan.set_defaults(func=command_scan)

    result = sub.add_parser("result", help="Parse RESULT.vmem and append it to local result history")
    result.add_argument("result_file", help="Path to RESULT.vmem")
    result.add_argument("--out", default="laca_out", help="Output directory containing result history")
    result.add_argument("--quiet", action="store_true")
    result.set_defaults(func=command_result)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    if getattr(args, "embedding_backend", "none") != "none":
        print("warning: optional embedding backends are reserved in v0.2; using heuristic scoring", file=sys.stderr)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

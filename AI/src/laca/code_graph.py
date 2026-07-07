from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import html
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Sequence

VERSION = "0.8.2"

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", "node_modules", "bower_components",
    "dist", "build", "target", "out", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".venv", "venv", "env", "AI", "AI_OUT", "AI_STATE", "coverage",
}

CODE_EXTENSIONS = {".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".c", ".h", ".cpp", ".hpp", ".cc", ".hh"}

JS_IMPORT_RE = re.compile(r"(?:import\s+(?:[^'\"]+\s+from\s+)?|require\s*\()\s*['\"]([^'\"]+)['\"]")
JS_FUNC_RE = re.compile(r"(?:function\s+([A-Za-z_$][\w$]*)|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(?[^=]*?\)?\s*=>|class\s+([A-Za-z_$][\w$]*))")
CPP_INCLUDE_RE = re.compile(r"#\s*include\s*[<\"]([^>\"]+)[>\"]")
CPP_SYMBOL_RE = re.compile(r"(?:class|struct)\s+([A-Za-z_]\w*)|(?:[A-Za-z_][\w:<>,~*&\s]+)\s+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:\{|;)")

@dataclass
class GraphNode:
    id: str
    type: str
    path: str = ""
    name: str = ""
    line: int = 0
    language: str = ""

@dataclass
class GraphEdge:
    source: str
    target: str
    type: str
    path: str = ""
    line: int = 0
    detail: str = ""


def sha256_file(path: Path, limit: int | None = None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        if limit is None:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        else:
            h.update(f.read(limit))
    return h.hexdigest()


def should_skip(path: Path, root: Path, exclude_patterns: list[str]) -> bool:
    rel_parts = path.relative_to(root).parts if path.exists() or path.parent.exists() else path.parts
    for part in rel_parts:
        if part in DEFAULT_EXCLUDE_DIRS:
            return True
    rel = str(path.relative_to(root)).replace("\\", "/")
    return any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(path.name, pat) for pat in exclude_patterns)


def iter_code_files(root: Path, exclude_patterns: list[str]) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if should_skip(path, root, exclude_patterns):
            continue
        if path.suffix.lower() in CODE_EXTENSIONS:
            yield path


def read_seed_paths(seed_file: Path | None, root: Path) -> set[str]:
    result: set[str] = set()
    if not seed_file or not seed_file.exists():
        return result
    try:
        lines = seed_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return result
    for line in lines:
        if not line.strip() or line.lower().startswith("rank"):
            continue
        parts = line.split("\t")
        for part in parts:
            p = part.strip().strip("`")
            if not p or "/" not in p and "\\" not in p and "." not in p:
                continue
            candidate = (root / p).resolve()
            if candidate.exists() and candidate.is_file():
                try:
                    result.add(str(candidate.relative_to(root)).replace("\\", "/"))
                except Exception:
                    pass
                break
    return result


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return dotted_name(node.func)
    if isinstance(node, ast.Subscript):
        return dotted_name(node.value)
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def lang_for(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".py", ".pyi"}: return "python"
    if ext in {".js", ".jsx", ".ts", ".tsx"}: return "javascript/typescript"
    if ext in {".c", ".h", ".cpp", ".hpp", ".cc", ".hh"}: return "c/cpp"
    return ext.lstrip(".")


def file_id(rel: str) -> str:
    return f"file:{rel}"


def symbol_id(rel: str, name: str, line: int) -> str:
    safe = name.replace(" ", "_").replace("|", "_")
    return f"symbol:{rel}:{safe}:{line}"


def parse_python(path: Path, rel: str, text: str) -> tuple[list[GraphNode], list[GraphEdge], list[str]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    errors: list[str] = []
    fid = file_id(rel)
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError as e:
        errors.append(f"{rel}:{e.lineno}: syntax error: {e.msg}")
        return nodes, edges, errors
    except Exception as e:
        errors.append(f"{rel}: parse error: {e}")
        return nodes, edges, errors

    class_stack: list[str] = []
    current_symbol: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                edges.append(GraphEdge(fid, f"module:{alias.name}", "imports", rel, getattr(node, "lineno", 0), alias.asname or ""))
            self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            module = node.module or ""
            for alias in node.names:
                target = f"module:{module}.{alias.name}" if module else f"module:{alias.name}"
                edges.append(GraphEdge(fid, target, "imports", rel, getattr(node, "lineno", 0), alias.asname or ""))
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            sid = symbol_id(rel, node.name, node.lineno)
            nodes.append(GraphNode(sid, "class", rel, node.name, node.lineno, "python"))
            edges.append(GraphEdge(fid, sid, "contains", rel, node.lineno, "class"))
            for base in node.bases:
                base_name = dotted_name(base)
                if base_name:
                    edges.append(GraphEdge(sid, f"symbol-ref:{base_name}", "inherits", rel, node.lineno, base_name))
            class_stack.append(node.name)
            prev = current_symbol[-1] if current_symbol else ""
            current_symbol.append(sid)
            self.generic_visit(node)
            current_symbol.pop()
            class_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_func(node, "function")

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_func(node, "function")

        def _visit_func(self, node: ast.AST, typ: str) -> None:
            name = getattr(node, "name", "")
            display = f"{class_stack[-1]}.{name}" if class_stack else name
            sid = symbol_id(rel, display, getattr(node, "lineno", 0))
            ntype = "method" if class_stack else typ
            nodes.append(GraphNode(sid, ntype, rel, display, getattr(node, "lineno", 0), "python"))
            parent = current_symbol[-1] if current_symbol else fid
            edges.append(GraphEdge(parent, sid, "contains", rel, getattr(node, "lineno", 0), ntype))
            current_symbol.append(sid)
            self.generic_visit(node)
            current_symbol.pop()

        def visit_Call(self, node: ast.Call) -> None:
            name = dotted_name(node.func)
            if name:
                src = current_symbol[-1] if current_symbol else fid
                edges.append(GraphEdge(src, f"call:{name}", "calls", rel, getattr(node, "lineno", 0), name))
            self.generic_visit(node)

    Visitor().visit(tree)
    return nodes, edges, errors


def parse_regex_code(path: Path, rel: str, text: str) -> tuple[list[GraphNode], list[GraphEdge], list[str]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    errors: list[str] = []
    fid = file_id(rel)
    ext = path.suffix.lower()
    language = lang_for(path)
    if ext in {".js", ".jsx", ".ts", ".tsx"}:
        for m in JS_IMPORT_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            edges.append(GraphEdge(fid, f"module:{m.group(1)}", "imports", rel, line, "regex"))
        for m in JS_FUNC_RE.finditer(text):
            name = next((g for g in m.groups() if g), "")
            line = text.count("\n", 0, m.start()) + 1
            if name:
                typ = "class" if m.group(3) else "function"
                sid = symbol_id(rel, name, line)
                nodes.append(GraphNode(sid, typ, rel, name, line, language))
                edges.append(GraphEdge(fid, sid, "contains", rel, line, "regex"))
    elif ext in {".c", ".h", ".cpp", ".hpp", ".cc", ".hh"}:
        for m in CPP_INCLUDE_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            edges.append(GraphEdge(fid, f"include:{m.group(1)}", "imports", rel, line, "include"))
        for m in CPP_SYMBOL_RE.finditer(text):
            name = m.group(1) or m.group(2)
            line = text.count("\n", 0, m.start()) + 1
            if name:
                typ = "class" if m.group(1) else "function"
                sid = symbol_id(rel, name, line)
                nodes.append(GraphNode(sid, typ, rel, name, line, language))
                edges.append(GraphEdge(fid, sid, "contains", rel, line, "regex"))
    return nodes, edges, errors


def build_graph(root: Path, out_dir: Path, state_dir: Path, *, seed_file: Path | None = None, full: bool = False, max_files: int = 500, exclude_patterns: list[str] | None = None) -> dict:
    root = root.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    exclude_patterns = exclude_patterns or []
    seed_paths = read_seed_paths(seed_file, root)
    all_code_files = list(iter_code_files(root, exclude_patterns))
    selected: list[Path] = []
    if full:
        selected = all_code_files[:max_files] if max_files > 0 else all_code_files
    else:
        if seed_paths:
            for p in all_code_files:
                rel = str(p.relative_to(root)).replace("\\", "/")
                if rel in seed_paths:
                    selected.append(p)
        # add nearby small baseline if no seed or too few files
        if len(selected) < min(25, max_files):
            for p in all_code_files:
                if p not in selected:
                    selected.append(p)
                if len(selected) >= max_files:
                    break
        selected = selected[:max_files]

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    errors: list[str] = []
    file_records: list[dict] = []
    language_counts: Counter[str] = Counter()

    for path in selected:
        rel = str(path.relative_to(root)).replace("\\", "/")
        language = lang_for(path)
        language_counts[language] += 1
        fid = file_id(rel)
        nodes.append(GraphNode(fid, "file", rel, path.name, 0, language))
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            errors.append(f"{rel}: read error: {e}")
            continue
        if path.suffix.lower() in {".py", ".pyi"}:
            ns, es, er = parse_python(path, rel, raw)
        else:
            ns, es, er = parse_regex_code(path, rel, raw)
        nodes.extend(ns); edges.extend(es); errors.extend(er)
        try:
            digest = sha256_file(path, limit=512 * 1024)
        except Exception:
            digest = ""
        file_records.append({"path": rel, "language": language, "sha256_head": digest, "symbols": len(ns), "edges": len(es)})

    graph = {
        "version": VERSION,
        "generated_at": time.time(),
        "root": str(root),
        "mode": "full" if full else "seeded",
        "scanned_code_files": len(selected),
        "available_code_files": len(all_code_files),
        "max_files": max_files,
        "seed_file": str(seed_file) if seed_file else "",
        "languages": dict(language_counts),
        "nodes": [asdict(n) for n in nodes],
        "edges": [asdict(e) for e in edges],
        "errors": errors[:200],
        "files": file_records,
    }
    write_graph_outputs(graph, out_dir, state_dir)
    return graph


def write_tsv(path: Path, rows: list[list[str]]) -> None:
    path.write_text("\n".join("\t".join(str(c).replace("\t", " ").replace("\n", " ") for c in row) for row in rows) + "\n", encoding="utf-8")


def write_graph_outputs(graph: dict, out_dir: Path, state_dir: Path) -> None:
    (out_dir / "code_graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    (state_dir / "code_graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

    symbol_rows = [["type", "name", "path", "line", "language", "id"]]
    for n in graph["nodes"]:
        if n["type"] in {"class", "function", "method"}:
            symbol_rows.append([n["type"], n["name"], n["path"], n["line"], n["language"], n["id"]])
    write_tsv(out_dir / "code_symbols.tsv", symbol_rows)

    import_rows = [["source", "target", "path", "line", "detail"]]
    call_rows = [["source", "target", "path", "line", "detail"]]
    inherits_rows = [["source", "target", "path", "line", "detail"]]
    for e in graph["edges"]:
        row = [e["source"], e["target"], e["path"], e["line"], e["detail"]]
        if e["type"] == "imports": import_rows.append(row)
        elif e["type"] == "calls": call_rows.append(row)
        elif e["type"] == "inherits": inherits_rows.append(row)
    write_tsv(out_dir / "import_edges.tsv", import_rows)
    write_tsv(out_dir / "call_edges.tsv", call_rows)
    write_tsv(out_dir / "inherit_edges.tsv", inherits_rows)

    edge_counts = Counter(e["type"] for e in graph["edges"])
    file_symbol_counts = Counter()
    for n in graph["nodes"]:
        if n["type"] in {"class", "function", "method"}:
            file_symbol_counts[n["path"]] += 1
    import_targets = Counter(e["target"] for e in graph["edges"] if e["type"] == "imports")
    call_targets = Counter(e["detail"] for e in graph["edges"] if e["type"] == "calls")

    report = [
        "# LACA Code Graph Report",
        "",
        f"Version: `{graph['version']}`",
        f"Mode: `{graph['mode']}`",
        f"Scanned code files: **{graph['scanned_code_files']}** / available **{graph['available_code_files']}**",
        f"Nodes: **{len(graph['nodes'])}**",
        f"Edges: **{len(graph['edges'])}**",
        "",
        "## Edge counts",
        "",
    ]
    for key, value in sorted(edge_counts.items()):
        report.append(f"- {key}: {value}")
    report += ["", "## Files with most symbols", ""]
    for path, count in file_symbol_counts.most_common(20):
        report.append(f"- `{path}` — {count}")
    report += ["", "## Top import targets", ""]
    for target, count in import_targets.most_common(20):
        report.append(f"- `{target}` — {count}")
    report += ["", "## Top call targets", ""]
    for target, count in call_targets.most_common(20):
        report.append(f"- `{target}` — {count}")
    if graph.get("errors"):
        report += ["", "## Parse/read warnings", ""]
        for err in graph["errors"][:50]:
            report.append(f"- {err}")
    report.append("")
    (out_dir / "graph_report.md").write_text("\n".join(report), encoding="utf-8")

    attention = [
        "# LACA Attention Guide",
        "",
        "This is a compact routing layer for AI agents. It is not a replacement for reading code; it tells the agent where to look first.",
        "",
        "## Read order",
        "",
        "1. `AI_OUT/current_task.md`",
        "2. `AI_OUT/action_points.tsv`",
        "3. `AI_OUT/code_symbols.tsv`",
        "4. `AI_OUT/import_edges.tsv` and `AI_OUT/call_edges.tsv`",
        "5. Open only the files needed for the current task.",
        "",
        "## Transformer-friendly rule",
        "",
        "Do not inject the full code graph into the prompt. Use this guide and the top symbol/edge tables as an attention map.",
        "",
        "## Most symbol-dense files",
        "",
    ]
    for path, count in file_symbol_counts.most_common(12):
        attention.append(f"- `{path}` — {count} symbols")
    attention += ["", "## Strong import hubs", ""]
    for target, count in import_targets.most_common(12):
        attention.append(f"- `{target}` — {count} imports")
    attention += ["", "## Frequent call names", ""]
    for target, count in call_targets.most_common(12):
        attention.append(f"- `{target}` — {count} calls")
    attention.append("")
    (out_dir / "attention_guide.md").write_text("\n".join(attention), encoding="utf-8")

    vmem = [
        f"GRAPH|version={graph['version']}|mode={graph['mode']}|files={graph['scanned_code_files']}|nodes={len(graph['nodes'])}|edges={len(graph['edges'])}",
        "RULE|use_graph_as_attention_map|do_not_dump_full_graph_into_prompt",
    ]
    for path, count in file_symbol_counts.most_common(20):
        vmem.append(f"GRAPH_FILE|symbols={count}|path={path}")
    for target, count in import_targets.most_common(20):
        vmem.append(f"GRAPH_IMPORT_HUB|count={count}|target={target}")
    for target, count in call_targets.most_common(20):
        vmem.append(f"GRAPH_CALL|count={count}|target={target}")
    (out_dir / "code_attention.vmem").write_text("\n".join(vmem) + "\n", encoding="utf-8")

    # small dependency-free HTML viewer
    graph_json = html.escape(json.dumps({
        "summary": {"nodes": len(graph["nodes"]), "edges": len(graph["edges"]), "mode": graph["mode"]},
        "nodes": graph["nodes"][:2000],
        "edges": graph["edges"][:4000],
    }, ensure_ascii=False))
    html_text = f"""<!doctype html>
<meta charset=\"utf-8\">
<title>LACA Code Graph</title>
<style>body{{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:24px;background:#111;color:#eee}}pre{{white-space:pre-wrap;background:#1e1e1e;padding:16px;border-radius:8px}}table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #333;padding:6px}}</style>
<h1>LACA Code Graph</h1>
<p>Mode: <b>{html.escape(graph['mode'])}</b>; files: <b>{graph['scanned_code_files']}</b>; nodes: <b>{len(graph['nodes'])}</b>; edges: <b>{len(graph['edges'])}</b>.</p>
<p>This viewer intentionally shows a capped graph subset. Full data is in <code>code_graph.json</code>.</p>
<h2>Graph JSON subset</h2>
<pre id=\"data\">{graph_json}</pre>
"""
    (out_dir / "graph.html").write_text(html_text, encoding="utf-8")


def explain_query(query: str, out_dir: Path) -> str:
    graph_path = out_dir / "code_graph.json"
    if not graph_path.exists():
        return "No code_graph.json found. Run `py AI\\run.py graph` first."
    graph = json.loads(graph_path.read_text(encoding="utf-8", errors="replace"))
    q = query.casefold()
    hits = []
    for n in graph.get("nodes", []):
        hay = " ".join([n.get("name", ""), n.get("path", ""), n.get("type", "")]).casefold()
        if q in hay:
            hits.append({"kind": "node", **n})
    for e in graph.get("edges", []):
        hay = " ".join([e.get("source", ""), e.get("target", ""), e.get("detail", ""), e.get("path", "")]).casefold()
        if q in hay:
            hits.append({"kind": "edge", **e})
    lines = [f"# LACA Query Explain: {query}", "", f"Hits: **{len(hits)}**", ""]
    for h in hits[:80]:
        if h["kind"] == "node":
            lines.append(f"- NODE `{h.get('type')}` `{h.get('name')}` in `{h.get('path')}` line {h.get('line')}")
        else:
            lines.append(f"- EDGE `{h.get('type')}` `{h.get('source')}` → `{h.get('target')}` in `{h.get('path')}` line {h.get('line')} `{h.get('detail')}`")
    result = "\n".join(lines) + "\n"
    (out_dir / "query_explain.md").write_text(result, encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="laca-code-graph", description="LACA optional AST/code graph layer")
    p.add_argument("root", nargs="?", default=".")
    p.add_argument("--out", default="AI_OUT")
    p.add_argument("--state", default="AI_STATE")
    p.add_argument("--seed-file", default="")
    p.add_argument("--full", action="store_true", help="Scan all supported code files up to --max-files")
    p.add_argument("--max-files", type=int, default=500)
    p.add_argument("--exclude-patterns", default="")
    p.add_argument("--query", default="", help="After graph build/existing graph, write query_explain.md")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root)
    out_dir = Path(args.out)
    state_dir = Path(args.state)
    excludes = [x.strip() for x in args.exclude_patterns.split(",") if x.strip()]
    seed = Path(args.seed_file) if args.seed_file else None
    graph = build_graph(root, out_dir, state_dir, seed_file=seed, full=args.full, max_files=args.max_files, exclude_patterns=excludes)
    print(f"LACA code graph v{VERSION}: mode={graph['mode']} files={graph['scanned_code_files']} nodes={len(graph['nodes'])} edges={len(graph['edges'])}")
    print(f"Wrote {out_dir / 'code_graph.json'}")
    print(f"Wrote {out_dir / 'attention_guide.md'}")
    if args.query:
        print(explain_query(args.query, out_dir))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

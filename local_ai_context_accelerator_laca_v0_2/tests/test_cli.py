from pathlib import Path

from laca.cli import main


def test_scan_and_result(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# Demo\n\nStatus: PASS\n", encoding="utf-8")
    (project / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (project / "test_app.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    out = tmp_path / "out"
    rc = main(["scan", str(project), "--focus", "fix tests", "--out", str(out), "--top-k", "5", "--quiet"])
    assert rc == 0
    assert (out / "context_state.vmem").exists()
    assert (out / "action_points.tsv").exists()
    assert (out / "project_index.json").exists()

    result = tmp_path / "RESULT.vmem"
    result.write_text("RESULT|PASS|tests passed\nEVIDENCE|pytest passed\nNEXT|ship\n", encoding="utf-8")
    rc = main(["result", str(result), "--out", str(out), "--quiet"])
    assert rc == 0
    assert (out / "result_history.jsonl").exists()
    assert "PASS" in (out / "context_update_report.md").read_text(encoding="utf-8")


def test_scan_without_focus(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# Demo\n", encoding="utf-8")
    out = tmp_path / "out"
    rc = main(["scan", str(project), "--out", str(out), "--quiet"])
    assert rc == 0
    state = (out / "context_state.vmem").read_text(encoding="utf-8")
    assert "focus=general" in state

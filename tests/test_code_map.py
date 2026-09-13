"""Static source facts, immutable provenance, real optional C++ grammar and replay."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from vaws_knowledge.code_map import build_code_map, compare_maps, navigate
from vaws_knowledge.code_map import cpp


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "static@example.test")
    git(root, "config", "user.name", "Static test")
    return root


def commit(root):
    git(root, "add", ".")
    git(root, "commit", "-qm", "source snapshot")
    return git(root, "rev-parse", "HEAD")


def test_python_source_import_resolution_and_no_execution(tmp_path):
    root = repo(tmp_path)
    (root / "pkg").mkdir()
    (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pkg" / "api.py").write_text("def work(x):\n    return x\n", encoding="utf-8")
    (root / "pkg" / "use.py").write_text("raise RuntimeError('never execute')\nfrom .api import work as run\ndef use(x):\n    return run(x)\n", encoding="utf-8")
    result = build_code_map(root, tmp_path / "state")
    assert result["complete"]
    edge = next(e for e in result["edges"] if e["kind"] == "static_call_reference")
    assert ":work:" in edge["target"]
    assert edge["evidence"]["path"] == "pkg/use.py"
    assert edge["evidence"]["line_start"] == 4
    assert next(n for n in result["nodes"] if n["name"] == "work")["signature"] == "work(x)"
    assert not result["revision"] and result["identity_kind"] == "observed_worktree_content"


def test_cpp_actual_parser_cross_language_registration_and_dynamic_boundary(tmp_path):
    pytest.importorskip("tree_sitter_cpp")
    root = repo(tmp_path)
    fixture = Path(__file__).parent / "fixtures" / "code_map"
    for path in fixture.iterdir():
        shutil.copyfile(path, root / path.name)
    result = build_code_map(root, tmp_path / "state")
    assert result["complete"], result["gaps"]
    graph = navigate(result, "npu_gemma_rms_norm", depth=3)
    kinds = {e["kind"] for e in graph["edges"]}
    assert {"torch_operator_reference", "torch_registration", "dynamic_api_name"} <= kinds
    regs = [e for e in result["edges"] if e["kind"] == "torch_registration"]
    assert {e["dispatch"] for e in regs} == {"torch::kPrivateUse1", "Meta"}
    assert all(e["resolution"] == "declared" for e in regs)
    assert any(e.get("guards") for e in regs)
    api = next(n for n in graph["nodes"] if n["kind"] == "dynamic_api")
    assert api["name"] == "aclnnGemmaRmsNorm"
    assert next(e for e in graph["edges"] if e["target"] == api["id"])["resolution"] == "dynamic_name_only"
    assert not any("fake_string" in n["name"] or "aclnnFakeComment" in n["name"] for n in result["nodes"])
    assert len(graph["nodes"]) <= 40 and len(graph["edges"]) <= 40


def test_pinned_revision_reads_committed_blob_and_replay_reads_no_source_bytes(tmp_path):
    root = repo(tmp_path)
    path = root / "op.py"
    path.write_text("def original():\n    return 1\n", encoding="utf-8")
    revision = commit(root)
    first = build_code_map(root, tmp_path / "state", revision=revision)
    path.write_text("def dirty():\n    return 2\n", encoding="utf-8")
    replay = build_code_map(root, tmp_path / "state", revision=revision)
    assert first["snapshot"] == replay["snapshot"]
    assert replay["stats"]["parsed"] == replay["stats"]["bytes_read"] == 0
    assert replay["stats"]["reused"] == 1
    assert any(n["name"] == "original" for n in replay["nodes"])
    current = build_code_map(root, tmp_path / "state")
    assert current["snapshot"] != replay["snapshot"]
    assert current["observed_head"] == revision and current["revision"] is None
    assert any(n["name"] == "dirty" for n in current["nodes"])


def test_same_size_mtime_change_invalidates_and_reuses_unrelated_file(tmp_path):
    import os
    root = repo(tmp_path)
    a, b = root / "a.py", root / "b.py"
    a.write_text("def one(): pass\n", encoding="utf-8")
    b.write_text("def stay(): pass\n", encoding="utf-8")
    before = build_code_map(root, tmp_path / "state")
    stat = a.stat()
    a.write_text("def two(): pass\n", encoding="utf-8")
    os.utime(a, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    after = build_code_map(root, tmp_path / "state")
    assert after["stats"]["parsed"] == after["stats"]["reused"] == 1
    assert compare_maps(before, after)["changed"] == ["a.py"]


def test_deleted_and_unavailable_are_distinguished_and_scopes_do_not_mix(tmp_path):
    root = repo(tmp_path)
    (root / "a.py").write_text("def a(): pass\n", encoding="utf-8")
    (root / "b.py").write_text("def b(): pass\n", encoding="utf-8")
    before = build_code_map(root, tmp_path / "state")
    partial = build_code_map(root, tmp_path / "state", limits={"max_files": 1})
    assert partial["status"] == "partial"
    delta = compare_maps(before, partial)
    assert delta["removed"] == [] and delta["unknown"] == ["b.py"]
    (root / "b.py").unlink()
    after = build_code_map(root, tmp_path / "state")
    assert compare_maps(before, after)["removed"] == ["b.py"]
    with pytest.raises(ValueError, match="same source and scope"):
        compare_maps(before, build_code_map(root, tmp_path / "state", paths=["a.py"]))


def test_broken_syntax_and_missing_cpp_dependency_are_explicit(tmp_path, monkeypatch):
    root = repo(tmp_path)
    (root / "bad.py").write_text("def bad(\n", encoding="utf-8")
    result = build_code_map(root, tmp_path / "state")
    assert result["status"] == "partial" and result["source_complete"]
    assert result["gaps"][0]["kind"] == "parse_error"
    import builtins
    original = builtins.__import__
    def no_cpp(name, *args, **kwargs):
        if name == "tree_sitter_cpp":
            raise ImportError("not installed")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_cpp)
    assert cpp.parse(b"int f(){}", "f.cpp")["gaps"][0]["kind"] == "parser_unavailable"


def test_budget_cancel_and_bad_cache_preserve_last_complete_map(tmp_path):
    root = repo(tmp_path)
    (root / "a.py").write_text("def a(): pass\n", encoding="utf-8")
    first = build_code_map(root, tmp_path / "state")
    report = next((tmp_path / "state").rglob("map-*.json"))
    original = report.read_bytes()
    partial = build_code_map(root, tmp_path / "state", cancelled=lambda: True)
    assert not partial["complete"] and report.read_bytes() == original
    partial = build_code_map(root, tmp_path / "state", limits={"max_file_bytes": 2})
    assert partial["gaps"][0]["kind"] == "file_byte_budget"
    cached = next((tmp_path / "state").rglob("parsed/*.json"))
    cached.write_text('{"content_sha256":"x","symbols":null}', encoding="utf-8")
    recovered = build_code_map(root, tmp_path / "state")
    assert recovered["complete"] and recovered["snapshot"] == first["snapshot"]


def test_ascend_host_and_tiling_registration_and_declaration(tmp_path):
    pytest.importorskip("tree_sitter_cpp")
    root = repo(tmp_path)
    (root / "op.cpp").write_text('namespace ops { class Gemma : public OpDef {}; OP_ADD(Gemma); }\nnamespace tiling { class GemmaTiling {}; REGISTER_TILING_DATA_CLASS(Gemma, GemmaTiling); }\nextern "C" int aclnnGemmaGetWorkspaceSize(int x);\n', encoding="utf-8")
    result = build_code_map(root, tmp_path / "state")
    assert any(n["name"] == "aclnnGemmaGetWorkspaceSize" and n["kind"] == "function_declaration" for n in result["nodes"])
    assert {e["registration"] for e in result["edges"] if e["kind"] == "ascend_registration"} == {"OP_ADD", "REGISTER_TILING_DATA_CLASS"}


def test_relative_scope_and_symlink_boundary(tmp_path):
    root = repo(tmp_path)
    (root / "inside").mkdir()
    (root / "inside" / "a.py").write_text("def a(): pass\n", encoding="utf-8")
    (root / "outside.py").write_text("def outside(): pass\n", encoding="utf-8")
    result = build_code_map(root, tmp_path / "state", paths=["inside"])
    assert [f["path"] for f in result["files"]] == ["inside/a.py"]
    with pytest.raises(ValueError, match="relative paths"):
        build_code_map(root, tmp_path / "state", paths=["../outside"])


def test_navigation_does_not_merge_unresolved_receivers(tmp_path):
    pytest.importorskip("tree_sitter_cpp")
    root = repo(tmp_path)
    (root / "ops.cpp").write_text("void a(){ x.dim(); }\nvoid b(){ x.dim(); }\n", encoding="utf-8")
    result = build_code_map(root, tmp_path / "state")
    graph = navigate(result, "a", depth=3)
    assert not any(n["name"] == "b" for n in graph["nodes"])


def test_busy_is_quiet_and_does_not_run_another_parser(tmp_path):
    from vaws_knowledge.distribution.sync import SwitchLock
    root = repo(tmp_path)
    (root / "a.py").write_text("def a(): pass\n", encoding="utf-8")
    first = build_code_map(root, tmp_path / "state")
    lockpath = tmp_path / "state" / "code-map" / first["source_id"] / "build.lock"
    with SwitchLock(lockpath):
        assert build_code_map(root, tmp_path / "state")["status"] == "busy"


def test_parser_failure_is_bounded_and_can_retry(tmp_path, monkeypatch):
    from vaws_knowledge.code_map import python
    root = repo(tmp_path)
    (root / "a.py").write_text("def a(): pass\n", encoding="utf-8")
    original = python.parse
    monkeypatch.setattr(python, "parse", lambda *args: (_ for _ in ()).throw(RecursionError("deep source")))
    result = build_code_map(root, tmp_path / "state")
    assert result["gaps"][0]["kind"] == "parser_failure"
    monkeypatch.setattr(python, "parse", original)
    assert build_code_map(root, tmp_path / "state")["complete"]


def test_python_syntax_warnings_are_recorded_not_printed(tmp_path, capsys):
    root = repo(tmp_path)
    (root / "a.py").write_text('value = "\\d"\n', encoding="utf-8")
    result = build_code_map(root, tmp_path / "state")
    assert result["complete"]
    assert capsys.readouterr().err == ""

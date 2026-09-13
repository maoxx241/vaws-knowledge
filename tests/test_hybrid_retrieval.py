"""Behavioral retrieval cases: exact evidence, outage use and rank fusion."""
from __future__ import annotations

import hashlib
import json
from unittest.mock import Mock

from vaws_knowledge.local.backend import Hit, MemoryBackend, UnavailableBackend
from vaws_knowledge.markdown import load_document, meta_path
from vaws_knowledge.retrieval import fuse, source_excerpt
from vaws_knowledge.server.layers import load_config
from vaws_knowledge.server.query import explain, query


def setup(tmp_path):
    notes = tmp_path / "notes"
    notes.mkdir()
    config = load_config({"state_root": str(tmp_path / "state"), "backend": "memory",
                          "layers": {"shared": {"enabled": False}, "candidate": {"enabled": False},
                                     "project": str(notes)}}, env={})
    config.retrieval = MemoryBackend()
    return config, notes


def test_long_note_returns_matching_lines_and_current_source_after_edit(tmp_path):
    config, notes = setup(tmp_path)
    path = notes / "case.md"
    raw = "# Graph observations\n\n" + "ordinary unrelated context\n" * 40 + "## Replay diagnosis\nACLGraph ERR0417 occurs only in this observed case.\nCause remains unknown.\n"
    path.write_text(raw, encoding="utf-8")
    hit = query(config, text="ERR0417").results[0]
    evidence = hit["evidence"]
    assert evidence["line_start"] > 35
    assert "Cause remains unknown" in hit["excerpt"]
    assert hit["excerpt"] == "\n".join(raw.splitlines()[evidence["line_start"] - 1:evidence["line_end"]])
    assert "text" not in evidence  # Do not repeat the source text in Agent context.
    assert evidence["content_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert explain(config, hit["ref"])["content"].endswith("Cause remains unknown.")
    path.write_text(raw.replace("unknown.", "still under investigation."), encoding="utf-8")
    assert query(config, text="ERR0417").results[0]["evidence"]["content_sha256"] != evidence["content_sha256"]


def test_vector_outage_and_search_exception_retain_local_matches_without_startup(tmp_path):
    config, notes = setup(tmp_path)
    (notes / "exact.md").write_text("# Operator note\n\naclnnFoo_42 fails in the recorded shape.\n", encoding="utf-8")
    for backend in (UnavailableBackend("offline"), MemoryBackend()):
        config.retrieval = backend
        backend.available = Mock(side_effect=AssertionError("query prepared backend"))
        backend.upsert = Mock(side_effect=AssertionError("query embedded"))
        if isinstance(backend, MemoryBackend):
            backend.search = Mock(side_effect=TimeoutError("read timed out"))
        result = query(config, text="aclnnFoo_42")
        assert result.degraded and result.unavailable
        assert result.results[0]["retrieval"] == ["lexical"]
        assert not config.state_root.exists()


def test_chinese_terms_exact_identifiers_and_related_semantic_hit(tmp_path):
    config, notes = setup(tmp_path)
    for name, text in {"exact": "# Evidence\n\nHCCL_E_PARA 参数错误，检查通信域。",
                       "semantic": "# Worker timeout\n\nCollective setup exceeded the deadline.",
                       "irrelevant": "# Browser\n\nWindow placement and font colors."}.items():
        (notes / f"{name}.md").write_text(text, encoding="utf-8")
    document = load_document(notes / "semantic.md", layer="project", root=notes)
    config.retrieval.search = Mock(return_value=[Hit(document.uri, .98, title=document.title)])
    result = query(config, text="HCCL_E_PARA 通信参数错误")
    assert {hit["title"] for hit in result.results} == {"Evidence", "Worker timeout"}
    assert any(hit["retrieval"] == ["lexical"] for hit in result.results)
    chinese = query(config, text="参数错误")
    assert any("参数错误" in hit["excerpt"] for hit in chinese.results)


def test_rrf_deduplicates_each_route_before_limit_and_does_not_compare_raw_scores():
    first = Hit("one", .01)
    second = Hit("two", 900)
    results = fuse([first, first, Hit("three", .001)], [second, first])
    assert results[0][0].uri == "one"
    assert results[0][1] == ["vector", "lexical"]
    assert len(results) == 3
    assert results[0][0].score == 1 / 61 + 1 / 62


def test_deleted_disabled_and_forged_identities_cannot_appear_via_fallback(tmp_path):
    config, notes = setup(tmp_path)
    path = notes / "forged.md"
    path.write_text("# Forged\n\nforgedneedle", encoding="utf-8")
    meta_path(path).write_text(json.dumps({"uri": "viking://resources/shared/v1/secret.md"}), encoding="utf-8")
    response = query(config, text="forgedneedle")
    assert response.results == [] and response.degraded
    meta_path(path).unlink()
    config.retrieval.upsert("viking://resources/project/forged.md", path.read_text(), layer="project")
    path.unlink()
    assert query(config, text="forgedneedle").results == []
    assert query(config, text="forgedneedle", layers=["shared"]).results == []


def test_exact_rare_token_ranks_above_long_generic_note(tmp_path):
    config, notes = setup(tmp_path)
    for name, raw in {"specific": "# Runtime note\n\nHCCL_E_PARA graph fails.",
                      "generic": "# Graph guide\n\n" + "graph capture replay " * 100,
                      "other": "# Graph introduction\n\ngraph background."}.items():
        (notes / f"{name}.md").write_text(raw, encoding="utf-8")
    result = query(config, text="HCCL_E_PARA graph", limit=1)
    assert result.results[0]["slug"] == "specific"


def test_long_single_line_keeps_match_and_reports_column():
    raw = "# Evidence\n" + "intro " * 220 + "unique_marker end\n"
    evidence = source_excerpt(raw, "unique_marker")
    assert "unique_marker" in evidence["text"]
    assert evidence["line_start"] == evidence["line_end"] == 2
    assert evidence["column_start"] > 1
    assert raw.splitlines()[1][evidence["column_start"] - 1:].startswith(evidence["text"])


def test_newline_hash_scope_matches_normalized_source_text():
    windows = source_excerpt("# Note\r\n\r\nunique_marker\r\n", "unique_marker")
    unix = source_excerpt("# Note\n\nunique_marker\n", "unique_marker")
    assert windows == unix
    assert unix["hash_scope"] == "utf8_text_with_normalized_newlines"


def test_partly_missing_mount_is_incomplete_even_if_backend_ready(tmp_path):
    from dataclasses import replace
    from vaws_knowledge.distribution.manifest import atomic_write_json

    config, notes = setup(tmp_path)
    (notes / "visible.md").write_text("# Seen\n\nunique_marker", encoding="utf-8")
    config.mounts["project"] = replace(config.mount("project"), roots=(notes, tmp_path / "missing"))
    atomic_write_json(config.state_root / "maintenance.json", {"ready": True})
    result = query(config, text="unique_marker")
    assert result.results and result.degraded
    assert any("could not be read" in note for note in result.notes)

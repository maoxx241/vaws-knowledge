"""Public enrichment follows the same immutable body revision and active switch."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from distribution.helpers import FakeClient, make_release_dir
from test_distribution_build import BuildFakeClient, _repo

from vaws_knowledge.distribution.build import build_pack
from vaws_knowledge.distribution.errors import CorruptPack, SourceUnavailable
from vaws_knowledge.distribution.manifest import EMBEDDING_MODEL, ExpectedContract, validate_release_manifest, sha256_file
from vaws_knowledge.distribution.references import prepared_shared_documents, verify_references
from vaws_knowledge.distribution.release import LocalReleaseSource, make_release
from vaws_knowledge.distribution.sync import DistributionState, check_and_sync, current_shared
from vaws_knowledge.markdown import normalized_sha256

EMBEDDING = {"model": EMBEDDING_MODEL, "dimension": 384}


def build(tmp_path, monkeypatch, *, alias="Gemma graph padding", topic="vllm-ascend"):
    from vaws_knowledge.distribution import build as module
    monkeypatch.setattr(module, "_installed_version", lambda package: "0.4.19" if package == "openviking" else "0.1.10")
    raw = "# RMSNorm observation\n\n## Conditions\nshape: 32 tokens\n\nGemma replay used the recorded shape. Cause remains unknown.\n"
    metadata = {"source": {"path": "C:/Users/private-person/secret.md", "host": "192.168.19.2"},
                "conditions": {"device": "Ascend"}, "evidence": {"token": "secret-private-evidence"},
                "retrieval": {"source_sha256": normalized_sha256(raw), "aliases": [alias], "topics": [topic]}}
    repo, sha = _repo(tmp_path, {"rmsnorm.md": raw, "rmsnorm.meta.json": json.dumps(metadata)})
    result = build_pack(repo=repo, out_dir=tmp_path / "out", client=BuildFakeClient(), expected_sha=sha)
    return result, repo, metadata


def sync(state, release, client=None, **kwargs):
    return check_and_sync(state, LocalReleaseSource(release), embedding_info=EMBEDDING, client=client or FakeClient(), **kwargs)


def test_build_prepares_allowed_metadata_and_context_from_final_public_body(tmp_path, monkeypatch):
    result, repo, metadata = build(tmp_path, monkeypatch, alias="Gemma graph from 192.168.19.2")
    reference = result.pack_path.parent / result.manifest["references"]["file"]
    rows = verify_references(reference, validate_release_manifest(result.manifest, expected=ExpectedContract()), pack_path=result.pack_path)
    row = rows["rmsnorm.md"]
    exported = reference.read_text(encoding="utf-8")
    assert "private-person" not in exported and "secret-private-evidence" not in exported
    assert "192.168.19.2" not in exported and "redacted" in exported
    assert row["retrieval"]["topics"] == ["vllm-ascend"]
    assert row["contexts"]["source_sha256"] == row["source_sha256"]
    assert any(item["field"] == "shape" for item in row["contexts"]["conditions"])
    assert json.loads((repo / "rmsnorm.meta.json").read_text()) == metadata


def test_release_switch_exposes_body_alias_topic_and_source_together(tmp_path, monkeypatch):
    result, _, _ = build(tmp_path, monkeypatch)
    release = make_release(pack_path=result.pack_path, build_manifest=result.manifest, out_dir=tmp_path / "release")
    state = tmp_path / "state"
    client = FakeClient()
    switched = sync(state, release, client)
    assert switched.status == "switched", switched.reason
    current = current_shared(state)
    docs = list(prepared_shared_documents(state, current=current))
    assert len(docs) == 1
    assert docs[0].uri == current["root_uri"] + "/rmsnorm.md"
    assert docs[0].retrieval["aliases"] == ["Gemma graph padding"]
    assert docs[0].retrieval["topics"] == ["vllm-ascend"]
    assert docs[0].retrieval["source_sha256"] == normalized_sha256(docs[0].raw_text)
    assert current["metadata_status"] == "available"
    assert current["references_sha256"] == result.manifest["references"]["sha256"]
    pointer = DistributionState(state).current_path.read_bytes()
    assert sync(state, release, client).status == "unchanged"
    assert DistributionState(state).current_path.read_bytes() == pointer


def test_corrupt_metadata_prevents_switch_and_preserves_old_source(tmp_path, monkeypatch):
    old = make_release_dir(tmp_path / "old")
    state = tmp_path / "state"
    client = FakeClient()
    assert sync(state, old, client).ok
    prior = DistributionState(state).current_path.read_bytes()
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    result, _, _ = build(build_dir, monkeypatch)
    release = make_release(pack_path=result.pack_path, build_manifest=result.manifest, out_dir=tmp_path / "release")
    asset = release / result.manifest["references"]["file"]
    asset.write_text("{}", encoding="utf-8")
    failure = sync(state, release, client)
    assert failure.status == "corrupt", failure.reason
    assert DistributionState(state).current_path.read_bytes() == prior
    assert list(prepared_shared_documents(state))[0].title == "Alpha note"


@pytest.mark.parametrize("change", ["body_hash", "contexts", "private_field", "commit"])
def test_even_rehashed_asset_must_match_prepared_source(tmp_path, monkeypatch, change):
    result, _, _ = build(tmp_path, monkeypatch)
    manifest_data = copy.deepcopy(result.manifest)
    asset = result.pack_path.parent / result.manifest["references"]["file"]
    payload = json.loads(asset.read_text())
    row = payload["documents"][0]
    if change == "body_hash":
        row["source_sha256"] = "f" * 64
    elif change == "contexts":
        row["contexts"]["sections"][0]["line_end"] = 999
    elif change == "private_field":
        row["source"] = {"path": "C:/private/secret"}
    else:
        payload["source_git_sha"] = "f" * 40
    asset.write_text(json.dumps(payload), encoding="utf-8")
    manifest_data["references"].update(size=asset.stat().st_size, sha256=sha256_file(asset))
    manifest = validate_release_manifest(manifest_data, expected=ExpectedContract())
    with pytest.raises(CorruptPack):
        verify_references(asset, manifest, pack_path=result.pack_path)


def test_prepared_metadata_tampering_is_detected_and_repaired_in_new_generation(tmp_path, monkeypatch):
    result, _, _ = build(tmp_path, monkeypatch)
    release = make_release(pack_path=result.pack_path, build_manifest=result.manifest, out_dir=tmp_path / "release")
    state = tmp_path / "state"
    client = FakeClient()
    assert sync(state, release, client).ok
    current = current_shared(state)
    sidecar = Path(current["prepared_root"]) / "rmsnorm.meta.json"
    original = sidecar.read_text()
    sidecar.write_text(original.replace("Gemma graph padding", "incorrect alias"), encoding="utf-8")
    with pytest.raises(CorruptPack, match="differs"):
        list(prepared_shared_documents(state))
    repaired = sync(state, release, client, verify=True)
    assert repaired.ok, repaired.reason
    assert current_shared(state)["prepared_root"] != current["prepared_root"]
    assert list(prepared_shared_documents(state))[0].retrieval["aliases"] == ["Gemma graph padding"]


def test_legacy_pack_reuses_body_without_claiming_enrichment(tmp_path):
    release = make_release_dir(tmp_path / "release")
    state = tmp_path / "state"
    client = FakeClient()
    assert sync(state, release, client).ok
    assert current_shared(state)["metadata_status"] == "unavailable_legacy"
    docs = list(prepared_shared_documents(state))
    assert len(docs) == 2 and all(not doc.retrieval for doc in docs)
    assert not any(name == "write" for name, _ in client.calls)


def test_catalog_search_discovers_prepared_alias_and_keeps_topic_selection(tmp_path, monkeypatch):
    from vaws_knowledge.catalog import refresh_catalog, search_catalog
    from vaws_knowledge.server.layers import load_config
    result, _, _ = build(tmp_path, monkeypatch, alias="numeric normalization incident", topic="ascend")
    release = make_release(pack_path=result.pack_path, build_manifest=result.manifest, out_dir=tmp_path / "release")
    state = tmp_path / "state"
    assert sync(state, release).ok
    bootstrap = tmp_path / "bootstrap"
    bootstrap.mkdir()
    config = load_config({"state_root": str(state), "backend": "memory", "layers": {
        "shared": str(bootstrap), "project": {"enabled": False}, "candidate": {"enabled": False}}}, env={})
    report = refresh_catalog(config, extra_documents=prepared_shared_documents(state))
    assert report["status"] == "ready", report
    found = search_catalog(config, "numeric normalization incident", layers=["shared"], selection={"topics": ["ascend"], "mode": "only"})
    assert found.hits and found.hits[0].uri.startswith(current_shared(state)["root_uri"])
    assert not search_catalog(config, "numeric normalization incident", layers=["shared"], selection={"topics": ["unrelated"], "mode": "only"}).hits


def test_context_lines_are_derived_after_public_preparation_and_stale_alias_is_ignored():
    from vaws_knowledge.distribution.references import prepare_reference
    from vaws_knowledge.context import document_context
    raw = "An earlier observation.\n\n# RMSNorm\n\n## Conditions\nhost: 192.168.12.3\n\nMeasured result remains conditional.\n"
    final, row = prepare_reference("rmsnorm.md", raw, {"retrieval": {
        "source_sha256": "f" * 64, "aliases": ["outdated unrelated result"], "topics": ["old"]}})
    assert final != raw and "192.168.12.3" not in final
    assert row["contexts"] == document_context(final)
    assert row["retrieval"]["aliases"] == row["retrieval"]["topics"] == []
    assert row["retrieval"]["source_sha256"] == normalized_sha256(final)

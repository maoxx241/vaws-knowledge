"""Native response replays do not rewrite evidence or enqueue it again."""

from __future__ import annotations

import io
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock, patch

import pytest

from vaws_knowledge import summary_hook
from vaws_knowledge.markdown import load_document, meta_path
from vaws_knowledge.server.layers import load_config


TEXT = "The prepared launch environment preserves CANN paths; the cause remains uncertain."


@pytest.fixture
def config(tmp_path):
    return load_config({
        "backend": "memory", "state_root": str(tmp_path / "state"),
        "layers": {"candidate": {"root": str(tmp_path / "candidate")}},
    }, env={})


def payload(text=TEXT, **extra):
    return {"hook_event_name": "Stop", "session_id": "first-session",
            "last_assistant_message": text, **extra}


def snapshot(root):
    return {path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.iterdir() if path.is_file()}


def test_replay_preserves_bytes_mtime_timestamp_and_queue(config):
    queue = Mock(return_value={"status": "local_only"})
    with patch("vaws_knowledge.publishing.queue_capture", queue), \
         patch("vaws_knowledge.server.capture.utc_now", return_value="2026-01-01T00:00:00Z"):
        first = summary_hook.capture_summary(payload(), config=config, client="codex")
    root = config.mount("candidate").roots[0]
    before = snapshot(root)
    with patch("vaws_knowledge.publishing.queue_capture", queue), \
         patch("vaws_knowledge.server.capture.utc_now", return_value="2026-09-13T00:00:00Z"):
        again = summary_hook.capture_summary(payload(), config=config, client="codex")
    assert again["status"] == "unchanged" and again["ref"] == first["ref"]
    assert snapshot(root) == before
    assert json.loads(next(root.glob("*.meta.json")).read_text())["captured_at"] == "2026-01-01T00:00:00Z"
    queue.assert_called_once()


def test_changed_summary_creates_new_evidence(config):
    queue = Mock(return_value={"status": "local_only"})
    with patch("vaws_knowledge.publishing.queue_capture", queue):
        first = summary_hook.capture_summary(payload(), config=config, client="codex")
        second = summary_hook.capture_summary(payload(TEXT + " A second run reproduced it."),
                                              config=config, client="codex")
    assert first["ref"] != second["ref"]
    assert second["status"] == "saved"
    assert len(list(config.mount("candidate").roots[0].glob("*.md"))) == 2
    assert queue.call_count == 2


def test_same_prose_from_other_client_preserves_first_source(config):
    first = summary_hook.capture_summary(payload(), config=config, client="codex")
    root = config.mount("candidate").roots[0]
    before = snapshot(root)
    again = summary_hook.capture_summary(payload(session_id="other-session"), config=config, client="claude")
    note = load_document(next(root.glob("*.md")), layer="candidate", root=root)
    assert again["status"] == "unchanged" and again["ref"] == first["ref"]
    assert snapshot(root) == before
    assert note.source == {"client": "codex", "session_id": "first-session"}


@pytest.mark.parametrize("rename", [False, True])
def test_replay_does_not_undo_maintainer_changes(config, rename):
    first = summary_hook.capture_summary(payload(), config=config, client="codex")
    root = config.mount("candidate").roots[0]
    note = next(root.glob("*.md"))
    note.write_text("# Maintained observation\n\nThe earlier explanation was disproved.\n", encoding="utf-8")
    if rename:
        renamed = root / "maintained-note.md"
        meta_path(note).rename(meta_path(renamed))
        note.rename(renamed)
    before = snapshot(root)
    with patch("vaws_knowledge.summary_hook.capture", side_effect=AssertionError("replay overwrote maintenance")):
        again = summary_hook.capture_summary(payload(), config=config, client="codex")
    assert again["status"] == "preserved" and again["ref"] == first["ref"]
    assert snapshot(root) == before


def test_parallel_delivery_saves_and_queues_once(config):
    entered, release = Event(), Event()
    original = summary_hook.capture

    def paused_capture(**kwargs):
        entered.set()
        assert release.wait(10)
        return original(**kwargs)

    queue = Mock(return_value={"status": "local_only"})
    with patch("vaws_knowledge.summary_hook.capture", side_effect=paused_capture) as save, \
         patch("vaws_knowledge.publishing.queue_capture", queue), \
         ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(summary_hook.capture_summary, payload(), config=config, client="codex")
        try:
            assert entered.wait(10)
            again = summary_hook.capture_summary(payload(), config=config, client="codex")
            assert again == {"status": "busy"}
        finally:
            release.set()
        saved = first.result(timeout=10)
    assert saved["status"] == "saved"
    save.assert_called_once()
    queue.assert_called_once()
    assert summary_hook.capture_summary(payload(), config=config, client="codex")["status"] == "unchanged"


def test_unrelated_summary_does_not_wait_for_other_content(config):
    entered, release = Event(), Event()
    original = summary_hook.capture

    def paused_capture(**kwargs):
        if kwargs["content"] == TEXT:
            entered.set()
            assert release.wait(10)
        return original(**kwargs)

    with patch("vaws_knowledge.summary_hook.capture", side_effect=paused_capture), \
         ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(summary_hook.capture_summary, payload(), config=config, client="codex")
        try:
            assert entered.wait(10)
            other = summary_hook.capture_summary(payload(TEXT + " A separate response."),
                                                 config=config, client="codex")
            assert other["status"] == "saved"
        finally:
            release.set()
        assert first.result(timeout=10)["status"] == "saved"
    assert len(list(config.mount("candidate").roots[0].glob("*.md"))) == 2


def test_hook_output_stays_quiet_and_uses_no_backend_or_transcript(config, monkeypatch, capsys):
    event = payload(transcript_path="this-file-must-not-be-read.jsonl")
    monkeypatch.setattr(summary_hook, "load_config", lambda **_: config)
    with patch("vaws_knowledge.server.capture.backend_for_config", side_effect=AssertionError("backend started")):
        for _ in range(2):
            monkeypatch.setattr(summary_hook.sys, "stdin", io.StringIO(json.dumps(event)))
            assert summary_hook.main(["--client", "codex"]) == 0
    assert capsys.readouterr().out == "{}\n{}\n"
    assert not config.state_root.exists()

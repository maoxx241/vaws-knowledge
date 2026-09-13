"""Explicit, bounded import transactions into independent Markdown output."""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Mapping

from .common import Budget, ImportLimit, IntakeError, Limits, command, digest, inside, read_json, write_atomic, write_json
from .generation import GenerationPending, generate
from .sources import iter_source, normalize, source_identity


@contextlib.contextmanager
def _lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise IntakeError("this source is already being synchronized") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _safe(root: Path, relative: str) -> Path:
    path = root / relative
    if not inside(path, root):
        raise ValueError("generated path escapes its output directory")
    current = path
    while current != root and current != current.parent:
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ValueError("generated path contains a symlink or junction")
        current = current.parent
    return path


def _file_hash(path: Path, max_bytes: int) -> str | None:
    if not path.is_file() or path.stat().st_size > max_bytes:
        return None
    return digest(path.read_bytes())


def _owned(output: Path, record: dict, limits: Limits) -> bool:
    for field in ("body", "metadata"):
        info = record.get(field, {})
        if not info.get("path") or not info.get("sha256"):
            return False
        if _file_hash(_safe(output, info.get("path", ".")), limits.output_chars * 8 + 128_000) != info.get("sha256"):
            return False
    for info in record.get("assets", []):
        if _file_hash(_safe(output, info["path"]), limits.total_bytes) != info["sha256"]:
            return False
    return True


def _parse(raw_path: Path, spec: dict, limits: Limits, budget: Budget) -> dict:
    options_path = raw_path.parent / "options.json"
    write_json(options_path, {"limits": asdict(limits), "options": {"ocr": spec.get("ocr")}})
    env = os.environ.copy()
    # Optional numerical dependencies may otherwise reserve dozens of BLAS
    # thread stacks just to parse a spreadsheet on a many-core host.
    for variable in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[variable] = "1"
    package_root = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = package_root + os.pathsep + env.get("PYTHONPATH", "")
    _, raw = command([sys.executable, "-m", "knowledge_intake.worker", str(raw_path), str(options_path)], timeout=budget.remaining(), max_bytes=limits.output_chars * 8 + 256_000, env=env)
    return json.loads(raw)


def _render(item, source_id: str, raw_hash: str, parsed: dict, assets: list[dict]) -> tuple[bytes, bytes]:
    title = re.sub(r"[\r\n]+", " ", item.name)
    header = [f"# {title}", "", f"Original source: {item.location}", "", f"Source SHA256: `{raw_hash}`", ""]
    if item.revision:
        header += ["Source revision: `" + json.dumps(item.revision, ensure_ascii=False, sort_keys=True) + "`", ""]
    for asset in assets:
        label = f"Page {asset['page']} image" if asset.get("page") else "Original asset"
        relative = Path(asset["path"]).name
        # The generated note lives beside its assets directory.
        link = asset["link"]
        header += [f"[{label}: {relative}]({link})", ""]
    warnings = list(dict.fromkeys(parsed["warnings"] + item.details.get("warnings", [])))
    partial = bool(parsed["partial"] or item.details.get("partial"))
    if warnings:
        header += ["## Extraction scope", ""] + [f"- {warning}" for warning in warnings] + [""]
    prefix = "\n".join(header) + "\n"
    offset = prefix.count("\n")
    text = prefix + parsed["text"].rstrip() + "\n"
    evidence = []
    for span in parsed["spans"]:
        evidence.append({**span, "line_start": span["line_start"] + offset, "line_end": span["line_end"] + offset, "hash_scope": "normalized_extracted_span_utf8"})
    meta = {"source": {"kind": "import", "source_id": source_id, "item_key": item.key, "location": item.location, "revision": item.revision, "sha256": raw_hash, **item.details},
            "evidence": {"kind": "source_extraction", "parser": parsed["parser"], "complete": not partial, "warnings": warnings, "spans": evidence, "assets": assets},
            "intake": {"version": 1, "generated": True, "body_sha256": digest(text.encode("utf-8"))}}
    return text.encode("utf-8"), (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sync_source(spec: str | dict, *, state_root: str | Path, output_root: str | Path, force: bool = False) -> dict:
    """Synchronize one independent source; never overwrite a maintainer's edits.

    force repeats conversion but does not bypass ownership, limits or revisions.
    Successful item checkpoints survive a later error; the source cursor advances
    only after a complete scan and all conversions succeed. Missing items remain
    intact and are reported, never inferred deleted from a partial listing.
    """
    spec = normalize(spec)
    limits = Limits.from_spec(spec.get("limits"))
    budget = Budget(limits)
    ident = source_identity(spec)
    state, output = Path(state_root).resolve(), Path(output_root).resolve()
    if state == output or inside(state, output):
        raise ValueError("state_root must be outside the published output_root")
    directory = _safe(state, ident)
    directory.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    result = {"status": "ok", "source_id": ident, "revision": None, "updated": 0, "unchanged": 0, "converted": 0, "preserved": [], "missing": [], "errors": [], "truncated": False, "output_root": str(output)}
    scan = {"complete": True, "revision": None, "warnings": []}
    with _lock(directory / "sync.lock"):
        journal_path = directory / "journal.json"
        journal = read_json(journal_path, {"version": 1, "source_id": ident, "items": {}})
        if journal.get("source_id") != ident or not isinstance(journal.get("items"), dict):
            raise ValueError("invalid source journal")
        # Resolve interrupted pair writes using exact old/new hashes only.
        for key, record in list(journal["items"].items()):
            pending = record.get("pending")
            if pending and _owned(output, pending, limits):
                journal["items"][key] = pending
            elif pending:
                recoverable = True
                for field in ("body", "metadata"):
                    info = pending[field]
                    actual = _file_hash(_safe(output, info["path"]), limits.output_chars * 8 + 128_000)
                    allowed = {info["sha256"], record.get(field, {}).get("sha256")}
                    staged = _safe(directory, pending["staged"][field])
                    if actual not in allowed or _file_hash(staged, limits.output_chars * 8 + 128_000) != info["sha256"]:
                        recoverable = False
                if recoverable:
                    for field in ("body", "metadata"):
                        write_atomic(_safe(output, pending[field]["path"]), _safe(directory, pending["staged"][field]).read_bytes())
                    journal["items"][key] = pending
        seen = set()
        try:
            for item in iter_source(spec, budget, scan, [state, output]):
                budget.check()
                key = digest(item.key)[:24]
                seen.add(key)
                raw_hash = digest(item.data)
                fingerprint = digest({"raw": raw_hash, "revision": item.revision, "options": {k: spec.get(k) for k in ("ocr", "caption")}, "limits": asdict(limits), "parser": "0.1"})
                old = journal["items"].get(key)
                body_rel = f"{ident}/{key}.md"
                meta_rel = f"{ident}/{key}.meta.json"
                body_path, meta_path = _safe(output, body_rel), _safe(output, meta_rel)
                if old and not _owned(output, old, limits) or not old and (body_path.exists() or meta_path.exists()):
                    result["preserved"].append(item.key)
                    scan["complete"] = False
                    continue
                if old and old.get("fingerprint") == fingerprint and old.get("complete") and not force:
                    result["unchanged"] += 1
                    continue
                try:
                    work = _safe(directory, f"work/{fingerprint}")
                    work.mkdir(parents=True, exist_ok=True)
                    raw_path = _safe(work, "original" + Path(item.name).suffix.lower())
                    if raw_path.exists() and _file_hash(raw_path, limits.file_bytes) != raw_hash:
                        raise IntakeError("staged original was modified")
                    if not raw_path.exists():
                        write_atomic(raw_path, item.data)
                    parsed = _parse(raw_path, spec, limits, budget)
                    result["converted"] += 1
                    caption = spec.get("caption")
                    if caption:
                        for asset in parsed["assets"]:
                            budget.check()
                            try:
                                generated = generate(caption if isinstance(caption, dict) else {}, task="image_caption", text=f"Describe the supplied original image for vLLM/Ascend/NPU/AI infrastructure reference. Preserve chart axes, units and visible uncertainty; do not infer benchmark results beyond visible content. Source: {item.location}. Page: {asset.get('page', 'image')}. OCR text: {parsed['text'][:12000]}", images=[Path(asset["path"])], allowed_refs=[item.location])
                                text = "## Native Agent image description" + (f" (page {asset['page']})" if asset.get("page") else "") + "\n\n" + generated["text"]
                                start = parsed["text"].count("\n") + 3 if parsed["text"] else 1
                                parsed["spans"].append({"line_start": start, "line_end": start + text.count("\n"), "sha256": digest(text.encode("utf-8")), "kind": "native_caption", "page": asset.get("page"), "asset_sha256": asset["sha256"], "generation": {k: v for k, v in generated.items() if k != "text"}})
                                parsed["text"] += ("\n\n" if parsed["text"] else "") + text
                                parsed["warnings"] = [warning for warning in parsed["warnings"] if not warning.startswith("image text requires")]
                            except GenerationPending as exc:
                                parsed["warnings"].append(str(exc))
                                parsed["partial"] = True
                        if not parsed["warnings"]:
                            parsed["partial"] = False
                    if len(parsed["text"]) > limits.output_chars:
                        raise ImportLimit("enriched output character budget reached")
                    asset_records = []
                    # Raw Markdown is an asset, not a second knowledge note.
                    # A non-.md extension prevents ordinary recursive mounts
                    # from indexing it again without its source sidecar.
                    asset_name = "original" + raw_path.suffix + (".source" if raw_path.suffix in {".md", ".markdown"} else "")
                    original = {"path": str(raw_path), "name": asset_name, "sha256": raw_hash}
                    selected_assets = [original] + [a for a in parsed["assets"] if a["sha256"] != raw_hash]
                    asset_bytes = 0
                    for asset in selected_assets:
                        budget.check()
                        asset_source = Path(asset["path"])
                        if not inside(asset_source, work):
                            raise ValueError("parser asset escaped its working directory")
                        asset_bytes += asset_source.stat().st_size
                        if asset_bytes > limits.total_bytes:
                            raise ImportLimit("converted asset byte budget reached")
                        name = re.sub(r"[^A-Za-z0-9._-]", "_", asset["name"])
                        relative = f"{ident}/assets/{asset['sha256']}/{name}"
                        target = _safe(output, relative)
                        if target.exists() and _file_hash(target, limits.total_bytes) != asset["sha256"]:
                            raise IntakeError("existing generated asset was modified")
                        if not target.exists():
                            write_atomic(target, asset_source.read_bytes())
                        asset_records.append({"path": relative, "link": f"assets/{asset['sha256']}/{name}", "sha256": asset["sha256"], **({"page": asset["page"]} if asset.get("page") else {})})
                    body, metadata = _render(item, ident, raw_hash, parsed, asset_records)
                    new = {"item_key": item.key, "fingerprint": fingerprint, "source_sha256": raw_hash, "revision": item.revision, "complete": not (parsed["partial"] or item.details.get("partial")), "body": {"path": body_rel, "sha256": digest(body)}, "metadata": {"path": meta_rel, "sha256": digest(metadata)}, "assets": asset_records}
                    # Recheck the existing pair after potentially lengthy OCR/native work.
                    if old and not _owned(output, old, limits):
                        result["preserved"].append(item.key)
                        scan["complete"] = False
                        continue
                    new["staged"] = {"body": f"work/{fingerprint}/generated.md", "metadata": f"work/{fingerprint}/generated.meta.json"}
                    write_atomic(_safe(directory, new["staged"]["body"]), body)
                    write_atomic(_safe(directory, new["staged"]["metadata"]), metadata)
                    journal["items"][key] = {**(old or {}), "pending": new}
                    write_json(journal_path, journal)
                    write_atomic(body_path, body)
                    write_atomic(meta_path, metadata)
                    journal["items"][key] = new
                    write_json(journal_path, journal)
                    result["updated"] += 1
                    if not new["complete"]:
                        scan["complete"] = False
                        result["errors"].extend({"item": item.key, "error": warning} for warning in parsed["warnings"] + item.details.get("warnings", []))
                except (IntakeError, GenerationPending, ValueError, OSError) as exc:
                    result["errors"].append({"item": item.key, "error": str(exc)})
                    scan["complete"] = False
            if scan["complete"]:
                result["missing"] = [record.get("item_key", key) for key, record in journal["items"].items() if key not in seen]
                journal["successful_revision"] = scan["revision"] or digest({key: journal["items"][key]["source_sha256"] for key in sorted(seen)})
                journal["successful_at"] = time.time()
                write_json(journal_path, journal)
        except (IntakeError, ValueError, OSError, KeyError) as exc:
            result["errors"].append({"error": str(exc)})
            scan["complete"] = False
        result["revision"] = journal.get("successful_revision")
        result["observed_revision"] = scan["revision"]
    result["status"] = "ok" if scan["complete"] else "partial"
    result["truncated"] = not scan["complete"]
    result["warnings"] = scan["warnings"]
    result["bytes_read"] = budget.bytes
    result["scanned_entries"] = budget.entries
    result["elapsed_seconds"] = round(time.monotonic() - budget.started, 3)
    return result


def sync_sources(config: Mapping, force: bool = False) -> dict:
    """Accept a standalone JSON-compatible configuration, not a service config."""
    if not config.get("state_root") or not config.get("output_root"):
        raise ValueError("standalone intake requires state_root and output_root")
    results = []
    for spec in config.get("sources", []):
        try:
            results.append(sync_source(spec, state_root=config["state_root"], output_root=config["output_root"], force=force))
        except (IntakeError, ValueError, OSError) as exc:
            results.append({"status": "error", "error": str(exc)})
    return {"status": "ok" if all(result["status"] == "ok" for result in results) else "partial", "sources": results, "output_root": str(Path(config["output_root"]).resolve())}

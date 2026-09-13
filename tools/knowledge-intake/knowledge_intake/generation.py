"""Hash-bound input and results for an independently operated native Agent.

This module does not launch an Agent, poll a chat, download a model or call a
model API. A native Agent can inspect the request's original images and return
its actual interpretation. Results are revision checked before acceptance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .common import ImportLimit, digest, inside, read_json, write_json


class GenerationPending(RuntimeError):
    pass


def request_record(task: str, text: str, images: Sequence[Path] = (), allowed_refs: Sequence[str] = (), max_output_tokens: int = 1000) -> dict:
    if len(text) > 32_000 or len(images) > 4 or len(allowed_refs) > 100:
        raise ImportLimit("native generation input budget exceeded")
    assets = []
    size = 0
    for path in images:
        size += path.stat().st_size
        if size > 16 * 1024 * 1024:
            raise ImportLimit("native generation image budget exceeded")
        assets.append({"path": str(path.resolve()), "sha256": digest(path.read_bytes())})
    record = {"task": task, "text": text, "images": assets, "allowed_refs": list(allowed_refs), "max_output_tokens": max_output_tokens}
    record["input_sha256"] = digest(record)
    return record


def accept_native_result(request: Mapping[str, Any], result: Mapping[str, Any]) -> dict:
    if result.get("input_sha256") != request.get("input_sha256"):
        raise ValueError("native generation input revision changed")
    for asset in request.get("images", []):
        path = Path(asset["path"])
        if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024 or digest(path.read_bytes()) != asset["sha256"]:
            raise ValueError("native generation image revision changed")
    text = result.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 32_000:
        raise ValueError("native generation must provide bounded nonempty text")
    refs = result.get("refs", [])
    if not isinstance(refs, list) or any(ref not in request.get("allowed_refs", []) for ref in refs):
        raise ValueError("native generation contains unknown source references")
    return {"text": text.strip(), "refs": refs, "input_sha256": request["input_sha256"],
            "provider": "native_agent", "model": result.get("model"), "usage": result.get("usage", {})}


def generate(config: Mapping[str, Any], *, task: str, text: str, images: Sequence[Path] = (),
             allowed_refs: Sequence[str] = (), max_output_tokens: int = 1000) -> dict:
    if config.get("provider", "native_agent") not in {"native", "native_agent"}:
        raise ValueError("intake uses native Agent results; no model service is started")
    if not 1 <= max_output_tokens <= 8192:
        raise ValueError("native generation output budget exceeded")
    directory = Path(str(config.get("directory") or ""))
    if not config.get("directory"):
        raise GenerationPending("native generation request directory is not configured")
    record = request_record(task, text, images, allowed_refs, max_output_tokens)
    ident = record["input_sha256"]
    directory.mkdir(parents=True, exist_ok=True)
    request_path = directory / f"{ident}.request.json"
    output = directory / f"{ident}.result.json"
    if not inside(request_path, directory) or not inside(output, directory):
        raise ValueError("generation result escapes request directory")
    write_json(request_path, record)
    if not output.is_file():
        raise GenerationPending(f"native generation pending: {request_path}")
    if output.stat().st_size > 128_000:
        raise ImportLimit("native generation response exceeds byte budget")
    return accept_native_result(record, read_json(output))

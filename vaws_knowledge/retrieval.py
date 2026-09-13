"""Small lexical complement and source excerpts for the existing vector index.

No model, persistent second index, query rewriting or applicability scoring.
Ranks are fused, never interpreted as confidence in a document's claims.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Sequence

from vaws_knowledge.local.backend import Hit
from vaws_knowledge.markdown import Document

_WORDS = re.compile(r"[a-z0-9_]+(?:[./+:-][a-z0-9_]+)*|[\u3400-\u9fff]+", re.I)
_CJK = re.compile(r"^[\u3400-\u9fff]+$")


def tokens(text: str) -> list[str]:
    """Keep code identifiers and adjacent Chinese characters searchable."""
    result: list[str] = []
    for word in _WORDS.findall(text.casefold()):
        if _CJK.fullmatch(word) and len(word) > 1:
            result.extend(word[i:i + 2] for i in range(len(word) - 1))
        else:
            result.append(word)
    return result


def lexical_search(text: str, documents: Sequence[Document], *, limit: int) -> list[Hit]:
    """BM25 over already loaded Markdown; exact names survive vector misses."""
    terms = set(tokens(text))
    if not terms or not documents:
        return []
    counts = [Counter(tokens(document.title + "\n" + document.content)) for document in documents]
    lengths = [sum(count.values()) for count in counts]
    average = sum(lengths) / max(len(lengths), 1) or 1
    frequencies = {term: sum(term in count for count in counts) for term in terms}
    hits: list[Hit] = []
    for document, count, length in zip(documents, counts, lengths):
        score = 0.0
        for term in terms:
            frequency = count[term]
            if frequency:
                inverse = math.log(1 + (len(documents) - frequencies[term] + .5) / (frequencies[term] + .5))
                score += inverse * frequency * 2.2 / (frequency + 1.2 * (.25 + .75 * length / average))
        if score:
            hits.append(Hit(document.uri, score, document.title, layer=document.layer))
    return sorted(hits, key=lambda hit: (-hit.score, hit.uri))[:limit]


def fuse(vector: Sequence[Hit], lexical: Sequence[Hit]) -> list[tuple[Hit, list[str]]]:
    """Reciprocal rank fusion, with one contribution per URI per retriever."""
    scores: dict[str, float] = {}
    selected: dict[str, Hit] = {}
    methods: dict[str, list[str]] = {}
    for method, hits in (("vector", vector), ("lexical", lexical)):
        seen: set[str] = set()
        rank = 0
        for hit in hits:
            if hit.uri in seen:
                continue
            seen.add(hit.uri)
            rank += 1
            scores[hit.uri] = scores.get(hit.uri, 0) + 1 / (60 + rank)
            selected.setdefault(hit.uri, hit)
            methods.setdefault(hit.uri, []).append(method)
    result: list[tuple[Hit, list[str]]] = []
    for uri in sorted(scores, key=lambda key: (-scores[key], key)):
        hit = selected[uri]
        result.append((Hit(uri, scores[uri], hit.title, hit.excerpt, hit.layer, hit.content), methods[uri]))
    return result


def source_excerpt(raw: str, query: str, *, max_chars: int = 600) -> dict:
    """Quote a bounded matching source window with one-based Markdown lines."""
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = raw.splitlines()
    wanted = set(tokens(query))
    if not lines:
        return {}
    weights = [len(wanted.intersection(tokens(line))) for line in lines]
    best = max(range(len(lines)), key=lambda index: weights[index])
    start = max(0, best - 2)
    end = min(len(lines), best + 5)
    excerpt = "\n".join(lines[start:end])
    truncated = len(excerpt) > max_chars
    column_start = 1
    if truncated:
        # Keep the matching line even when the preceding context is very long.
        start = best
        excerpt = "\n".join(lines[start:end])
        if len(excerpt) > max_chars:
            positions = [match.start() for match in _WORDS.finditer(lines[best])
                         if wanted.intersection(tokens(match.group()))]
            offset = max(0, (positions[0] if positions else 0) - max_chars // 3)
            column_start = offset + 1
            excerpt = excerpt[offset:offset + max_chars]
            end = start + len(excerpt.splitlines())
    return {"text": excerpt, "line_start": start + 1, "line_end": end,
            "column_start": column_start,
            "content_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "hash_scope": "utf8_text_with_normalized_newlines",
            "truncated": truncated}

# Reference retrieval measurements

Status: dated implementation evidence (2026-09-13); not a hardware guarantee.

These runners exercise ordinary files and the public query implementation.
They do not claim that repeated source text is a relevance benchmark or that a
memory vector fixture establishes native OpenViking performance. Native MCP,
OpenViking and FastEmbed acceptance is recorded separately by the integration
owner.

## Reproduce

From the package checkout:

```powershell
uv run --no-project python tests/performance/benchmark_legacy_lexical.py --output .vaws-local/performance/legacy.json
uv run --no-project python tests/performance/evaluate_reference_fixture.py --output .vaws-local/performance/retrieval.json
uv run --no-project python tests/performance/benchmark_reference_catalog.py --sizes 10000 100000 --queries 40 --output .vaws-local/performance/catalog.json
```

The capacity runner creates real temporary Markdown files from all 65 checked-in
VA corpus entries, adds unique markers, builds the actual catalog, changes one
file, verifies incremental reuse, and calls actual `query` and `maintain`.
It reports the initial incomplete query, build, scan, update, search, query,
output size, source reads, SQLite size and Python peak working set separately.
Its maintenance phase uses `MemoryBackend`; native embedding cost is excluded.
Temporary files are removed on completion. Large first builds take minutes.

## Observed CPU capacity

Windows 11 build 26200, Python 3.13.12, 32 logical CPUs; development host has
approximately 64 GiB RAM. The target remains 16 GiB without a discrete GPU.
These are measured process-memory requirements on the development host, not a
claim of testing a physical 16 GiB machine. Other implementation work was active
during measurements; these are not isolated laboratory timings.

| Measured phase | 10,000 notes, final repeat | 100,000 notes, extension |
|---|---:|---:|
| Authored UTF-8 text | 39.38 MiB | 393.84 MiB |
| First incomplete public query | 137.61 ms | 150.67 ms |
| First offline build | 89.15 s | 776.92 s |
| Unchanged refresh | 0.946 s | 10.586 s |
| One-file changed refresh | 1.144 s | 9.158 s |
| Warm catalog p50 / p95 | 35.09 / 51.05 ms | 171.06 / 227.40 ms |
| Public query p50 / p95, vectors disabled | 56.52 / 73.59 ms | 180.88 / 249.65 ms |
| Maximum public query | 88.76 ms | 266.08 ms |
| Maximum successful original reads per query | 8 | 8 |
| Maximum response bytes | 13,120 | 13,120 |
| SQLite on disk | 181.97 MiB | 1.77 GiB |
| Peak Python working set before vector fixture | 78.62 MiB | 276.49 MiB |
| Peak working set including memory vector fixture | 195.59 MiB | 1.57 GiB |

Each warm series has 40 samples over identifier and NPU-domain queries. The
100k data contains repeated vocabulary, which makes broad queries match many
documents. Both unchanged refreshes read zero body bytes and parse zero notes;
the changed refreshes parse exactly one note. Windows newline conversion means
on-disk source bytes differ slightly from authored UTF-8 text.

The 10k p95 target of 100 ms passes for the catalog and the complete public
lexical route. The 100k extension is measured, not hidden behind a smaller
corpus: broad retrieval costs about 250 ms, and metadata scanning takes about
10.6 seconds. First builds and integrity audits belong to maintenance. The
catalog alone should be budgeted at approximately 0.5 GiB resident memory and
2 GiB disk for this 100k workload; repair temporarily retains an additional
complete catalog generation. Native vector storage and processes need their
own measured budget.

Actual unchanged `maintain(force=True)` on the final 10k repeat took 1.459 s.
The complete 100k run began before the integration owner stopped force-wakeup
from running the health audit. That run measured 239.31 s initial maintenance
and 113.60 s unchanged forced maintenance with the old audit behavior. Those
100k maintenance times are retained as evidence of the identified cost, not
reported as final unchanged behavior. The subsequent 10k repeat verifies the
updated path, including its real directory scan and receipt reuse. No native
100k embedding throughput or final 100k forced-maintenance timing is claimed.

## Scoring baseline and quality regression

The retained whole-corpus lexical algorithm, with enrichment cleared, took
median 12.30 ms for 65 notes, 191.61 ms for 1,000 and 2,020.84 ms for 10,000
over three samples. This excludes filesystem scanning and vectors. An earlier
design probe observed 15.29 / 232.60 / 2,953.74 ms; the runnable baseline makes
the workload and current timings reproducible instead of treating one probe as
an SLA.

The checked-in fixture contains ten authored VA domain notes and thirteen
queries: ACLGraph, HCCL, NIXL PD, Triton UB, Kimi K3/KDA, ACLNN dtype, HBM
attribution, NPU theoretical-versus-measured basis, version conditions and one
explicit no-evidence case. These are regression scenarios, not verified device
claims or independent held-out annotations. No VAWS startup/coordinator note
is used to establish business relevance.

| Same-fixture ablation | Without generated metadata | Source-bound aliases/topics |
|---|---:|---:|
| Scored questions | 12 | 12 |
| Recall@8 / MRR / nDCG | 0.75 / 0.75 / 0.75 | 1.00 / 1.00 / 1.00 |
| Checked source spans and hashes | 14/14 | 18/18 |
| Explicit no-evidence abstention | 1/1 | 1/1 |
| Query p95, vectors disabled | 11.14 ms | 11.72 ms |

This is an unenriched-catalog ablation, not a comparison against an old package
version. Query reports retain degraded/incomplete diagnostics because vectors
are deliberately unavailable. Missing labels stay unknown; repeated hits
cannot inflate nDCG. Tests separately cover stale aliases, malformed scopes,
table headers, code clipping, distant conditions and exact multi-span positions.

## Maintenance API and failure boundaries

- `refresh_catalog(config, force=False, extra_documents=None)` is the sole normal
  writer. `force` hashes existing sources, while unchanged fingerprints still
  avoid extraction. The report contains complete `changed_uris`, `deleted_uris`,
  `previous_snapshot`, `snapshot`, body reads, parses, counts and errors.
- A snapshot is an opaque `epoch:revision` string. A new database gets a new
  epoch; comparing just revision numbers is invalid. Vector receipt consumers
  must check both their indexed snapshot and the report's previous snapshot
  before consuming a delta. Imported shared vectors remain distribution-owned.
- `extra_documents`, when supplied, is a complete iterator of the active
  prepared shared collection. Replacement and retirement of old imported rows
  share one SQL transaction; any iterator failure rolls it back. `None` does
  not re-read shared material, and an empty iterator removes only imported
  derived rows. The release owner supplies source-validated, public-prepared
  documents and reuses an unchanged release pointer.
- `search_catalog` reads a snapshot; `get_catalog_document(s)` fetches selected
  references. `shared_current` lets search use the caller's single observed
  release pointer. Query validates returned originals. Topic preference does
  not hide cross-topic evidence; explicit maintenance `selection.mode=only`
  is a content filter, not authorization. `all-topics` and `topic:NAME` are
  optional text conveniences, not new ordinary tool parameters.
- `repair_catalog(config, extra_documents=None, limits=None)` explicitly builds
  a new bounded database and atomically replaces `reference-catalog.json`.
  Defaults are 100,000 notes, 1 GiB source bytes and 1,800 seconds. Existing
  databases/WAL files and active reader transactions are preserved. Failure or
  pointer contention leaves the old pointer active; the report says whether a
  switch occurred. Repair is never invoked by query or provider initialization.
  Old generations remain available as backups; storage is not silently deleted.
- `export_catalog` streams portable source-bound metadata and exact source
  context. It is **not** a public redaction boundary. Public callers build from
  the package-prepared copy and validate every field.
- `evaluate(config, cases, limit=8)` uses public query by default and supports
  exact-reference grades 0–4, unknown labels, no-evidence cases, evidence checks,
  categories, latency and output size. It does not certify source claims.

The ordinary MCP surface remains `knowledge_query`, `knowledge_explain` and
`knowledge_capture`. Normal query has a 20-result ceiling and defaults to 4,800
excerpt characters. Without a catalog, fallback has a 128-note / 1 MiB / 100 ms
scan budget and reports incomplete; it never builds an index. A read of one
reference is bounded at 4 MiB and its metadata at 256 KiB, including files that
grow after a stat call. Oversized/unavailable sources remain unknown and intact.

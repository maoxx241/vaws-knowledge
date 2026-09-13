# vaws-knowledge

Local Markdown reference notes for vLLM-Ascend development, with CPU retrieval
through OpenViking and optional public contribution and shared releases.

Knowledge helps the Agent reuse experience. Lookup and capture are optional:
ordinary work needs no knowledge checklist, structured form or extra completion
step. Results are references, not instructions or applicability decisions. Use
current evidence and judgment; a review or release does not prove a hardware claim.

## Read and capture

`knowledge_query(text, limit=8)` finds related notes, `knowledge_explain(ref)`
reads the original, and `knowledge_capture(title, content)` saves a local note.
Capturing the same title updates that local note.
A title and non-empty Markdown body are enough. Keep known conditions, versions,
evidence and uncertainty in the prose. No frontmatter, fixed headings, runtime
coordinates, verification label or task association is required.

Install Python 3.11 or newer and the package:

```sh
python -m pip install -e .
vaws-knowledge prepare --project /path/to/project
vaws-knowledge server --config /path/to/project/.vaws-local/knowledge/service.json
```

Workspace installation calls `prepare` automatically. It prepares the CPU model,
bundled notes and indexes before reporting readiness. After a valid query or
successful MCP capture, the service maintains them in the background. Connecting,
listing tools, pinging and closing an unused provider do not start maintenance,
create a retrieval backend, or contact the network. A standalone installation can use the same command;
it creates local configuration without enabling public contribution.

```sh
vaws-knowledge capture --title "Graph replay observation" \
  --content "Eager passed; graph replay differed after the input layout changed."
vaws-knowledge query --text "graph replay input layout"
vaws-knowledge query --ref "REFERENCE_RETURNED_BY_QUERY"
```

Shared, project and candidate notes are searched together by relevance. Their
location and recorded context remain visible; there is no trust tier or automatic
condition verdict. A missing or unavailable result means unknown and does not
block independent development.

Markdown files retain the original content. MCP capture saves locally without
waiting for retrieval startup or indexing. Background maintenance reconciles
added, edited and deleted files and periodically checks actual content and vectors.
Queries use the ready index without waiting for downloads or repairs. Explain
and native summary capture do not activate maintenance. A reconnect reuses the
saved check and audit deadlines instead of revalidating all vectors. While a
knowledge connection is active and the backend is available, the hourly audit
detects losses that ordinary incremental reconciliation cannot see. Without an
active connection, overdue work resumes at the next query/capture or explicit
`prepare`; there is no unattended hourly guarantee. Shared updates preserve project and candidate
files. Configured summary hooks save locally even when public sharing is off;
sharing itself follows the publishing configuration. Reuse an existing useful
summary for capture instead of writing another one.

Bundled and configured Markdown remains searchable alongside the active shared
release; installing a smaller release does not hide the packaged notes.
A retrieved shared note can be read through
`knowledge_explain(ref)` just like a local note. The package handles indexing
and active shared versions internally.

`VAWS_KNOWLEDGE_CONFIG` selects storage and backend configuration;
`VAWS_KNOWLEDGE_STATE` selects local runtime state. The local OpenViking instance
uses CPU embedding on loopback. `VAWS_KNOWLEDGE_EMBEDDING_CACHE` can supply an
existing model cache; preparation downloads an uncached model. Background
embedding and OpenViking children use an independent empty stdin, so a Windows
MCP reader cannot block their interpreter startup. Windows children stay hidden.
See [the service reference](vaws_knowledge/server/README.md) for setup details.

## Optional maintenance

Project and local notes can be edited as ordinary Markdown. For an explicit
consolidation task, `vaws-knowledge skill` reads the optional
`curate-knowledge` guidance. It helps preserve conditions and unresolved
differences without prescribing a required workflow. Install it for native
discovery with `vaws-knowledge skill --install-dir <client-skill-directory>`.
Ordinary lookup, capture and task completion need no skill.

## Public contribution and shared updates

Public sharing follows existing authorization and configuration. The package
prepares a redacted public copy while preserving the private source, and handles
configured submission retries. The public corpus uses Markdown/redaction checks
and **human review and merge**. Local and shared observations remain reference
material regardless of publication status.

Shared release synchronization is enabled by default, independently of public
upload permission. For explicitly requested contribution setup,
`vaws-knowledge publishing configure --config PATH` creates or reuses a
contribution fork. `--read-only` disables contribution and keeps release sync
without a fork or GitHub login. Existing
private candidates are not bulk uploaded when sharing is enabled. Ordinary
development does not need a fork, publishing commands or a wait for PR review.

See [publishing setup](docs/publishing.md) and [public contribution](docs/contribution.md).
These maintenance operations are separate from normal Agent work.
The [native-client table](docs/publishing.md#native-client-summaries) distinguishes
automatic final-response capture from MCP support; Kimi Code currently has MCP
and session support without a native final-text summary hook.

The distribution module builds dense OVPack releases from fixed Git commits and
verifies imports before switching the active shared version. Failed updates keep
the prior version. MCP handles configured retries and synchronization internally.
See [distribution](docs/distribution.md); detailed formats belong to the package,
not note authors.

## Retrieval evidence and independent maintenance

Queries fuse the existing vector ranking with lexical matches from mounted
Markdown. Exact code identifiers and Chinese text remain searchable while the
vector service is pending; the result still reports degraded/unavailable when
that route fails. Each source URI contributes once per route. Relevance scores
are reciprocal ranks, not truth or applicability confidence.

Hits include a matching source window, one-based Markdown lines, clipping
information, and the SHA256 of UTF-8 text with normalized newlines. Shared-pack
hits identify their indexed snapshot and source revision when available.
`knowledge_explain` still reads the original. Local source changes can make a
later read differ; the hash identifies what this query actually observed.

For a separate maintenance task, `python -m vaws_knowledge health --config PATH`
returns a local worklist (first 50 findings; `--limit` changes only output size).
No model or external source is called. Mechanical hints cover exact duplicate
Markdown with matching recorded context, note age, unavailable sources and
changes to relative links inside mounted roots since observation. Only a
rebuildable cache is written. Age and lookup failures do not establish that a
claim is stale or false. External and unrecorded sources remain unchecked.

Active knowledge maintenance refreshes the worklist at its deadline or a change
wakeup. It reuses unchanged parsed records and reports; its failures never
change index readiness. An independent maintainer can use the existing
`curate-knowledge` skill for semantic decisions and authorized note edits.
Ordinary task agents have no added tool call or completion step. No autonomous
LLM, scheduler, deletion, merging, promotion or public publication is enabled.

Repeated native final-response events retain the first timestamp and provenance,
skip duplicate writes/contribution queueing, and preserve maintainer edits.

The design borrows rank fusion and source evidence from
[WeKnora](https://github.com/Tencent/WeKnora/blob/17f893865d4d8337f7e0bf942c6931a8ce7a08c1/internal/application/service/knowledgebase_search_fusion.go),
and incremental/source-aware maintenance from
[TeamAI](https://github.com/Tencent/teamai-cli/blob/6dc1b9919ef1856717c381d6559bb7738089075e/src/wiki-engine/code-knowledge/code-incremental.ts).
Both remain research references, with no runtime dependency or additional Agent
obligations.

## Validation

Local tests cover Markdown capture/query, index reconciliation, public redaction,
submission and prebuilt distribution. Windows coverage includes UTF-8 pipes,
cross-drive paths, process and file-lock handling. Native OpenViking and dense
distribution tests are opt-in and need the model cache described in
`tests/test_openviking_local.py` and `tests/distribution/test_native_chain.py`.
Set `VAWS_KNOWLEDGE_LIVE_OV=1` to run native OpenViking tests; the distribution
test has its own documented opt-in. Test fixtures are not hardware evidence.

The installed package version identifies the current interface. Agent tools and
the packaged reference notes use the same Markdown path. Retired structured
corpus and automated-review interfaces have been removed.

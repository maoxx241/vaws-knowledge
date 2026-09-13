# Knowledge capability implementation plan

Status: planned implementation and acceptance record (2026-09-13); not a runtime contract

## Objective and scope

Implement all twelve capabilities discussed after the TeamAI / WeKnora review,
with pre-release breaking changes where they reduce total user cost. This is
not satisfied by adding interfaces, documenting future features, or delivering
only the easiest subset. The existing nine VAWS design principles govern the
implementation. Detailed user annotations, if supplied separately, must be
reconciled into this record before final acceptance.

The previous 0.6.0 work is a baseline, not completion of this objective. Its
authoritative package baseline is `e16d87287f7db51ca96efc945a9514e4146131d6`.
Research references remain the fixed TeamAI `6dc1b9919ef1856717c381d6559bb7738089075e`
and WeKnora `17f893865d4d8337f7e0bf942c6931a8ce7a08c1` revisions linked in the
workspace's earlier adoption report.

## Detailed user annotations and domain scope

The annotations were received on 2026-09-13 and supersede narrower assumptions
in the initial research. The knowledge library serves **vLLM-Ascend development**:
vLLM, Ascend NPU, AI and infrastructure are the primary knowledge domains.
VAWS implementation experience is not the library's purpose. Existing private
notes remain intact, but default sources, topics, digests and quality examples
focus on the development domain.

- External intake is a separately installable tool, decoupled from VAWS and the
  knowledge MCP. Its output is ordinary Markdown/assets and optional source
  metadata, consumable through normal mounts. It has no `vaws_knowledge` import
  or dependency. Parser/network dependencies do not enter the base MCP package.
- PR experience intake is limited to `vllm-project/vllm` and
  `vllm-project/vllm-ascend`; VAWS PRs are engineering-validation evidence only.
- Prefer the user's installed **Grok Bot** for topics, associations, digests,
  independent research and multimodal interpretation. This is the desktop app
  with a cloud computer, distinct from the Grok Build coding CLI.
- Target machine: **16 GB RAM, Windows, no discrete GPU**. No new local
  multimodal embedding model. Prefer agent-native vision; any optional OCR
  adapter must be light, on demand and outside MCP initialization/query.
- Code maps must demonstrate useful evidence while bounding scanning, parsing,
  storage and resident memory. They need not depend on Cursor's internal index.
- Evaluation scope includes **all VAWS tools**, consolidating existing PR and
  runtime evidence into a separate engineering-validation archive and filling
  missing reproducible checks. Existing valid measurements are reused with
  their actual revisions and limitations; they are not VA domain knowledge.

## User-visible outcome

Ordinary tasks retain optional `knowledge_query`, `knowledge_explain`, and
`knowledge_capture`. A title and Markdown body remain sufficient. They do not
choose parsers, chunk policies, source identities, maintenance jobs, topic
schemas, model prompts, or release steps. Knowledge remains reference material;
generated pages, usage counts, age and review do not confer truth or authority.

Maintainers can import and synchronize selected sources, inspect static code
relationships, and run bounded independent research and curation. The package
handles mechanical work and records actual outcomes. Independent agents make
open judgments and produce source-linked Markdown or hash-bound enrichment.
No generic agent runtime is added to the ordinary query path.

## Architecture and data contracts

1. Markdown remains the recoverable body. Existing optional `.meta.json`
   sidecars hold source, conditions and evidence. An optional `retrieval`
   section can hold aliases and topics bound to the normalized body SHA256.
   Authors need not write this section; maintenance tools generate it. Stale
   generated enrichment is ignored and appears in the maintenance worklist.
2. A rebuildable local catalog stores normalized bodies, section/line spans,
   term postings and enrichment fingerprints. Changes are reconciled by the
   maintenance owner. Queries reuse a snapshot, validate selected source
   evidence, and report incomplete/pending state when applicable. No query
   rereads and retokenizes the complete corpus. Cold fallback has an explicit
   bound. Original embedding lookup may remain; no per-query generative LLM,
   OCR, alias generation or ingestion is introduced.
3. Source adapters produce stable source IDs, original locations, content
   hashes, revision/cursor observations, assets, and normalized Markdown.
   Converted source material is separate from curated notes. An interrupted
   fetch does not advance the successful cursor or imply source deletion.
   Local imports, URLs, Git and PR material share this contract.
4. Static code maps record definitions, imports, calls and registrations with
   file, revision, lines and extraction kind. Dynamic or heuristic edges are
   labelled. Document associations retain explicit evidence and unresolved
   candidates; name matching cannot establish runtime behavior or a conflict.
5. Independent curation consumes bounded source changes and existing summaries,
   produces topics, aliases, cases and digests, and applies results only against
   their observed source revisions. Semantic changes preserve readable history
   and can be undone. Network/model failures retain existing knowledge.
6. Project/topic selection is configuration for content relevance, not a new
   identity or access-control system. Cross-topic retrieval remains possible
   without requiring an ordinary task to change roles.
7. Shared publication carries the same useful reference information. Public
   export uses a package-prepared, redacted source, never raw private sidecars.
   A release binds Markdown and its derived reference catalog to one Git SHA
   and switches them together. Local paths/credentials must not leak through
   aliases, assets, relations or metadata. Existing valid packs and Git history
   are reused where compatible; a new format version may require rebuilding.

## Complete capability acceptance matrix

| ID | Required capability | Evidence required for completion |
|---|---|---|
| K01 | External import and incremental synchronization | Actual local Markdown/HTML/PDF/Office and selected URL/Git import; repeat yields no unnecessary conversion; changed input updates; interrupted sync retains cursor and existing content; source is retrievable/explainable. |
| K02 | PR changes become reusable experience | A real public PR is fetched with pinned base/head and complete or explicitly bounded evidence; independent curation produces a source-linked case retaining uncertainty; replay avoids duplicate cases. |
| K03 | Maintained topic pages and navigation | An independent agent organizes multiple existing notes into a source-linked topic page; query finds it; backlinks/affected-source changes work; no default authority boost or mandatory reading. |
| K04 | Code and interface map | Actual Python and Ascend C++ source extraction with revision/line evidence, cross-language registration examples and bounded navigation; dynamic endpoints stay unknown/static, never claimed as executed. |
| K05 | Document/code/experience association maintenance | A changed symbol or source identifies linked claims/skills/cases; unrelated material stays unchanged; removed/renamed/unavailable source and heuristic candidates remain distinguishable. |
| K06 | Offline question/alias generation | A real independent generation run produces source-bound aliases; paraphrased queries reach original evidence; source edits invalidate stale aliases; no generative call at query time. |
| K07 | Context-aware retrieval | Realistic Markdown headings, conditions, tables and fences retain necessary context within measured output limits; multiple spans have accurate positions; large blocks show clipping and explain access. |
| K08 | Searchable images and scans | Actual OCR and image-description generation on sample material; indexed text points to original image/page/report; unavailable providers report a bounded failure; original structured measurements remain accessible. |
| K09 | Retrieval regression evaluation | Checked-in representative query/evidence set; actual public query path measurements for relevance, source/context coverage, latency and output size; no-result and version-conflict cases; compare baseline with implementation. |
| K10 | Cross-task maintenance digest | Existing summaries and evidence generate a bounded digest and candidate recurring topics; source links and covered interval are visible; no transcript scraping or per-task extra reporting. |
| K11 | Independent topic research/curation | A real native agent runs a bounded maintenance job, gathers evidence, returns validated edits, and updates knowledge; interruption/cost limits/status/history work independently of ordinary tasks. |
| K12 | Project/topic content selection | Two configured topic selections retrieve the intended material; cross-topic requests remain possible; selection survives shared release build/import and does not become permission or truth. |
| K13 | VAWS-wide evaluation archive and reproducible coverage | Map every current tool family to versioned evidence, runnable checks and limitations; consolidate existing relevant PR reports; fill identified verification gaps without presenting old results as current execution. |

History, source provenance, public redaction, three-tool usability, and the
inactive-provider contract are cross-cutting acceptance requirements.

## Delivery batches and ownership

The numbered batches are delivery boundaries, not optional priority tiers.
All must finish. Independent implementation starts only after this design and
the module contracts have been circulated.

1. **Reference catalog and retrieval**: incremental catalog, structured excerpts,
   source-bound aliases/topics, content selection, evaluation runner and scale
   benchmarks. Own `catalog`, `context`, `evaluation`, retrieval/query/Markdown
   integration and their tests.
2. **Independent source ingestion and media**: local/URL/Git/PR adapters, common normalized
   source/asset storage, incremental journal, PDF/Office/OCR/vision capability
   adapters, realistic format fixtures. Own the separately packaged
   `tools/knowledge-intake/` and its tests; the base package only mounts outputs.
3. **Code and relationships**: Python/C++ static map, registration links,
   document associations, affected-source worklist and bounded graph navigation.
   Own `code_map`/`relations` and their tests.
4. **Curation and publication integration**: Grok Bot independent-agent execution,
   question/topic/case/digest workflows, revision checks/history, source-bound
   model generation, public catalog release and atomic consumption. Own curation,
   provider/lifecycle/CLI/distribution integration and related tests.
5. **Consumer and final acceptance**: installed package pin/config/help, existing
   maintenance Skill updates and projections, live representative end-to-end
   demonstrations, scale evaluation, VAWS-wide evidence archive and coverage,
   native Windows/Linux/macOS checks, final
   per-requirement audit. Keep coordinator/source-workspace changes with their
   existing owners and integrate current upstream pins.

Each coherent implementation gets a reviewable PR with actual validation.
Tests from mocks establish contracts only; live parser/model/agent/retrieval
claims require actual execution. PRs may be stacked while dependencies develop.

## Performance and failure budgets

- Unused provider initialize/list/ping/EOF: zero new scanner, network, model,
  indexing, or maintenance activity.
- Repeated query: no full-corpus body reads/tokenization, no new generative
  calls, no ingestion/curation waits. Preserve bounded source validation and
  actual degradation in responses.
- Baseline observed locally on 2026-09-13: lexical scoring alone took median
  15.29 ms for 65 real notes (266 KB), 232.60 ms for a synthetic 1,000-note
  corpus and 2,953.74 ms for 10,000 notes made from the real text (three runs;
  excludes disk scanning and vector retrieval). Preserve a reproducible runner
  and remeasure the final implementation rather than treating these as SLAs.
- Initial acceptance target: 10,000-note warm lexical catalog p95 <= 100 ms
  on the development host, zero unchanged body re-parses, bounded top-k source
  reads, and no unexplained regression on the real corpus. Measure cold build,
  incremental update, memory/disk use and vector service separately. Tighten or
  revise targets with evidence, not by reducing functionality or hiding costs.
- Default query response has a total text budget; preserve line/section/asset
  references when clipping. Measure output size with retrieval quality.
- Imports/curation have byte/document/time/output bounds, cancellation and
  resumable successful checkpoints. No recursive maintenance-agent spawning or
  automatic unbounded source discovery. Heavy optional parsers/providers load
  only for corresponding configured maintenance work.

## Progress

- [x] Revalidated package and consumer worktrees; reused the task's prepared workspace.
- [x] Coordinated ownership with the two parallel VAWS tasks.
- [x] Identified existing whole-corpus query cost and shared metadata loss.
- [x] Reconcile detailed user annotations and VA development domain scope.
- [ ] Complete batches 1-5 and all K01-K13 acceptance evidence.
- [ ] Audit actual merged/installed state against this full scope.

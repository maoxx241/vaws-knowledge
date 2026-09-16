# [参考] DSA CP local metadata fixed-capacity Triton（PR #16629）

- **日期**: 2026-09-16
- **状态**: OPEN / blocked / reference-only
- **阅读方式**: `gh` + PR body/files（未跑 NPU）

## Pinned（本轮）

| 字段 | 值 |
|---|---|
| PR | https://github.com/vllm-project/vllm-ascend/pull/16629 |
| 标题 | `[Performance][DSA] Eliminate per-step re-JIT of the local metadata build with a fixed-capacity Triton kernel` |
| state | OPEN；MERGEABLE；BLOCKED |
| base / head | `714dd1d1ba032972e6a734254a816ca13c302da1` / `70540b56fd5ff19314292376429cfaf9cd7fe625` |
| 规模 | +369 / −25，**3 files** |
| 对比 | https://github.com/vllm-project/vllm-ascend/compare/714dd1d1ba032972e6a734254a816ca13c302da1...70540b56fd5ff19314292376429cfaf9cd7fe625 |

### CI

| Check | 结论 |
|---|---|
| DCO / PR create / main | **pass** |
| ci-gate / pre-commit | **fail** |

## Themes

1. Fixed-capacity grid keyed by `max_num_seqs`（防逐步 re-JIT）
2. Fused local_query_start_loc / local_seq_lens / start_pos
3. Ascend int32→fp32 vector-path lowering CLAIM
4. 与 #16542 fixed-capacity indices **分案对照**

## Retrieval queries

1. dsa_local_metadata fixed capacity Triton 16629
2. eliminate re-JIT num_reqs bucket DSA CP
3. do_not_specialize COMPUTE_START_POS Ascend
4. PR 16629 vs 16542 Triton capacity patterns
5. head 70540b56 blocked dsa_cp wiring

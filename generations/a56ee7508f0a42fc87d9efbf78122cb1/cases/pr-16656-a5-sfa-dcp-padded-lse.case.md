# Case: A5 SFA DCP — padded-index LSE + empty local shards

- **日期**: 2026-09-18
- **状态**: OPEN not-draft / MERGEABLE / **BLOCKED** / reference-only
- **来源 PR**: https://github.com/vllm-project/vllm-ascend/pull/16656 （author `recky-c`；labels: `module:tests`, `ready-a5`, `ready-precise`）
- **Pinned（本轮 gh 2026-09-18）**: base `c7ca0b676b9668535f467b78cff1274a4ddb63b2` · head `60c6c32ab18de4b8b97f643bfb6a568290bd373c`

## 修订说明 / Revision notes（2026-09-18，Asia/Shanghai）

- 新建 case；单 commit `fix: handle padded and empty A5 SFA DCP shards`（`60c6c32a…`）。
- 规模 +112/−2，**7 files**；MERGEABLE **BLOCKED**。
- 文件面（VERIFIED）：`csrc/.../sparse_flash_attention_*_mla.h`、`attention/context_parallel/sfa_cp.py`、`device/hardware_profile.py`、相关 UT/e2e ops test。
- 根因 CLAIM：A5 SFA DCP decode 稀疏 index 前缀有效、尾部 `-1` padding；用 KV length 作 softmax 范围会污染 per-rank 归一化。
- 能力 CLAIM：advertise `SFA_DCP_REPLICATED_INDEXER` on A5；**不**声称 C8；目标 GLM5.2 W4A8、SFA C8 与 indexer C8 **均关闭**、TP8/DCP8/EP、eager、无 MTP/PD（body CLAIM）。
- CI 摘要（VERIFIED sample）：pre-commit/main/PR create/cpu-ut **SUCCESS**；a5 selected tests 仍进行中 → overall **BLOCKED**。

## Trigger — 何时想起本 case

讨论 **A5 Sparse Flash Attention + DCP**、padded sparse indices、LSE/softmax 合并错误、或 empty local key shards 时。

## Preconditions / environment signals

- base `main` @ `c7ca0b67…`；head @ `60c6c32a…`。
- 依赖关系 CLAIM：全模型实验曾叠加 #16325 indexer metadata（tested rev `ec6e301d…`）——**本 PR 不含**那些改动。
- 现有 custom op 已接受 PA_BSND + `return_softmax_lse` → 无需 host-tiling 变更（CLAIM）。

## Observed failure pattern（若有）

- Incorrect per-rank normalization / LSE when sparse index has `-1` pad beyond valid prefix；empty local selection with nonempty cache（CLAIM）。

## Fix direction（仅限本 PR，附条件）

1. Bound sparse-mode-0 LSE by actual valid index prefix。
2. Zero-init skipped queries（output + softmax max/sum；LSE → −inf 重建 CLAIM）。
3. Init `n2Size` before output init；prefill KV/RoPE views contiguous after packed DCP gather。
4. Advertise `SFA_DCP_REPLICATED_INDEXER` on A5 with platform capability check。

**条件**: head `60c6c32ab18de4b8b97f643bfb6a568290bd373c`；OPEN blocked；C8 **非**本 PR 范围。

## Do-not-overgeneralize

- A5 + 特定关闭 C8 配置 ≠ 全 SFA/C8/PD 路径已修。
- 勿把 #16325 或其他 indexer PR 的 pin 并入本 case。
- 数值修复 CLAIM ≠ 本轮 VERIFIED NPU。

## Evidence links

- PR: https://github.com/vllm-project/vllm-ascend/pull/16656
- Compare: https://github.com/vllm-project/vllm-ascend/compare/c7ca0b676b9668535f467b78cff1274a4ddb63b2...60c6c32ab18de4b8b97f643bfb6a568290bd373c

## Retrieval queries

1. A5 SFA DCP padded index LSE empty shards Ascend
2. PR 16656 sparse flash attention softmax valid prefix
3. SFA_DCP_REPLICATED_INDEXER hardware_profile A5
4. GLM5.2 W4A8 TP8 DCP8 SFA C8 disabled eager
5. sparse_flash_attention_kernel_mla padded -1 indices

# Case: A5 Kimi K3 — MRv1/MRv2 DCP、DSpark ACLGraph、strided Flash MLA/GQA（draft）

- **日期**: 2026-09-15
- **状态**: OPEN **draft** / MERGEABLE / **BLOCKED** / reference-only；超大 PR（+53k/−207，220 files）
- **来源 PR**: https://github.com/vllm-project/vllm-ascend/pull/16468 （author `maoxx241`；labels: `documentation`, `module:tests`, `module:ops`, `module:core`）
- **Pinned（本轮 gh）**: base `26f1363f7180dfcbeac1230679976cede6010fc8` · head `8a293f09830a5c55bd4fc5c2e2219f0edcd59443`

## 修订说明 / Revision notes（2026-09-15，Asia/Shanghai）

- 新建 case；**draft** 全程标注；验收数字与拓扑来自 PR body/评论 → **CLAIM**（本轮未复跑 NPU）。
- 与 #16157（K3 DSpark ACL Graph padding/Query-T on `releases/v0.26.0rc`）主题相关但 **分案**：本 PR 面向 main / A5 Flash MLA·GQA·DCP 扩展。
- CI：ci-gate/pre-commit **fail**；CI 非 acceptance gate（PR 自述 CLAIM）。
- B035 AsStrided 100-layer backing-size 边界与 `gpu_memory_utilization=0.88` workaround → **CLAIM**，非根因修复。

## Trigger — 何时想起本 case

讨论 **Kimi K3 on Ascend A5** 时：

- MRv1/MRv2 + **DCP**（含 draft 复制 KV / DCP1 vs target DCP2）；
- DSpark **ACLGraph** replay（target+draft）；
- strided **Flash MLA / GQA**；PD 跨节点 KV；
- 与 rc0.26 `#16157` padding 契约的差异（勿混 pin）。

## Preconditions / environment signals

- base `main` @ `26f1363f…`；head `feat/rfc16464-a5-kimi-k3-flash-mla` @ `8a293f0…`。
- 体量：csrc `a5_mla_common` / `flash_mla_with_kvcache` / MoE `causal_conv1d_v2` + Python attention/spec_decode/worker 大范围改动（VERIFIED 文件列表）。
- vLLM pin（PR body）：`84030bbe3d74d99bad477a3d2e37a973ccd8865c`（CLAIM）。

## Observed failure pattern（若有）

- Feature/RFC 落地；已知 CLAIM：B035 AsStrided 窄边界失败 → 调低 memory util 规避。

## Fix direction（仅限本 PR，附条件 — 高层）

1. A5 Flash MLA/GQA 内核与 tiling 路径（大量 `csrc/attention/a5_mla_common`、`flash_mla_with_kvcache`）。
2. DSpark proposer / graph contract + MRv2 speculator/device metadata（Python）。
3. DCP 配置：GQA draft 可 DCP1 + replicated KV；target DCP2（CLAIM 验收矩阵）。
4. PD：跨节点 KV transfer + full-graph replay 叙述（CLAIM）。
5. CPU UTs：graph contract、DCP slots、replicated KV、Flash cache（VERIFIED 存在测试文件）。

**条件**: head `8a293f09830a5c55bd4fc5c2e2219f0edcd59443`；**OPEN draft** + blocked；CI fail。

## Do-not-overgeneralize

- Draft / 超大 diff → 禁止当已合入行为。
- 验收表（GPQA/GSM8K/acceptance%）为作者环境 CLAIM，非本轮 VERIFIED。
- 禁止与 #16157 rc 分支 pin 混用。
- memory-util workaround ≠ 通用 >16GiB 修复。

## Evidence links

- PR: https://github.com/vllm-project/vllm-ascend/pull/16468
- Compare: https://github.com/vllm-project/vllm-ascend/compare/26f1363f7180dfcbeac1230679976cede6010fc8...8a293f09830a5c55bd4fc5c2e2219f0edcd59443
- Related padding case #16157: https://github.com/vllm-project/vllm-ascend/pull/16157
- Launch/results comment (PR): https://github.com/vllm-project/vllm-ascend/pull/16468#issuecomment-5666315412

## Retrieval queries

1. A5 Kimi K3 Flash MLA GQA DCP DSpark ACLGraph MRv1 MRv2
2. PR 16468 draft head 8a293f0 feat/rfc16464-a5-kimi-k3-flash-mla
3. replicated draft KV DCP1 target DCP2 DP4 TP8 acceptance
4. B035 AsStrided backing-size gpu_memory_utilization 0.88 workaround
5. a5_mla_common flash_mla_with_kvcache causal_conv1d_v2

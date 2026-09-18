# Topic: A5 SFA DCP padded-index LSE / empty shards

- **日期**: 2026-09-18
- **关联 case**: [`cases/pr-16656-a5-sfa-dcp-padded-lse.case.md`](../cases/pr-16656-a5-sfa-dcp-padded-lse.case.md)
- **PR**: https://github.com/vllm-project/vllm-ascend/pull/16656
- **Pins**: base `c7ca0b67…` · head `60c6c32a…` · OPEN BLOCKED

## 要点

- **VERIFIED**：7-file kernel/host/UT 面；+112/−2；cpu-ut/pre-commit pass sample。
- **CLAIM**：按 valid index 前缀约束 LSE；empty local shards 零初始化；advertise A5 `SFA_DCP_REPLICATED_INDEXER`；非 C8。
- **UNVERIFIED**：全模型数值；本轮未跑 NPU。

## 勿过度推广

- 关闭 C8 的验证目标 ≠ 启用 C8；勿合并 #16325 pin。

## Retrieval queries

1. A5 SFA DCP padded LSE empty local keys
2. PR 16656 sparse flash attention DCP merge
3. SFA_DCP_REPLICATED_INDEXER Ascend A5

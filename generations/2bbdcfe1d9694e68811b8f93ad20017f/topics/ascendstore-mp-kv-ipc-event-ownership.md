# [参考] AscendStore multiprocess KV transfer / IPC / Event 所有权（PR #15832）

- **日期**: 2026-09-14
- **状态**: OPEN **draft** / blocked / reference-only（非正确性背书；draft 条件有效）
- **阅读方式**: 本轮委托元数据 + 证据条目（未跑 NPU；未改上游）

## Pinned（本轮委托证据）

| 字段 | 值 |
|---|---|
| PR URL | https://github.com/vllm-project/vllm-ascend/pull/15832 |
| 标题 | `[KV Pool][Feature] Run AscendStore KV transfers in worker subprocesses` |
| 状态 | **OPEN**；**isDraft=true**；mergeable_state **blocked** |
| base / head 分支 | `main` / `feat/ascend-store-transfer-mp` |
| **base SHA** | `660c4582aa580ce98edc9b681bb6ff6d03153575` |
| **head SHA** | `cea32e97544a2f3f73d5c5310569077912963bd0` |
| 作者 | `ChenZhuo888` |
| 规模 | +4965 / −15，**32 files** |
| 对比 | https://github.com/vllm-project/vllm-ascend/compare/660c4582aa580ce98edc9b681bb6ff6d03153575...cea32e97544a2f3f73d5c5310569077912963bd0 |

### CI / checks（委托）

| Check | 结论 |
|---|---|
| DCO | **pass** |

## 修订说明 / Revision notes（2026-09-14，Asia/Shanghai）

1. 新建 topic：mp KV transfer 架构要点 + Event 所有权 CLAIM。
2. 默认 `use_multiprocess=false` — 开启需显式配置。
3. Draft：合入形态与 hang 全版本复现 **UNVERIFIED**。

## Motivation（CLAIM）

- RFC #14143：transfer-process 削减进程内 AscendStore transfer 线程的 Python/GIL 争用。

## Architecture（VERIFIED from 委托证据）

1. **开关**：`kv_connector_extra_config.use_multiprocess`，**default false**。
2. **职责划分**：Worker = scheduling + KV ownership；child = backend I/O、registration、key construction。
3. **包** `.../ascend_store/mp/`：`process.py`（Popen+pipe）、`client.py`（ZMQ DEALER）、`npu_ipc.py`（export/import storage specs）、adapter / service / transfer / tp_mismatch / mooncake_backend。
4. **`pool_worker.py`**：读 `use_multiprocess`；init 顺序 KV-events vs backend；`_get_worker_global_rank` 跨 DP×TP×PP×PCP。
5. **Mooncake mp**：`register_memory(address, length, "npu:<device_index>")`；CI pin `mooncake-transfer-engine-npu` `0.3.11.post1` → `0.3.12.post1`（Mooncake #2191）。

## Event ownership（CLAIM experiment + design）

1. 跨进程 imported NPU Event：在 HCCL-associated producer 之后 synchronize **hung**；source-process Event OK。
2. **最终设计**：Events 留在 Worker；child `None` Event slots；本地 wait 后再 RPC → happens-before。
3. **Precedents CLAIM**：LMCache-Ascend HCCL channel；SGLang Ascend HiCache — Events 留 owning process。

## Coverage / tests（CLAIM vs VERIFIED）

| 项 | 分层 |
|---|---|
| block / key-layerwise / GVA-layerwise；hybrid/Mamba；compressed；TP mismatch；Mooncake SSD | **CLAIM** 覆盖；SSD e2e 环境缺 → **UT only** |
| UT ~454 local | **CLAIM** 数量 |
| e2e one-card **A2** Mooncake + two-card **A3** Memcache | **CLAIM**；硬件不可互换叙述 |
| 可能减少 transfer/compute overlap | **CLAIM**；无测吞吐 |
| Hang 是否全 CANN/torch-npu 可复现 | **UNVERIFIED** |
| Draft merge readiness | **UNVERIFIED** |

## Applicability boundaries

- 参考：AscendStore mp 可选路径；Event 留 Worker 的设计意图。
- 勿：默认开启；把 draft 当生产；混用 A2/A3/310P 结论；把 hang 实验当全版本定理。

## Related

- Case: [`cases/pr-15832-ascendstore-multiprocess-kv-transfer.case.md`](../cases/pr-15832-ascendstore-multiprocess-kv-transfer.case.md)
- PR: https://github.com/vllm-project/vllm-ascend/pull/15832
- RFC: https://github.com/vllm-project/vllm-ascend/pull/14143

## Retrieval queries

1. `AscendStore mp KV IPC Event ownership Worker child None slots`
2. `use_multiprocess kv_connector_extra_config default false`
3. `ascend_store mp process Popen ZMQ DEALER npu_ipc`
4. `Mooncake register_memory npu:device_index 0.3.12.post1`
5. `PR 15832 draft RFC 14143 transfer-process GIL`

## Explicit uncertainty markers

- `[DRAFT-BLOCKED]` OPEN draft。
- `[CLAIM-HANG-EXPERIMENT]` Event hang 叙述。
- `[CLAIM-THROUGHPUT]` 无测 overlap 数字。
- `[HW-NOT-EQUIV]` A2≠A3≠其它。
- `[UNVERIFIED-MERGE]` readiness 未知。

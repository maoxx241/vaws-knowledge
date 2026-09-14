# Case: AscendStore KV 传输放入 worker 子进程（draft）

- **日期**: 2026-09-14
- **状态**: OPEN **draft** / mergeable_state blocked / reference-only
- **来源 PR**: https://github.com/vllm-project/vllm-ascend/pull/15832 （OPEN draft；author `ChenZhuo888`）
- **Pinned（本轮委托证据）**: base `660c4582aa580ce98edc9b681bb6ff6d03153575` · head `cea32e97544a2f3f73d5c5310569077912963bd0`

## 修订说明 / Revision notes（2026-09-14，Asia/Shanghai）

- 新建 case：**draft** 条件全程标注；merge readiness **UNVERIFIED**。
- Event 所有权实验与「最终设计 Events 留在 Worker」标 **CLAIM**（实验叙述）；包结构 / 开关 / Mooncake pin 等可核对点标 VERIFIED。
- **勿**把 A2 Mooncake e2e 与 A3 Memcache e2e 叙述外推为全硬件等价；310P 未在本 PR 证据中等同。

## Trigger — 何时想起本 case

讨论 **AscendStore** KV connector 时：

- 进程内 transfer 线程的 Python/GIL 争用；
- `kv_connector_extra_config.use_multiprocess`；
- 跨进程 NPU Event synchronize hang（HCCL-associated producer）；
- Mooncake `register_memory(..., "npu:<device_index>")` 与 engine 版本 pin。

## Preconditions / environment signals

- 仓库：`vllm-project/vllm-ascend`；base `main` @ `660c4582aa580ce98edc9b681bb6ff6d03153575`；head `feat/ascend-store-transfer-mp` @ `cea32e97544a2f3f73d5c5310569077912963bd0`。
- RFC 语境：#14143 transfer-process（**CLAIM** 动机）。
- 开关：`use_multiprocess` **default false**（可选）。
- Draft / blocked → 行为可能继续变。

## Observed failure pattern（若有）

- **[CLAIM experiment]** 跨进程 import 的 NPU Event 在 HCCL-associated producer 之后 synchronize **hung**；同进程 Event OK → 设计选择：Events 留 Worker；child 侧 `None` Event slots；本地 wait 后再 RPC 形成 happens-before。
- **[CLAIM precedents]** LMCache-Ascend HCCL channel + SGLang Ascend HiCache：Events 留在 owning process。

## Fix direction（仅限本 PR，附条件）

1. 可选 `kv_connector_extra_config.use_multiprocess`（默认 false）。
2. Worker 保留 scheduling / KV ownership；child 负责 backend I/O、registration、key construction。
3. 包 `.../ascend_store/mp/`：`process.py`（Popen+pipe）、`client.py`（ZMQ DEALER）、`npu_ipc.py`（export/import storage specs）、adapter/service/transfer/tp_mismatch/mooncake_backend。
4. `pool_worker.py` 读开关；init 顺序 KV-events vs backend；`_get_worker_global_rank` 跨 DP×TP×PP×PCP。
5. Mooncake mp：`register_memory(address, length, "npu:<device_index>")`；CI pin `mooncake-transfer-engine-npu` `0.3.11.post1` → `0.3.12.post1`（Mooncake #2191）。
6. 覆盖面 CLAIM：block / key-layerwise / GVA-layerwise、hybrid/Mamba、compressed、TP mismatch、Mooncake SSD（SSD e2e 环境缺 → 仅 UT）。

**条件**: head `cea32e97544a2f3f73d5c5310569077912963bd0`；**OPEN draft** + blocked；默认关闭 multiprocess。

## Do-not-overgeneralize

- Draft ≠ 可生产默认开启。
- Hang 复现未宣称覆盖全部 CANN/torch-npu（**UNVERIFIED**）。
- 「可能减少 transfer/compute overlap」无测吞吐（CLAIM）。
- A2 one-card Mooncake ≠ A3 two-card Memcache ≠ 其它卡型。

## Evidence links

- PR: https://github.com/vllm-project/vllm-ascend/pull/15832
- Compare: https://github.com/vllm-project/vllm-ascend/compare/660c4582aa580ce98edc9b681bb6ff6d03153575...cea32e97544a2f3f73d5c5310569077912963bd0
- RFC ref: https://github.com/vllm-project/vllm-ascend/pull/14143

## Retrieval queries

1. `AscendStore use_multiprocess KV transfer worker subprocess`
2. `npu_ipc export import storage specs ZMQ DEALER ascend_store mp`
3. `NPU Event hang HCCL cross-process synchronize Worker ownership`
4. `mooncake-transfer-engine-npu 0.3.12.post1 register_memory npu:device`
5. `PR 15832 draft feat/ascend-store-transfer-mp cea32e97`

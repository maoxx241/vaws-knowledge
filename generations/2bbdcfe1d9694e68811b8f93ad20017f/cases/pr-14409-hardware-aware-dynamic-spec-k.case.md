# Case: Hardware-aware dynamic speculative decoding（physical K）

- **日期**: 2026-09-14
- **状态**: OPEN not-draft / blocked / reference-only；**head 仍在移动 — 每轮需重 pin**
- **来源 PR**: https://github.com/vllm-project/vllm-ascend/pull/14409 （OPEN；author `momo609`；labels: `module:tests`, `module:core`）
- **Pinned（本轮委托证据）**: base `6b9b83968f5ea81aa11750fc19ef4bd1eb383321` · head `2aacea2f2641da45d91074a4b79f38b32fa196ce`（相对更早 `cff3def…` **已移动**）

## 修订说明 / Revision notes（2026-09-14，Asia/Shanghai）

- 新建 case；注明 **pin-latest-each-run**：head 相对历史 tip 已变，下次维护必须重取 SHA。
- Checks：DCO **fail**、ci-gate **fail**、pre-commit **fail**；PR create/main **pass**。
- 性能收益、CI 失败根因、运行时 NPU 增益 → **UNVERIFIED**。
- 追随 #15098（CLAIM 关系）。

## Trigger — 何时想起本 case

讨论 **动态控制下一轮物理 draft 长度 K**（batch/acceptance hybrid），使更短 K 减少 draft 算力；以及：

- `DynamicSpecConfig` policy `confidence_budget` | `hardware_aware`；
- DFlash/DSpark + `physical_k_scope` / ACLGraph capture widths；
- `AdaptiveDraftKController` 默认阈值与 hysteresis / probe。

## Preconditions / environment signals

- 仓库：`vllm-project/vllm-ascend`；base @ `6b9b83968f5ea81aa11750fc19ef4bd1eb383321`；head `2aacea2f2641da45d91074a4b79f38b32fa196ce`。
- Methods：**limited to dspark / dflash**（VERIFIED 委托）。
- Graph：ACLGraph capture 使用 `physical_k_capture_scope` / `extend_capture_descriptors`；PIECEWISE adaptive-verification gate wrapper。
- CI 多项 fail → 合入前证据不足。

## Observed failure pattern（若有）

- PR 动机为 **feature**（动态 K），非单一 crash log；本轮无独立现场日志。

## Fix direction（仅限本 PR，附条件）

1. `dynamic_spec.py`：`resolve_physical_k`；`AdaptiveDraftKController`；defaults `min_batch=8`, `acceptance=0.6`, `low_steps=4`, `high_steps=2`, `probe_interval=32`。
2. `DynamicSpecConfig`：policy `confidence_budget|hardware_aware`；`physical_k` object；methods 限 dspark/dflash。
3. `hardware_aware.py`（+711）：capture_k widths、`physical_k_scope`、buffers、PIECEWISE adaptive-verification gate wrapper、DFlash/DSpark mixins。
4. DFlash/DSpark inherit PhysicalK mixins；`propose` 包 `physical_k_scope`；ACLGraph capture：`physical_k_capture_scope` / `extend_capture_descriptors`。
5. Model runner：`adaptive_verification_gate_wrapper`；UTs：policy + runtime widths。
6. **CLAIM**：controller 仅 CPU acceptance；hysteresis + 周期性 full-width probes。

**条件**: head `2aacea2f2641da45d91074a4b79f38b32fa196ce`（可能继续移动）；OPEN blocked；DCO/ci-gate/pre-commit fail。

## Do-not-overgeneralize

- 禁止把 dynamic K 说成已验证 NPU 吞吐提升（**UNVERIFIED**）。
- 禁止外推到非 dspark/dflash 方法。
- 禁止假设 head 固定；须 **pin-latest-each-run**。
- 追随 #15098 ≠ #15098 行为已在本 PR 复述完整。

## Evidence links

- PR: https://github.com/vllm-project/vllm-ascend/pull/14409
- Compare: https://github.com/vllm-project/vllm-ascend/compare/6b9b83968f5ea81aa11750fc19ef4bd1eb383321...2aacea2f2641da45d91074a4b79f38b32fa196ce
- Related: https://github.com/vllm-project/vllm-ascend/pull/15098
- Spec decoding docs: https://docs.vllm.ai/projects/ascend/en/latest/user_guide/feature_guide/speculative_decoding.html

## Retrieval queries

1. `hardware_aware dynamic speculative decoding physical_k AdaptiveDraftKController`
2. `DynamicSpecConfig confidence_budget hardware_aware dspark dflash`
3. `physical_k_scope physical_k_capture_scope extend_capture_descriptors ACLGraph`
4. `PR 14409 head 2aacea2f moved pin-latest-each-run`
5. `adaptive_verification_gate_wrapper PIECEWISE min_batch acceptance probe_interval`

# [参考] Hardware-aware physical K / ACLGraph（PR #14409）

- **日期**: 2026-09-14
- **状态**: OPEN / blocked / reference-only；**head 移动中 — 每轮重 pin**
- **阅读方式**: 本轮委托元数据 + 证据条目（未跑 NPU）

## Pinned（本轮委托证据）

| 字段 | 值 |
|---|---|
| PR URL | https://github.com/vllm-project/vllm-ascend/pull/14409 |
| 标题 | `feat: add hardware-aware dynamic speculative decoding` |
| 状态 | **OPEN**；not draft；**blocked**；labels: `module:tests`, `module:core` |
| **base SHA** | `6b9b83968f5ea81aa11750fc19ef4bd1eb383321` |
| **head SHA（本轮）** | `2aacea2f2641da45d91074a4b79f38b32fa196ce` |
| 相对更早 head | `cff3def…`（**已过时**；勿当最新） |
| 作者 | `momo609` |
| 规模 | +1864 / −65，**15 files** |
| 对比 | https://github.com/vllm-project/vllm-ascend/compare/6b9b83968f5ea81aa11750fc19ef4bd1eb383321...2aacea2f2641da45d91074a4b79f38b32fa196ce |

### CI / checks（委托）

| Check | 结论 |
|---|---|
| DCO | **fail** |
| ci-gate | **fail** |
| pre-commit | **fail** |
| PR create | **pass** |
| main | **pass** |

## 修订说明 / Revision notes（2026-09-14，Asia/Shanghai）

1. 新建 topic；显式 **pin-latest-each-run**（head 已从 `cff3def…` 移到 `2aacea2f…`）。
2. CLAIM：追随 #15098；动态控制 next-iter 物理 draft 长度 K。
3. NPU 性能增益与 CI 失败根因 **UNVERIFIED**。

## Intent（CLAIM）

- 通过 batch/acceptance hybrid 动态控制下一轮物理 draft 长度 K；更短 K → 更少 draft compute。
- 追随 https://github.com/vllm-project/vllm-ascend/pull/15098。

## Mechanism（VERIFIED from 委托证据）

1. **`dynamic_spec.py`**：`resolve_physical_k`；`AdaptiveDraftKController`；defaults：`min_batch=8`, `acceptance=0.6`, `low_steps=4`, `high_steps=2`, `probe_interval=32`。
2. **`DynamicSpecConfig`**：policy `confidence_budget|hardware_aware`；`physical_k` object；methods **limited to dspark/dflash**。
3. **`hardware_aware.py`（+711）**：capture_k widths；`physical_k_scope`；buffers；PIECEWISE adaptive-verification gate wrapper；DFlash/DSpark mixins。
4. **Proposers**：DFlash/DSpark inherit PhysicalK mixins；`propose` wraps `physical_k_scope`；ACLGraph capture 用 `physical_k_capture_scope` / `extend_capture_descriptors`。
5. **Model runner**：`adaptive_verification_gate_wrapper`；UTs policy + runtime widths。

### CLAIM（非本轮独立证明）

- Controller 仅用 **CPU acceptance**；hysteresis + periodic full-width probes。

### UNVERIFIED

- NPU 实际性能增益。
- CI（DCO / ci-gate / pre-commit）fail 根因与修复进度。
- Head 是否继续移动 → 下次必须重 pin。

## Applicability boundaries

- 参考：dspark/dflash + hardware_aware / confidence_budget 动态物理 K 与 ACLGraph capture 宽度扩展。
- 勿：外推其它 speculative methods；把 OPEN+failing checks 当已验证性能特性；缓存过期 head SHA。

## Related

- Case: [`cases/pr-14409-hardware-aware-dynamic-spec-k.case.md`](../cases/pr-14409-hardware-aware-dynamic-spec-k.case.md)
- PR: https://github.com/vllm-project/vllm-ascend/pull/14409
- Related #15098: https://github.com/vllm-project/vllm-ascend/pull/15098
- Spec docs: https://docs.vllm.ai/projects/ascend/en/latest/user_guide/feature_guide/speculative_decoding.html
- ACL Graph: https://docs.vllm.ai/projects/ascend/en/latest/developer_guide/Design_Documents/ACL_Graph.html

## Retrieval queries

1. `vllm-ascend PR 14409 hardware-aware dynamic speculative decoding`
2. `AdaptiveDraftKController resolve_physical_k min_batch 8 acceptance 0.6`
3. `hardware_aware.py physical_k_capture_scope PIECEWISE gate`
4. `DFlash DSpark PhysicalK mixin propose physical_k_scope`
5. `14409 DCO fail ci-gate fail head 2aacea2f pin-latest`

## Explicit uncertainty markers

- `[HEAD-MOVING]` 须每轮重 pin。
- `[CI-FAILING]` DCO / ci-gate / pre-commit。
- `[CLAIM-FOLLOW-15098]` 关系未深读 #15098。
- `[UNVERIFIED-NPU-PERF]` 无测增益。
- `[METHODS-LIMIT]` 仅 dspark/dflash。

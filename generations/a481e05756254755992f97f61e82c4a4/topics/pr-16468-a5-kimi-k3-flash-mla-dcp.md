# [参考] A5 Kimi K3 Flash MLA/GQA + DCP + DSpark ACLGraph（PR #16468）

- **日期**: 2026-09-15
- **状态**: OPEN **draft** / blocked / reference-only；超大变更集
- **阅读方式**: `gh` 元数据 + PR body/file churn（未跑 NPU；未装模型）

## Pinned（本轮）

| 字段 | 值 |
|---|---|
| PR | https://github.com/vllm-project/vllm-ascend/pull/16468 |
| 标题 | `[Feat][A5] Kimi K3 MRv1/MRv2 DCP, DSpark ACLGraph and strided Flash MLA/GQA` |
| state | OPEN；**isDraft=true**；MERGEABLE；BLOCKED |
| base / head | `26f1363f7180dfcbeac1230679976cede6010fc8` / `8a293f09830a5c55bd4fc5c2e2219f0edcd59443` |
| 规模 | +53270 / −207，**220 files** |
| 对比 | https://github.com/vllm-project/vllm-ascend/compare/26f1363f7180dfcbeac1230679976cede6010fc8...8a293f09830a5c55bd4fc5c2e2219f0edcd59443 |

### CI（摘要）

| Check | 结论 |
|---|---|
| DCO / PR create / main | **pass** |
| ci-gate / pre-commit | **fail** |

## Themes（索引）

1. **Flash MLA/GQA kernels（A5）** — `csrc/attention/a5_mla_common`, `flash_mla_with_kvcache`
2. **DSpark ACLGraph** — proposer/graph contract UTs；MRv1/MRv2 replay CLAIM
3. **DCP** — target/draft 不同 DCP；replicated draft KV
4. **PD** — 跨节点 KV + acceptance CLAIM
5. **分案** — rc `#16157` padding/Query-T ≠ 本 main/A5 扩展

## VERIFIED / CLAIM / UNVERIFIED

- **VERIFIED**：draft/blocked；pins；file churn 热点；测试文件存在。
- **CLAIM**：DP4/TP8/DCP 验收表；PD 128/128；B035 workaround；vLLM `84030bbe…`。
- **UNVERIFIED**：合入形态；CI 绿；本环境复现；MRv2 GQA pending 项。

## Retrieval queries

1. Kimi K3 A5 Flash MLA GQA DSpark ACLGraph draft 16468
2. DCP replicated draft KV MRv1 MRv2 DP4 TP8
3. a5_mla_common vf_basic_block flash_mla_with_kvcache
4. PR 16468 vs 16157 rc0.26 padding separate cases
5. head 8a293f0 rfc16464 blocked draft

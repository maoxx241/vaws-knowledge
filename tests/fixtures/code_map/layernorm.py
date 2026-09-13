"""Small static fixture following vLLM-Ascend's Gemma RMSNorm binding pattern.

Actual upstream acceptance uses the original repository, not this fixture.
"""
raise AssertionError("source inspection must never execute this module")

import torch


class AscendGemmaRMSNorm:
    def forward_oot(self, x):
        x, _ = torch.ops._C_ascend.npu_gemma_rms_norm(x, self.weight, self.variance_epsilon)
        return x

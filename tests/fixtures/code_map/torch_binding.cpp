// Minimal syntax fixture for actual PyTorch/Ascend registration idioms.
namespace vllm_ascend {
std::tuple<at::Tensor, at::Tensor> npu_gemma_rms_norm(
    const at::Tensor& x, const at::Tensor& gamma, double epsilon) {
    at::Tensor y, rstd;
    EXEC_NPU_CMD(aclnnGemmaRmsNorm, x, gamma, epsilon, y, rstd);
    return std::tuple<at::Tensor, at::Tensor>(y, rstd);
}
}

#ifndef SKIP_GEMMA
TORCH_LIBRARY_EXPAND(CONCAT(_C, _ascend), ops) {
    ops.def("npu_gemma_rms_norm(Tensor x, "
            "Tensor gamma, float epsilon=1e-6) -> (Tensor y, Tensor rstd)");
    ops.impl("npu_gemma_rms_norm", torch::kPrivateUse1,
             &vllm_ascend::npu_gemma_rms_norm);
}
#endif

// EXEC_NPU_CMD(aclnnFakeComment, x);
const char* example = "ops.impl(\"fake_string\", fake)";

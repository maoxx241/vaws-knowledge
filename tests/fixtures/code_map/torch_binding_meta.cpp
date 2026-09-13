namespace vllm_ascend { namespace meta {
at::Tensor npu_gemma_rms_norm_meta(const at::Tensor& x) { return x; }
} }
TORCH_LIBRARY_IMPL_EXPAND(CONCAT(_C, _ascend), Meta, ops) {
    ops.impl("npu_gemma_rms_norm", &vllm_ascend::meta::npu_gemma_rms_norm_meta);
}

"""Knowledge outcome interpretation; storage and redaction stay shared."""
from functools import wraps
from contextvars import ContextVar
from vaws_diagnostics import get_recorder

_ACTIVE = ContextVar("knowledge_diagnostic_operation", default=None)


def capture_failure(error, category="internal_error"):
    op = _ACTIVE.get()
    if op is not None:
        op.fail(category, exception=error)


def observed(name, *, level="INFO"):
    def decorate(function):
        @wraps(function)
        def call(*args, **kwargs):
            with get_recorder("vaws-knowledge").operation(name, level=level) as op:
                token = _ACTIVE.set(op)
                try:
                    result = function(*args, **kwargs)
                finally:
                    _ACTIVE.reset(token)
                if type(result) is int and result != 0:
                    op.fail("returned_failure", exit_code=result)
                elif isinstance(result, dict) and isinstance(result.get("status"), str) and result["status"] in {"pending", "unavailable", "partial", "failed"}:
                    if result.get("reason"):
                        op.fail("maintenance_unavailable", retryable=True)
                    else:
                        op.event("WARNING", "knowledge.incomplete", status=result["status"])
                elif isinstance(result, tuple) and len(result) == 2 and result[1] is True:
                    op.fail(result[0].get("error", "tool_error") if isinstance(result[0], dict) else "tool_error")
                elif isinstance(result, dict) and isinstance(result.get("error"), dict):
                    code = result["error"].get("code")
                    op.fail("protocol_response", error_code=code,
                            classification="caller" if type(code) is int and code in {-32700, -32600, -32601, -32602} else "unknown")
                return result
        return call
    return decorate

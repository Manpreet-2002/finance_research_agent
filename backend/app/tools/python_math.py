"""Deterministic bounded Python math executor for intermediate analytics."""

from __future__ import annotations

import ast
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import multiprocessing
import os
try:  # pragma: no cover - platform-specific import guard
    import resource
except Exception:  # pragma: no cover - non-posix fallback
    resource = None  # type: ignore[assignment]
from time import perf_counter
import traceback
from typing import Any

import statistics

_MAX_CODE_CHARS = 12_000
_MAX_IO_BYTES = 400_000
_DEFAULT_TIMEOUT_SECONDS = 2.0
_MAX_TIMEOUT_SECONDS = 5.0
_MAX_ADDRESS_SPACE_BYTES = 512 * 1024 * 1024
_MAX_FILE_BYTES = 5 * 1024 * 1024
_MAX_OPEN_FILES = 128
_MAX_PROCESSES = 32
_MAX_STD_STREAM_CHARS = _MAX_IO_BYTES
_ALLOWED_MODULES: dict[str, Any] = {"math": math, "statistics": statistics}
_ALLOWED_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "BaseException": BaseException,
    "bool": bool,
    "Exception": Exception,
    "RuntimeError": RuntimeError,
    "TypeError": TypeError,
    "ValueError": ValueError,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "print": print,
    "__import__": __import__,
}
_DISALLOWED_CALL_NAMES: set[str] = {
    "eval",
    "exec",
    "open",
    "compile",
    "input",
    "__import__",
    "locals",
    "globals",
    "vars",
    "dir",
    "help",
    "breakpoint",
    "quit",
    "exit",
}


def execute_python_math(
    *,
    code: str,
    inputs: dict[str, Any] | None,
    function_name: str = "compute",
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Execute user-provided deterministic Python math function under strict bounds."""
    normalized_code = code.strip()
    if not normalized_code:
        raise ValueError("Python math tool requires non-empty 'code'.")
    if len(normalized_code) > _MAX_CODE_CHARS:
        raise ValueError(
            f"Python math code too large ({len(normalized_code)} chars > {_MAX_CODE_CHARS})."
        )

    safe_inputs = dict(inputs or {})
    input_json = json.dumps(_to_jsonable(safe_inputs), sort_keys=True)
    if len(input_json.encode("utf-8")) > _MAX_IO_BYTES:
        raise ValueError("Python math inputs exceed size bound.")

    _validate_math_code(normalized_code)
    timeout = _normalize_timeout(timeout_seconds)
    code_hash = _sha256_hex(normalized_code)
    input_hash = _sha256_hex(input_json)

    started = perf_counter()
    worker_result = _run_worker(
        code=normalized_code,
        inputs=safe_inputs,
        function_name=function_name,
        timeout_seconds=timeout,
    )
    elapsed_ms = (perf_counter() - started) * 1000.0

    output = _to_jsonable(worker_result.get("output"))
    output_json = json.dumps(output, sort_keys=True)
    stdout_text = str(worker_result.get("stdout") or "")
    stderr_text = str(worker_result.get("stderr") or "")
    exit_code = int(worker_result.get("exit_code") or 0)

    if len(output_json.encode("utf-8")) > _MAX_IO_BYTES:
        raise ValueError("Python math output exceeds size bound.")
    if len(stdout_text.encode("utf-8")) > _MAX_IO_BYTES:
        raise ValueError("Python math stdout exceeds size bound.")
    if len(stderr_text.encode("utf-8")) > _MAX_IO_BYTES:
        raise ValueError("Python math stderr exceeds size bound.")

    return {
        "code_hash": code_hash,
        "input_hash": input_hash,
        "function_name": function_name,
        "timeout_seconds": timeout,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": round(elapsed_ms, 3),
        "output": output,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "exit_code": exit_code,
    }


def _run_worker(
    *,
    code: str,
    inputs: dict[str, Any],
    function_name: str,
    timeout_seconds: float,
) -> Any:
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue[dict[str, Any]] = ctx.Queue(maxsize=1)
    process = ctx.Process(
        target=_math_worker_entry,
        args=(queue, code, inputs, function_name, timeout_seconds),
    )
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join()
        raise TimeoutError(
            f"Python math execution exceeded timeout ({timeout_seconds}s)."
        )
    if queue.empty():
        raise RuntimeError(
            "Python math worker returned no result "
            f"(exit_code={process.exitcode})."
        )
    payload = queue.get()
    payload["exit_code"] = process.exitcode
    if not payload.get("ok"):
        error = str(payload.get("error") or "Python math worker failed.")
        stdout_text = str(payload.get("stdout") or "").strip()
        stderr_text = str(payload.get("stderr") or "").strip()
        details: list[str] = [error]
        if stderr_text:
            details.append(f"STDERR: {stderr_text}")
        if stdout_text:
            details.append(f"STDOUT: {stdout_text}")
        raise RuntimeError(" | ".join(details))
    return payload


def _math_worker_entry(
    queue: multiprocessing.Queue[dict[str, Any]],
    code: str,
    inputs: dict[str, Any],
    function_name: str,
    timeout_seconds: float,
) -> None:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    try:
        _apply_security_limits(timeout_seconds=timeout_seconds)
        # Minimize ambient secret exposure from parent process.
        os.environ.clear()
        os.environ["PYTHONIOENCODING"] = "utf-8"
        globals_scope: dict[str, Any] = {
            "__builtins__": _ALLOWED_BUILTINS,
            **_ALLOWED_MODULES,
        }
        locals_scope: dict[str, Any] = {}
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(
            stderr_buffer
        ):
            compiled = compile(code, "<python_execute_math>", "exec")
            exec(compiled, globals_scope, locals_scope)  # noqa: S102
            fn = locals_scope.get(function_name) or globals_scope.get(function_name)
            if not callable(fn):
                raise ValueError(
                    f"Function '{function_name}' not found in code body."
                )
            output = fn(inputs)
        queue.put(
            {
                "ok": True,
                "output": _to_jsonable(output),
                "stdout": _trim_stream(stdout_buffer.getvalue()),
                "stderr": _trim_stream(stderr_buffer.getvalue()),
            }
        )
    except Exception as exc:  # pragma: no cover - subprocess defensive path
        traceback.print_exc(file=stderr_buffer)
        queue.put(
            {
                "ok": False,
                "error": f"{exc.__class__.__name__}: {exc}",
                "stdout": _trim_stream(stdout_buffer.getvalue()),
                "stderr": _trim_stream(stderr_buffer.getvalue()),
            }
        )


def _validate_math_code(code: str) -> None:
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise ValueError(f"Invalid Python syntax: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _DISALLOWED_CALL_NAMES:
                raise ValueError(
                    f"Disallowed function call: {node.func.id}()."
                )
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Dunder names are not allowed in python_execute_math.")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError(
                "Dunder attribute access is not allowed in python_execute_math."
            )


def _normalize_timeout(raw_timeout: float | None) -> float:
    if raw_timeout is None:
        return _DEFAULT_TIMEOUT_SECONDS
    timeout = float(raw_timeout)
    if timeout <= 0:
        return _DEFAULT_TIMEOUT_SECONDS
    return min(timeout, _MAX_TIMEOUT_SECONDS)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


def _trim_stream(value: str) -> str:
    if len(value) <= _MAX_STD_STREAM_CHARS:
        return value
    omitted = len(value) - _MAX_STD_STREAM_CHARS
    return f"{value[:_MAX_STD_STREAM_CHARS]}\n...<truncated {omitted} chars>"


def _apply_security_limits(*, timeout_seconds: float) -> None:
    if resource is None:  # pragma: no cover - non-posix fallback
        return

    cpu_seconds = max(1, int(timeout_seconds) + 1)
    _safe_setrlimit(resource.RLIMIT_CPU, cpu_seconds, cpu_seconds)
    _safe_setrlimit(resource.RLIMIT_AS, _MAX_ADDRESS_SPACE_BYTES, _MAX_ADDRESS_SPACE_BYTES)
    _safe_setrlimit(resource.RLIMIT_FSIZE, _MAX_FILE_BYTES, _MAX_FILE_BYTES)
    _safe_setrlimit(resource.RLIMIT_NOFILE, _MAX_OPEN_FILES, _MAX_OPEN_FILES)
    _safe_setrlimit(resource.RLIMIT_NPROC, _MAX_PROCESSES, _MAX_PROCESSES)
    _safe_setrlimit(resource.RLIMIT_CORE, 0, 0)


def _safe_setrlimit(limit_name: int, soft: int, hard: int) -> None:
    try:
        resource.setrlimit(limit_name, (soft, hard))  # type: ignore[arg-type]
    except Exception:
        return

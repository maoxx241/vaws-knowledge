from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class IntakeError(RuntimeError):
    pass


class ImportLimit(IntakeError):
    pass


@dataclass
class Limits:
    files: int = 100
    scan_entries: int = 5000
    file_bytes: int = 16 * 1024 * 1024
    total_bytes: int = 64 * 1024 * 1024
    seconds: float = 120
    pages: int = 100
    output_chars: int = 500_000
    image_pixels: int = 16_000_000
    cells: int = 100_000
    archive_bytes: int = 64 * 1024 * 1024
    memory_mb: int = 512

    @classmethod
    def from_spec(cls, value: Any) -> "Limits":
        if not isinstance(value or {}, dict):
            raise ValueError("limits must be an object")
        unknown = set(value or {}) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown limits: {sorted(unknown)}")
        values = value or {}
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values.values()):
            raise ValueError("limits must be finite positive numbers")
        if any(k != "seconds" and not isinstance(v, int) for k, v in values.items()):
            raise ValueError("count and byte limits must be integers")
        return cls(**values)


@dataclass
class Budget:
    limits: Limits
    started: float = field(default_factory=time.monotonic)
    bytes: int = 0
    files: int = 0
    entries: int = 0

    def check(self) -> None:
        if time.monotonic() - self.started > self.limits.seconds:
            raise ImportLimit("source time budget reached")

    def scan(self) -> None:
        self.check()
        self.entries += 1
        if self.entries > self.limits.scan_entries:
            raise ImportLimit("source scan budget reached")

    def take(self, count: int) -> None:
        self.check()
        if count > self.limits.file_bytes or self.bytes + count > self.limits.total_bytes:
            raise ImportLimit("source byte budget reached")
        if self.files >= self.limits.files:
            raise ImportLimit("source file budget reached")
        self.bytes += count
        self.files += 1

    def remaining(self) -> float:
        self.check()
        return max(.05, self.limits.seconds - (time.monotonic() - self.started))


@dataclass
class Item:
    key: str
    name: str
    data: bytes
    location: str
    revision: Any = None
    details: dict = field(default_factory=dict)


def digest(value: Any) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp = tempfile.mkstemp(prefix=".intake-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def write_json(path: Path, value: Any) -> None:
    write_atomic(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ImportLimit("state file exceeds byte budget")
    return json.loads(path.read_text(encoding="utf-8"))


def bounded_read(path: Path, budget: Budget) -> bytes:
    budget.check()
    with path.open("rb") as stream:
        data = stream.read(min(budget.limits.file_bytes, budget.limits.total_bytes - budget.bytes) + 1)
    budget.take(len(data))
    return data


def _darwin_rss_reader():
    """Read the child's resident bytes, without launching a process per sample."""
    import ctypes

    # Darwin proc_taskinfo, <sys/proc_info.h>: six uint64 and twelve int32.
    class TaskInfo(ctypes.Structure):
        _fields_ = [("virtual", ctypes.c_uint64), ("resident", ctypes.c_uint64),
                    ("times", ctypes.c_uint64 * 4), ("counters", ctypes.c_int32 * 12)]

    libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    query = libproc.proc_pidinfo
    query.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
    query.restype = ctypes.c_int

    def resident_bytes(pid: int) -> int:
        info = TaskInfo()
        if query(pid, 4, 0, ctypes.byref(info), ctypes.sizeof(info)) != ctypes.sizeof(info):
            raise IntakeError("cannot inspect subprocess resident memory")
        return info.resident

    return resident_bytes


def command(args: list[str], *, timeout: float, max_bytes: int, cwd: Path | None = None,
            env: dict | None = None, check: bool = True, memory_mb: int | None = None) -> tuple[int, bytes]:
    """Pipe output into bounded files; kill at the actual byte/time limit."""
    # RLIMIT_AS on macOS can reject an ordinary Python process's startup VM.
    # Supervise RSS in the parent instead; the 10ms sampling permits brief overshoot.
    resident_bytes = _darwin_rss_reader() if sys.platform == "darwin" and memory_mb else None
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(args, cwd=cwd, env=env, stdout=stdout, stderr=stderr, creationflags=creationflags)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if time.monotonic() - started > timeout:
                    raise ImportLimit("subprocess time budget reached")
                if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > max_bytes:
                    raise ImportLimit("subprocess output budget reached")
                if resident_bytes is not None:
                    try:
                        used = resident_bytes(process.pid)
                    except IntakeError:
                        if process.poll() is not None:  # exited between poll and proc_pidinfo
                            break
                        raise
                    if used > memory_mb * 1024 * 1024:
                        raise ImportLimit("subprocess resident memory budget reached")
                time.sleep(.01)
            if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > max_bytes:
                raise ImportLimit("subprocess output budget reached")
            stdout.seek(0)
            output = stdout.read(max_bytes + 1)
            if check and process.returncode:
                raise IntakeError(f"{Path(args[0]).name} failed (exit {process.returncode})")
            return process.returncode, output
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()

"""Disposable URL downloader; the parent enforces the absolute wall deadline."""
from __future__ import annotations

import json
import sys

from .common import Budget, IntakeError, Limits
from .sources import _url_bytes_in_process
from .worker import _memory_limit


def main() -> None:
    url, byte_limit, seconds, memory = sys.argv[1:]
    job = _memory_limit(int(memory))
    limits = Limits(file_bytes=int(byte_limit), total_bytes=int(byte_limit), seconds=float(seconds))
    try:
        data, metadata = _url_bytes_in_process(url, Budget(limits))
    except (IntakeError, ValueError, OSError) as exc:
        data, metadata = b"", {"error": str(exc)}
    sys.stdout.buffer.write(json.dumps(metadata, ensure_ascii=False).encode("utf-8") + b"\n" + data)


if __name__ == "__main__":
    main()

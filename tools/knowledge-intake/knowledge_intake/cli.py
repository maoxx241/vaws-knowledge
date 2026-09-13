from __future__ import annotations

import argparse
import json
from pathlib import Path

from .sync import sync_sources


def main() -> int:
    parser = argparse.ArgumentParser(description="Independent source intake into Markdown and assets")
    parser.add_argument("config", type=Path, help="standalone JSON configuration")
    parser.add_argument("--force", action="store_true", help="repeat conversion while preserving edited outputs")
    args = parser.parse_args()
    result = sync_sources(json.loads(args.config.read_text(encoding="utf-8")), force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())

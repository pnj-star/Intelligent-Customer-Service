"""MCP 启动入口：优先使用 components/ 下的独立副本，再启动 MCP 服务。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

for name in ("common_core", "retrieve_skill", "nl2sql_skill"):
    src = ROOT / "components" / name / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from customer_service.mcp import main  # noqa: E402


if __name__ == "__main__":
    args = list(sys.argv[1:])
    if not any(arg.startswith("--transport") for arg in args):
        args[:0] = ["--transport", "streamable-http"]
    if "--port" not in args:
        args.extend(["--port", "8001"])
    main(argv=args)

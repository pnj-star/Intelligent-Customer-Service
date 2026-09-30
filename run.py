"""本地启动入口：优先使用 components 下的独立副本，再启动 FastAPI 服务。"""

from __future__ import annotations

import sys
import os
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

import uvicorn  # noqa: E402

from customer_service.app import create_app  # noqa: E402


def main() -> None:
    app = create_app()
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

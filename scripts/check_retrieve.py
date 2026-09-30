"""真实调用低层 retrieve()，排查 RAG 返回为空的原因。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for rel in (
    "components/common_core/src",
    "components/retrieve_skill/src",
    "components/nl2sql_skill/src",
    "src",
):
    path = str(ROOT / rel)
    if path not in sys.path:
        sys.path.insert(0, path)

from common_core.context import AgentContext  # noqa: E402
from retrieve_skill.builder import build_pipeline, build_runtime  # noqa: E402


async def main() -> None:
    env_path = ROOT / ".env"
    runtime = build_runtime(dotenv_paths=[str(env_path)])
    pipeline = build_pipeline(runtime, include_defaults=False)
    for tenant, kb in (
        ("Influencer", "Influencer_knowlege"),
        ("t_mushroom", "kb_mushroom"),
    ):
        try:
            docs = await pipeline.retrieve(
                "羊肚菌有什么功效",
                context=AgentContext(tenant_id=tenant, kb_id=kb, request_id="check-retrieve"),
                query_rewrite_mode="off",
            )
            print(f"{tenant} / {kb}: count={len(docs)}")
            if docs:
                first = {
                    key: (str(value)[:60] if isinstance(value, str) else value)
                    for key, value in docs[0].items()
                }
                print("  first:", first)
        except Exception as exc:  # noqa: BLE001
            print(f"{tenant} / {kb}: ERR {type(exc).__name__}: {str(exc)[:300]}")


if __name__ == "__main__":
    asyncio.run(main())

"""LLM 连通性检查：验证 .env 的 LLM_* 配置能否完成意图识别与闲聊调用。"""

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

from common_core.config import RuntimeConfig, load_env_files  # noqa: E402
from common_core.providers import OpenAICompatibleLLM  # noqa: E402
from customer_service.prompts import INTENT_SYSTEM_PROMPT  # noqa: E402


async def main() -> None:
    env_path = ROOT / ".env"
    if env_path.is_file():
        load_env_files(str(env_path))
    runtime = RuntimeConfig.from_env()
    print("base_url:", runtime.llm.base_url)
    print("model:", runtime.llm.model)

    llm = OpenAICompatibleLLM(runtime.llm)
    try:
        out = await llm.chat_json(
            [{"role": "user", "content": "你好"}],
            system_prompt=INTENT_SYSTEM_PROMPT,
            temperature=0.0,
        )
        print("chat_json OK:", out)
    except Exception as exc:  # noqa: BLE001
        print("chat_json ERR:", type(exc).__name__, str(exc)[:1000])

    try:
        out = await llm.chat(
            [{"role": "user", "content": "你好"}],
            system_prompt="你是客服，负责闲聊。",
            temperature=0.6,
        )
        print("chat OK:", out)
    except Exception as exc:  # noqa: BLE001
        print("chat ERR:", type(exc).__name__, str(exc)[:1000])


if __name__ == "__main__":
    asyncio.run(main())

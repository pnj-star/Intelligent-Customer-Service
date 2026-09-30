"""内存短期记忆的增删、裁剪与过期测试。"""

from __future__ import annotations

import asyncio
import time

from customer_service.memory import ShortTermMemory


def test_history_trim_and_persist() -> None:
    memory = ShortTermMemory(max_messages=3)

    async def main() -> None:
        for index in range(5):
            await memory.append_message("s1", "user", f"msg-{index}")
        history = await memory.get_history("s1")
        assert len(history) == 3
        assert history[-1] == {"role": "user", "content": "msg-4"}

    asyncio.run(main())


def test_entities_merge_keep_old_slots() -> None:
    memory = ShortTermMemory()

    async def main() -> None:
        await memory.set_entities("s1", {"product": "华为P60"})
        await memory.set_entities("s1", {"product": "华为P70", "order": "ORD-1"})
        entities = await memory.get_entities("s1")
        assert entities == {"product": "华为P70", "order": "ORD-1"}

    asyncio.run(main())


def test_clarification_state_and_rounds() -> None:
    memory = ShortTermMemory()

    async def main() -> None:
        await memory.set_pending_clarification("s1", True)
        await memory.set_clarification_rounds("s1", 2)
        assert await memory.get_pending_clarification("s1") is True
        assert await memory.get_clarification_rounds("s1") == 2
        await memory.set_pending_clarification("s1", False)
        assert await memory.get_pending_clarification("s1") is False

    asyncio.run(main())


def test_ttl_expiry() -> None:
    memory = ShortTermMemory(ttl_seconds=0.05, max_sessions=10)

    async def main() -> None:
        await memory.append_message("s1", "user", "hello")
        assert await memory.get_session("s1") is not None
        time.sleep(0.1)
        assert await memory.get_session("s1") is None

    asyncio.run(main())


def test_max_sessions_eviction() -> None:
    memory = ShortTermMemory(ttl_seconds=3600, max_sessions=2)

    async def main() -> None:
        for sid in ("a", "b", "c"):
            await memory.append_message(sid, "user", sid)
        assert await memory.get_session("a") is None
        assert await memory.get_session("b") is not None
        assert await memory.get_session("c") is not None

    asyncio.run(main())

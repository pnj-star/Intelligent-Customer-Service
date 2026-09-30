"""内存版短期记忆：会话历史、实体槽位、澄清状态。

只保证单进程内有效；后续需要 Redis 或长期记忆时替换本类即可。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionMemory:
    session_id: str
    messages: list[dict[str, str]] = field(default_factory=list)
    entities: dict[str, str] = field(default_factory=dict)
    pending_clarification: bool = False
    clarification_rounds: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()


class ShortTermMemory:
    """按 session_id 保存最近若干轮对话与已确认实体。"""

    def __init__(
        self,
        *,
        ttl_seconds: int = 86400,
        max_messages: int = 20,
        max_sessions: int = 1000,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_messages = max_messages
        self.max_sessions = max_sessions
        self._slots: dict[str, SessionMemory] = {}
        self._lock = asyncio.Lock()

    async def get_session(self, session_id: str) -> SessionMemory | None:
        await self._cleanup()
        return self._slots.get(session_id)

    async def get_or_create_session(self, session_id: str) -> SessionMemory:
        async with self._lock:
            await self._cleanup_locked()
            slot = self._slots.get(session_id)
            if slot is None:
                slot = SessionMemory(session_id=session_id)
                self._slots[session_id] = slot
            slot.touch()
            return slot

    async def get_history(self, session_id: str) -> list[dict[str, str]]:
        slot = await self.get_session(session_id)
        if slot is None:
            return []
        return list(slot.messages)

    async def get_entities(self, session_id: str) -> dict[str, str]:
        slot = await self.get_session(session_id)
        if slot is None:
            return {}
        return dict(slot.entities)

    async def get_pending_clarification(self, session_id: str) -> bool:
        slot = await self.get_session(session_id)
        return bool(slot.pending_clarification) if slot else False

    async def get_clarification_rounds(self, session_id: str) -> int:
        slot = await self.get_session(session_id)
        return slot.clarification_rounds if slot else 0

    async def append_message(self, session_id: str, role: str, content: str) -> None:
        slot = await self.get_or_create_session(session_id)
        async with self._lock:
            slot.messages.append({"role": role, "content": str(content)})
            if len(slot.messages) > self.max_messages:
                overflow = len(slot.messages) - self.max_messages
                slot.messages = slot.messages[overflow:]
            slot.touch()

    async def set_entities(
        self,
        session_id: str,
        entities: dict[str, Any] | None,
    ) -> None:
        slot = await self.get_or_create_session(session_id)
        async with self._lock:
            for key, value in (entities or {}).items():
                if value is not None and str(value).strip():
                    slot.entities[str(key)] = str(value).strip()
            slot.touch()

    async def set_pending_clarification(self, session_id: str, value: bool) -> None:
        slot = await self.get_or_create_session(session_id)
        async with self._lock:
            slot.pending_clarification = bool(value)
            slot.touch()

    async def set_clarification_rounds(self, session_id: str, value: int) -> None:
        slot = await self.get_or_create_session(session_id)
        async with self._lock:
            slot.clarification_rounds = max(0, int(value))
            slot.touch()

    async def clear(self, session_id: str) -> None:
        async with self._lock:
            self._slots.pop(session_id, None)

    async def _cleanup(self) -> None:
        async with self._lock:
            await self._cleanup_locked()

    async def _cleanup_locked(self) -> None:
        now = time.time()
        expired = [
            sid
            for sid, slot in self._slots.items()
            if now - slot.updated_at > self.ttl_seconds
        ]
        for sid in expired:
            self._slots.pop(sid, None)
        if len(self._slots) > self.max_sessions:
            sorted_slots = sorted(
                self._slots.items(),
                key=lambda item: item[1].updated_at,
            )
            for sid, _ in sorted_slots[: len(self._slots) - self.max_sessions]:
                self._slots.pop(sid, None)


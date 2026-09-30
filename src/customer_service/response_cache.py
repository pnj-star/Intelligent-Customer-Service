"""用户问题 -> 最终回答的 Redis 缓存适配器。"""

from __future__ import annotations

from typing import Any


class ResponseCache:
    def __init__(
        self,
        cache: Any,
        *,
        scope: str,
        short_ttl: int = 300,
        long_ttl: int = 1800,
    ) -> None:
        self.cache = cache
        self.scope = scope
        self.short_ttl = short_ttl
        self.long_ttl = long_ttl

    @staticmethod
    def _key(query: str) -> str:
        return str(query or "").strip()

    def get(self, query: str, *, context: Any = None) -> str | None:
        return self.cache.get(
            self.scope,
            self._key(query),
            tenant_id=getattr(context, "tenant_id", ""),
            kb_id=getattr(context, "kb_id", ""),
        )

    def put(
        self,
        query: str,
        response: str,
        *,
        context: Any = None,
        ttl: int | None = None,
    ) -> bool:
        effective_ttl = ttl or (
            self.long_ttl
            if len(str(response or "").strip()) >= 20
            else self.short_ttl
        )
        return bool(
            self.cache.set(
                self.scope,
                self._key(query),
                str(response or ""),
                ttl=effective_ttl,
                tenant_id=getattr(context, "tenant_id", ""),
                kb_id=getattr(context, "kb_id", ""),
            )
        )


"""回答缓存适配器测试。"""

from __future__ import annotations

from common_core.context import AgentContext

from customer_service.response_cache import ResponseCache


class FakeRedisCache:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str, str, str], str] = {}

    def get(
        self,
        scope: str,
        key: str,
        *,
        tenant_id: str = "",
        kb_id: str = "",
    ) -> str | None:
        return self.store.get((scope, tenant_id, kb_id, key))

    def set(
        self,
        scope: str,
        key: str,
        value: str,
        *,
        ttl: int | None = None,
        tenant_id: str = "",
        kb_id: str = "",
    ) -> bool:
        self.store[(scope, tenant_id, kb_id, key)] = value
        return True


def test_put_get_is_scoped_by_tenant_and_kb() -> None:
    cache = FakeRedisCache()
    response_cache = ResponseCache(cache, scope="customer_service")
    ctx = AgentContext(tenant_id="t1", kb_id="kb1")

    assert response_cache.put("华为P60退货政策", "答案是退货政策", context=ctx) is True
    assert response_cache.get("华为P60退货政策", context=ctx) == "答案是退货政策"
    assert (
        response_cache.get(
            "华为P60退货政策",
            context=AgentContext(tenant_id="t2", kb_id="kb1"),
        )
        is None
    )


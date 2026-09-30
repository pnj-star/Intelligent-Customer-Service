"""客服依赖容器：LLM、两个 pipeline、Redis 回答缓存与内存短期记忆。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common_core.context import AgentContext

from config.business_config import (
    DEFAULT_DB_ID,
    DEFAULT_KB_ID,
    DEFAULT_TENANT_ID,
    HISTORY_MAX_MESSAGES,
    MAX_CLARIFICATION_ROUNDS,
    RESPONSE_CACHE_PREFIX,
    RESPONSE_CACHE_SHORT_TTL,
    RESPONSE_CACHE_TTL,
)

from .memory import ShortTermMemory
from .response_cache import ResponseCache


@dataclass
class CustomerServiceDependencies:
    """图节点需要的一切外部能力，测试时全部可以注入 fake。"""

    llm: Any
    retrieve_pipeline: Any = None
    nl2sql_pipeline: Any = None
    response_cache: Any = None
    memory: Any = None
    tenant_id: str = DEFAULT_TENANT_ID
    kb_id: str = DEFAULT_KB_ID
    db_id: str = DEFAULT_DB_ID

    def context(self, state: dict[str, Any] | None = None) -> AgentContext:
        state = state or {}
        return AgentContext(
            tenant_id=state.get("tenant_id") or self.tenant_id,
            kb_id=state.get("kb_id") or self.kb_id,
            session_id=state.get("session_id", ""),
            request_id=state.get("request_id", ""),
        )


def build_default_dependencies(
    *,
    env_file: str | Path | None = None,
) -> CustomerServiceDependencies:
    """从项目根 .env 组装真实依赖。

    三个组件都优先使用 components/ 下的本地副本，运行时统一读取本项目 .env。
    """
    from nl2sql_skill.builder import build_cache as build_nl2sql_cache
    from nl2sql_skill.builder import build_nl2sql_pipeline
    from retrieve_skill.builder import build_pipeline, build_runtime
    from common_core.providers import OpenAICompatibleLLM, RedisCache

    root = Path(__file__).parents[2]
    env_path = str(root / ".env") if env_file is None else str(env_file)

    runtime = build_runtime(dotenv_paths=[env_path])
    llm = OpenAICompatibleLLM(runtime.llm)
    # 客服链路使用低层 retrieve()（与 merchant 实例一致），不加载重排器/父块缓存。
    retrieve_pipeline = build_pipeline(runtime, llm=llm, include_defaults=False)
    nl2sql_pipeline = build_nl2sql_pipeline(
        dotenv_paths=[env_path],
        cache=build_nl2sql_cache(dotenv_paths=[env_path]),
    )
    cache = RedisCache(runtime.cache, shared=True)
    response_cache = ResponseCache(
        cache,
        scope=RESPONSE_CACHE_PREFIX,
        short_ttl=RESPONSE_CACHE_SHORT_TTL,
        long_ttl=RESPONSE_CACHE_TTL,
    )
    memory = ShortTermMemory(max_messages=HISTORY_MAX_MESSAGES)
    return CustomerServiceDependencies(
        llm=llm,
        retrieve_pipeline=retrieve_pipeline,
        nl2sql_pipeline=nl2sql_pipeline,
        response_cache=response_cache,
        memory=memory,
        tenant_id=DEFAULT_TENANT_ID,
        kb_id=DEFAULT_KB_ID,
        db_id=DEFAULT_DB_ID,
    )

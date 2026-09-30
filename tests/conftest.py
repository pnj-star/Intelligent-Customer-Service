"""测试夹具：保证 import 解析到 components/ 本地副本，并提供 fake provider。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

for rel in (
    "src",
    "",
    "components/common_core/src",
    "components/retrieve_skill/src",
    "components/nl2sql_skill/src",
):
    path = str(ROOT / rel) if rel else str(ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)

from common_core.context import AgentContext  # noqa: E402
from nl2sql_skill.types import NL2SQLResult  # noqa: E402
from retrieve_skill.results import RetrieveResult  # noqa: E402

from customer_service.dependencies import CustomerServiceDependencies  # noqa: E402
from customer_service.memory import ShortTermMemory  # noqa: E402


class FakeLLM:
    def __init__(
        self,
        chat_response: str = "好的",
        intent_response: dict[str, Any] | None = None,
    ) -> None:
        self.chat_response = chat_response
        self.intent_response = intent_response or {
            "intent_type": "rag",
            "entities": {},
            "rewritten_query": "",
            "clarify_questions": [],
        }

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        system_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        return self.chat_response

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        system_prompt: str = "",
        temperature: float | None = None,
    ) -> dict[str, Any]:
        return dict(self.intent_response)


class FakeRetrievePipeline:
    def __init__(
        self,
        *,
        result: Any = None,
        status: str = "retrieved",
        docs: list[dict[str, Any]] | None = None,
    ) -> None:
        self.result = result
        self.status = status
        self.docs = docs or []

    async def retrieve_context(self, query: str, context: Any = None, **kwargs: Any) -> Any:
        if isinstance(self.result, BaseException):
            raise self.result
        if self.result is not None:
            return self.result
        return RetrieveResult(
            status=self.status,
            docs=self.docs,
            rewritten_query=query,
        )

    async def retrieve(self, query: str, context: Any = None, **kwargs: Any) -> Any:
        if isinstance(self.result, BaseException):
            raise self.result
        if isinstance(self.result, list):
            return list(self.result)
        return list(self.docs)


class FakeNL2SQLPipeline:
    def __init__(
        self,
        *,
        result: Any = None,
        status: str = "executed",
        rows: list[dict[str, Any]] | None = None,
        digest: dict[str, Any] | None = None,
        clarify_questions: list[str] | None = None,
        message: str = "",
    ) -> None:
        self.result = result
        self.status = status
        self.rows = rows or []
        self.digest = digest
        self.clarify_questions = clarify_questions or []
        self.message = message

    async def generate(self, request: Any) -> Any:
        if isinstance(self.result, BaseException):
            raise self.result
        if self.result is not None:
            return self.result
        return NL2SQLResult(
            status=self.status,
            query=request.query,
            tenant_id=request.tenant_id,
            db_id=request.db_id,
            request_id=request.request_id,
            rows=self.rows,
            digest=self.digest,
            clarify_questions=self.clarify_questions,
            message=self.message,
        )


class FakeResponseCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, query: str, *, context: AgentContext | None = None) -> str | None:
        return self.store.get(query)

    def put(
        self,
        query: str,
        response: str,
        *,
        context: AgentContext | None = None,
        ttl: int | None = None,
    ) -> bool:
        self.store[query] = response
        return True


def make_deps(
    *,
    llm: FakeLLM | None = None,
    retrieve: FakeRetrievePipeline | None = None,
    nl2sql: FakeNL2SQLPipeline | None = None,
    cache: FakeResponseCache | None = None,
    memory: ShortTermMemory | None = None,
) -> CustomerServiceDependencies:
    return CustomerServiceDependencies(
        llm=llm or FakeLLM(),
        retrieve_pipeline=retrieve or FakeRetrievePipeline(),
        nl2sql_pipeline=nl2sql or FakeNL2SQLPipeline(),
        response_cache=cache or FakeResponseCache(),
        memory=memory or ShortTermMemory(),
        tenant_id="t1",
        kb_id="kb1",
        db_id="erp",
    )


__all__ = [
    "FakeLLM",
    "FakeNL2SQLPipeline",
    "FakeResponseCache",
    "FakeRetrievePipeline",
    "make_deps",
]

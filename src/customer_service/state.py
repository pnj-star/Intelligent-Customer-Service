"""客服图的状态定义，框架中立，便于单测。"""

from __future__ import annotations

from typing import Any, TypedDict


class CustomerServiceState(TypedDict, total=False):
    user_query: str
    entities: dict[str, str]
    memory_entities: dict[str, str]
    rewritten_query: str
    answer: str
    cache_hit: bool
    retrieve_result: dict[str, Any] | None
    sql_result: dict[str, Any] | None
    intent_type: str
    history: list[dict[str, str]]
    messages: list[dict[str, Any]]
    needs_clarification: bool
    clarify_questions: list[str]
    pending_clarification: bool
    clarification_rounds: int
    context_docs: list[dict[str, Any]]
    sql_rows: list[dict[str, Any]]
    sql_digest: dict[str, Any] | None
    context_text: str
    final_response: str
    route_taken: str
    tenant_id: str
    kb_id: str
    db_id: str
    session_id: str
    request_id: str

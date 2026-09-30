"""客服图节点实现。

节点只依赖注入的 CustomerServiceDependencies；业务话术集中在 config.business_config。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from nl2sql_skill.types import NL2SQLRequest

from config.business_config import (
    COMMISSION_KEYWORDS,
    FALLBACK_TEXT,
    MAX_CONTEXT_CHARS,
    MAX_DOC_CHARS,
    MAX_CLARIFICATION_ROUNDS,
    MAX_SQL_JSON_CHARS,
    PRODUCT_LIST_PHRASES,
    RAG_HINT_KEYWORDS,
)

from .prompts import ANSWER_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT, INTENT_SYSTEM_PROMPT
from .result_validator import BranchOutcome, validate_nl2sql_result, validate_retrieve_result

logger = logging.getLogger(__name__)

INTENT_NAMES = {"chat", "rag", "sql", "rag+sql"}


def _should_ask(state: dict[str, Any]) -> bool:
    return int(state.get("clarification_rounds") or 0) < MAX_CLARIFICATION_ROUNDS


def _entity_in_query(query: str, entities: dict[str, str]) -> bool:
    return any(value and str(value) in query for value in entities.values())


def _forced_intent(query: str) -> str | None:
    """佣金/产品数量类问题至少走 sql；带检索意图词时升级为 rag+sql。"""
    sql_hit = any(keyword in query for keyword in COMMISSION_KEYWORDS) or any(
        phrase in query for phrase in PRODUCT_LIST_PHRASES
    )
    if not sql_hit:
        return None
    if any(keyword in query for keyword in RAG_HINT_KEYWORDS):
        return "rag+sql"
    return "sql"


def _result_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, BaseException):
        return {"status": "error", "message": str(result)}
    if isinstance(result, list):
        docs = [dict(item) for item in result]
        return {
            "status": "retrieved" if docs else "no_context",
            "message": "",
            "docs": docs,
            "rows": [],
        }
    return {
        "status": str(getattr(result, "status", "") or ""),
        "message": str(getattr(result, "message", "") or ""),
        "docs": [dict(item) for item in (getattr(result, "docs", None) or [])],
        "rows": [dict(item) for item in (getattr(result, "rows", None) or [])],
    }


def _messages(state: dict[str, Any]) -> list[dict[str, str]]:
    messages = [
        {"role": str(item.get("role", "user")), "content": str(item.get("content", ""))}
        for item in (state.get("history") or [])
        if isinstance(item, dict)
    ]
    query = state.get("user_query") or ""
    messages.append({"role": "user", "content": query})
    return messages


async def _call_retrieve(deps: Any, state: dict[str, Any]) -> Any:
    query = state.get("rewritten_query") or state.get("user_query") or ""
    context = deps.context(state)
    return await deps.retrieve_pipeline.retrieve(
        query,
        context=context,
        query_rewrite_mode="off",
        rewrite_query=query,
    )


async def _call_sql(deps: Any, state: dict[str, Any]) -> Any:
    query = state.get("rewritten_query") or state.get("user_query") or ""
    request = NL2SQLRequest(
        query=query,
        tenant_id=state.get("tenant_id") or deps.tenant_id,
        db_id=state.get("db_id") or deps.db_id,
        request_id=state.get("request_id", ""),
        session_id=state.get("session_id", ""),
        history=state.get("history") or [],
        execute=True,
    )
    return await deps.nl2sql_pipeline.generate(request)


def make_cache(deps: Any) -> Any:
    async def cache_node(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("user_query") or ""
        if not query:
            return {"cache_hit": False}
        try:
            cached = deps.response_cache.get(query, context=deps.context(state))
        except Exception as exc:  # noqa: BLE001 - 缓存故障不阻断主流程
            logger.warning("response cache read failed (non-fatal): %s", exc)
            cached = None
        if cached:
            return {
                "cache_hit": True,
                "final_response": cached,
                "answer": cached,
                "route_taken": "cache",
            }
        return {"cache_hit": False}

    return cache_node


def make_intent(deps: Any) -> Any:
    async def intent_node(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("user_query") or ""
        try:
            payload = await deps.llm.chat_json(
                _messages(state),
                system_prompt=INTENT_SYSTEM_PROMPT,
                temperature=0.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("intent LLM call failed: %s", exc)
            return {
                "intent_type": "",
                "final_response": FALLBACK_TEXT,
                "route_taken": "intent_error",
            }
        if not isinstance(payload, dict):
            return {
                "intent_type": "",
                "final_response": FALLBACK_TEXT,
                "route_taken": "intent_invalid",
            }

        intent = str(payload.get("intent_type") or "").strip().lower()
        forced = _forced_intent(query)
        if forced is not None:
            intent = forced
        if intent not in INTENT_NAMES:
            return {
                "intent_type": "",
                "final_response": FALLBACK_TEXT,
                "route_taken": "intent_invalid",
            }

        raw_entities = payload.get("entities") or {}
        if isinstance(raw_entities, dict):
            entities = {
                str(key): str(value).strip()
                for key, value in raw_entities.items()
                if value is not None and str(value).strip()
            }
        elif isinstance(raw_entities, list):
            entities = {
                f"entity_{index + 1}": str(value).strip()
                for index, value in enumerate(raw_entities)
                if str(value).strip()
            }
        else:
            entities = {}

        merged = {**(state.get("memory_entities") or {}), **entities}
        clarify = [
            str(item).strip()
            for item in (payload.get("clarify_questions") or [])
            if str(item).strip()
        ]

        entity_in_query = _entity_in_query(query, entities)
        if intent == "chat":
            rewritten = query
        elif entity_in_query or not merged:
            # 当前问题已带实体：原样透传；完全无实体时也先原样走，避免编造。
            rewritten = query
        else:
            # 实体来自历史/上一轮追问，用 LLM 补全后的规范问题。
            rewritten = str(payload.get("rewritten_query") or "").strip() or query

        if (
            intent in ("sql", "rag", "rag+sql")
            and not entity_in_query
            and not merged
            and clarify
            and _should_ask(state)
        ):
            return {
                "intent_type": intent,
                "entities": merged,
                "memory_entities": merged,
                "rewritten_query": rewritten,
                "needs_clarification": True,
                "clarify_questions": clarify,
                "clarification_rounds": int(state.get("clarification_rounds") or 0) + 1,
                "route_taken": "intent_clarify",
            }

        return {
            "intent_type": intent,
            "entities": merged,
            "memory_entities": merged,
            "rewritten_query": rewritten,
            "needs_clarification": False,
            "clarify_questions": [],
            "route_taken": "intent",
        }

    return intent_node


def make_chat(deps: Any) -> Any:
    async def chat_node(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("user_query") or ""
        try:
            response = str(
                await deps.llm.chat(
                    [{"role": "user", "content": query}],
                    system_prompt=CHAT_SYSTEM_PROMPT,
                    temperature=0.6,
                )
                or FALLBACK_TEXT
            ).strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("chat LLM call failed, using fallback: %s", exc)
            response = FALLBACK_TEXT
        return {"final_response": response, "route_taken": "chat"}

    return chat_node


def make_rag(deps: Any) -> Any:
    async def rag_node(state: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await _call_retrieve(deps, state)
        except BaseException as exc:  # noqa: BLE001
            result = exc
        outcome = validate_retrieve_result(result)
        store = {"retrieve_result": _result_dict(result)}
        if outcome.valid:
            return {**store, "context_docs": outcome.docs, "route_taken": "rag"}
        return {
            **store,
            "context_docs": [],
            "final_response": FALLBACK_TEXT,
            "route_taken": f"rag_{outcome.kind}",
        }

    return rag_node


def make_sql(deps: Any) -> Any:
    async def sql_node(state: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await _call_sql(deps, state)
        except BaseException as exc:  # noqa: BLE001
            result = exc
        outcome = validate_nl2sql_result(result)
        store = {"sql_result": _result_dict(result)}
        if outcome.valid:
            return {
                **store,
                "sql_rows": outcome.rows,
                "sql_digest": outcome.digest,
                "route_taken": "sql",
            }
        if _should_ask(state) and outcome.needs_clarification:
            return {
                **store,
                "needs_clarification": True,
                "clarify_questions": outcome.clarify_questions,
                "clarification_rounds": int(state.get("clarification_rounds") or 0) + 1,
                "route_taken": "sql_clarify",
            }
        if outcome.kind == "guardrail":
            return {
                **store,
                "sql_rows": [],
                "final_response": outcome.message,
                "route_taken": "sql_guardrail",
            }
        return {
            **store,
            "sql_rows": [],
            "final_response": FALLBACK_TEXT,
            "route_taken": f"sql_{outcome.kind}",
        }

    return sql_node


def make_rag_sql(deps: Any) -> Any:
    async def rag_sql_node(state: dict[str, Any]) -> dict[str, Any]:
        rag_task = asyncio.create_task(_call_retrieve(deps, state))
        sql_task = asyncio.create_task(_call_sql(deps, state))
        raw_rag, raw_sql = await asyncio.gather(
            rag_task,
            sql_task,
            return_exceptions=True,
        )
        rag_outcome = validate_retrieve_result(raw_rag)
        sql_outcome = validate_nl2sql_result(raw_sql)
        store = {
            "retrieve_result": _result_dict(raw_rag),
            "sql_result": _result_dict(raw_sql),
        }

        if rag_outcome.valid or sql_outcome.valid:
            return {
                **store,
                "context_docs": rag_outcome.docs,
                "sql_rows": sql_outcome.rows,
                "sql_digest": sql_outcome.digest,
                "route_taken": "rag_sql",
            }

        if _should_ask(state) and (
            rag_outcome.needs_clarification or sql_outcome.needs_clarification
        ):
            questions = list(
                dict.fromkeys(
                    rag_outcome.clarify_questions + sql_outcome.clarify_questions
                )
            )
            return {
                **store,
                "needs_clarification": True,
                "clarify_questions": questions,
                "clarification_rounds": int(state.get("clarification_rounds") or 0) + 1,
                "route_taken": "rag_sql_clarify",
            }

        if sql_outcome.kind == "guardrail":
            return {
                **store,
                "context_docs": [],
                "sql_rows": [],
                "final_response": sql_outcome.message,
                "route_taken": "rag_sql_guardrail",
            }
        return {
            **store,
            "context_docs": [],
            "sql_rows": [],
            "final_response": FALLBACK_TEXT,
            "route_taken": "rag_sql_empty",
        }

    return rag_sql_node


def _build_answer_content(state: dict[str, Any], query: str) -> tuple[str, str]:
    doc_blocks: list[str] = []
    for doc in state.get("context_docs") or []:
        title = (
            doc.get("parent_title")
            or doc.get("title")
            or doc.get("source")
            or ""
        )
        content = str(doc.get("content") or "").strip()
        if not content:
            continue
        text = content[:MAX_DOC_CHARS]
        doc_blocks.append(f"[{title}]\n{text}" if title else text)
    docs_text = "\n\n".join(doc_blocks)[:MAX_CONTEXT_CHARS]

    sql_blocks: list[str] = []
    rows = state.get("sql_rows") or []
    if rows:
        sql_blocks.append(
            json.dumps(rows[:20], ensure_ascii=False, default=str)[
                :MAX_SQL_JSON_CHARS
            ]
        )
    digest = state.get("sql_digest")
    if digest:
        sql_blocks.append(
            json.dumps(digest, ensure_ascii=False, default=str)[:MAX_SQL_JSON_CHARS]
        )
    sql_text = "\n\n".join(sql_blocks)

    context_text = "\n\n".join(
        [text for text in (docs_text, sql_text) if text]
    )
    content = (
        f"用户问题：{query}\n\n"
        f"【知识库资料】\n{docs_text or '（无）'}\n\n"
        f"【数据库查询结果】\n{sql_text or '（无）'}"
    )
    return context_text, content


def make_answer(deps: Any) -> Any:
    async def answer_node(state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("user_query") or ""
        context_text, content = _build_answer_content(state, query)
        try:
            response = str(
                await deps.llm.chat(
                    [{"role": "user", "content": content}],
                    system_prompt=ANSWER_SYSTEM_PROMPT,
                    temperature=0.0,
                )
                or FALLBACK_TEXT
            ).strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("answer LLM call failed, using fallback: %s", exc)
            response = FALLBACK_TEXT
        return {
            "context_text": context_text,
            "final_response": response,
            "route_taken": "answer",
        }

    return answer_node


def make_fallback(deps: Any) -> Any:
    async def fallback_node(state: dict[str, Any]) -> dict[str, Any]:
        return {"final_response": FALLBACK_TEXT, "route_taken": "fallback"}

    return fallback_node


def make_finalize(deps: Any) -> Any:
    async def finalize_node(state: dict[str, Any]) -> dict[str, Any]:
        response = state.get("final_response") or FALLBACK_TEXT
        query = state.get("user_query") or ""
        try:
            deps.response_cache.put(query, response, context=deps.context(state))
        except Exception as exc:  # noqa: BLE001
            logger.warning("response cache write failed (non-fatal): %s", exc)
        return {
            "answer": response,
            "final_response": response,
            "route_taken": state.get("route_taken") or "finalize",
        }

    return finalize_node


def build_nodes(deps: Any) -> dict[str, Any]:
    return {
        "cache": make_cache(deps),
        "intent": make_intent(deps),
        "chat": make_chat(deps),
        "rag": make_rag(deps),
        "sql": make_sql(deps),
        "rag_sql": make_rag_sql(deps),
        "answer": make_answer(deps),
        "fallback": make_fallback(deps),
        "finalize": make_finalize(deps),
    }


__all__ = ["build_nodes", "BranchOutcome"]

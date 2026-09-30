"""LangGraph 图编排：缓存 -> 意图 -> 路由 -> 分支 -> 回答 -> 收尾。"""

from __future__ import annotations

from typing import Any, Literal

from .nodes import build_nodes
from .state import CustomerServiceState


_FACTORY_STATE: dict[str, Any] = {}


def _message_text(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content", "")
    if isinstance(content, list):
        parts = [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("text")
        ]
        return "".join(parts).strip()
    return str(content or "").strip()


def entry_node(state: CustomerServiceState) -> dict[str, Any]:
    """兼容 LangSmith Studio 的 messages 输入：提取最后一轮用户消息。"""
    updates: dict[str, Any] = {}
    query = (state.get("user_query") or "").strip()
    messages = state.get("messages") or []
    if query or not messages:
        return updates

    last_user_idx: int | None = None
    for idx in range(len(messages) - 1, -1, -1):
        message = messages[idx]
        if isinstance(message, dict) and message.get("role") == "user":
            text = _message_text(message)
            if text:
                last_user_idx = idx
                query = text
                break
    if not query:
        return updates

    updates["user_query"] = query
    if not state.get("history"):
        history: list[dict[str, str]] = []
        for message in messages[:last_user_idx]:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "")
            if role not in ("user", "assistant"):
                continue
            text = _message_text(message)
            if text:
                history.append({"role": role, "content": text})
        updates["history"] = history
    return updates


def after_entry(
    state: CustomerServiceState,
) -> Literal["intent", "cache"]:
    if state.get("pending_clarification"):
        return "intent"
    return "cache"


def after_cache(
    state: CustomerServiceState,
) -> Literal["intent", "__end__"]:
    if state.get("cache_hit"):
        return "__end__"
    return "intent"


def after_intent(
    state: CustomerServiceState,
) -> Literal["chat", "rag", "sql", "rag_sql", "fallback", "__end__"]:
    if state.get("needs_clarification"):
        return "__end__"
    return {
        "chat": "chat",
        "rag": "rag",
        "sql": "sql",
        "rag+sql": "rag_sql",
    }.get(state.get("intent_type", ""), "fallback")


def after_rag(
    state: CustomerServiceState,
) -> Literal["answer", "finalize", "__end__"]:
    if state.get("needs_clarification"):
        return "__end__"
    return "answer" if state.get("context_docs") else "finalize"


def after_sql(
    state: CustomerServiceState,
) -> Literal["answer", "finalize", "__end__"]:
    if state.get("needs_clarification"):
        return "__end__"
    return "answer" if state.get("sql_rows") else "finalize"


def after_rag_sql(
    state: CustomerServiceState,
) -> Literal["answer", "finalize", "__end__"]:
    if state.get("needs_clarification"):
        return "__end__"
    if state.get("context_docs") or state.get("sql_rows"):
        return "answer"
    return "finalize"


def build_graph(deps: Any):
    """用注入的依赖组装并编译客服图。"""
    from langgraph.graph import END, StateGraph

    nodes = build_nodes(deps)
    builder = StateGraph(CustomerServiceState)
    for name, node in nodes.items():
        builder.add_node(name, node)

    builder.set_entry_point("entry")
    builder.add_node("entry", entry_node)
    builder.add_conditional_edges(
        "entry",
        after_entry,
        {"intent": "intent", "cache": "cache"},
    )
    builder.add_conditional_edges(
        "cache",
        after_cache,
        {"intent": "intent", "__end__": END},
    )
    builder.add_conditional_edges(
        "intent",
        after_intent,
        {
            "chat": "chat",
            "rag": "rag",
            "sql": "sql",
            "rag_sql": "rag_sql",
            "fallback": "fallback",
            "__end__": END,
        },
    )
    builder.add_edge("chat", "finalize")
    builder.add_edge("fallback", "finalize")
    builder.add_conditional_edges(
        "rag",
        after_rag,
        {"answer": "answer", "finalize": "finalize", "__end__": END},
    )
    builder.add_conditional_edges(
        "sql",
        after_sql,
        {"answer": "answer", "finalize": "finalize", "__end__": END},
    )
    builder.add_conditional_edges(
        "rag_sql",
        after_rag_sql,
        {"answer": "answer", "finalize": "finalize", "__end__": END},
    )
    builder.add_edge("answer", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile()


def create_graph() -> Any:
    """LangGraph 运行时入口：零参数工厂，依赖只构建一次。

    不能带 deps 参数：LangGraph 会把单参数工厂当成 config 工厂并传入 dict。
    """
    graph = _FACTORY_STATE.get("graph")
    if graph is None:
        from .dependencies import build_default_dependencies

        graph = build_graph(build_default_dependencies())
        _FACTORY_STATE["graph"] = graph
    return graph


__all__ = ["CustomerServiceState", "build_graph", "create_graph"]

"""MCP 服务助手函数测试（不启动真实服务）。"""

from __future__ import annotations

import asyncio

from customer_service.graph import build_graph
from customer_service.mcp_server import create_mcp_server, _run_chat

from conftest import FakeLLM, FakeNL2SQLPipeline, FakeRetrievePipeline, make_deps


def test_mcp_server_creates_with_fake_deps() -> None:
    deps = make_deps()
    server = create_mcp_server(deps=deps)
    assert server is not None


def test_run_chat_returns_answer_and_updates_memory() -> None:
    deps = make_deps(
        llm=FakeLLM(
            chat_response="华为P60售价6999元。",
            intent_response={
                "intent_type": "sql",
                "entities": {"product": "华为P60"},
                "rewritten_query": "华为P60 的价格",
                "clarify_questions": [],
            },
        ),
        nl2sql=FakeNL2SQLPipeline(rows=[{"price": 6999}]),
    )
    graph = build_graph(deps)

    async def main() -> None:
        payload = await _run_chat(
            deps,
            graph,
            message="华为P60多少钱",
            session_id="s1",
            tenant_id="t1",
            kb_id="kb1",
            db_id="erp",
            request_id="req-1",
        )
        assert payload["ok"] is True
        assert payload["answer"] == "华为P60售价6999元。"
        assert payload["needs_clarification"] is False
        assert payload["sql_rows"] == [{"price": 6999}]
        history = await deps.memory.get_history("s1")
        assert history[-1]["role"] == "assistant"

    asyncio.run(main())


def test_run_chat_returns_clarify_questions() -> None:
    deps = make_deps(
        llm=FakeLLM(
            intent_response={
                "intent_type": "sql",
                "entities": {},
                "rewritten_query": "",
                "clarify_questions": ["请问要查询哪个商品？"],
            }
        )
    )
    graph = build_graph(deps)

    async def main() -> None:
        payload = await _run_chat(
            deps,
            graph,
            message="它的价格",
            session_id="s2",
            tenant_id="t1",
            kb_id="kb1",
            db_id="erp",
            request_id="req-2",
        )
        assert payload["needs_clarification"] is True
        assert payload["clarify_questions"] == ["请问要查询哪个商品？"]
        assert await deps.memory.get_pending_clarification("s2") is True

    asyncio.run(main())


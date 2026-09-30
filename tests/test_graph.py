"""全链路图测试：缓存、路由、并行容错与澄清续流。"""

from __future__ import annotations

import asyncio
import inspect

from config.business_config import FALLBACK_TEXT

from customer_service.graph import build_graph, create_graph

from conftest import FakeLLM, FakeNL2SQLPipeline, FakeResponseCache, FakeRetrievePipeline, make_deps


def run_graph(deps, state):
    return asyncio.run(build_graph(deps).ainvoke(state))


def test_create_graph_factory_is_zero_arg() -> None:
    signature = inspect.signature(create_graph)
    assert len(signature.parameters) == 0


def test_messages_input_supported() -> None:
    deps = make_deps(
        llm=FakeLLM(
            chat_response="你好呀！",
            intent_response={
                "intent_type": "chat",
                "entities": {},
                "rewritten_query": "",
                "clarify_questions": [],
            },
        )
    )
    result = run_graph(
        deps,
        {
            "messages": [
                {"role": "user", "content": "之前问过售后政策"},
                {"role": "assistant", "content": "已回复"},
                {"role": "user", "content": "你好"},
            ]
        },
    )
    assert result["user_query"] == "你好"
    assert result["final_response"] == "你好呀！"
    assert result["route_taken"] == "chat"


def test_cache_hit_short_circuits() -> None:
    cache = FakeResponseCache()
    cache.put("华为P60退货政策", "缓存答案")
    deps = make_deps(cache=cache, llm=FakeLLM(chat_response="不该走到这里"))
    result = run_graph(deps, {"user_query": "华为P60退货政策"})
    assert result["final_response"] == "缓存答案"
    assert result["route_taken"] == "cache"


def test_chat_route() -> None:
    deps = make_deps(
        llm=FakeLLM(
            chat_response="你好呀！",
            intent_response={
                "intent_type": "chat",
                "entities": {},
                "rewritten_query": "",
                "clarify_questions": [],
            },
        )
    )
    result = run_graph(deps, {"user_query": "你好"})
    assert result["final_response"] == "你好呀！"
    assert result["route_taken"] == "chat"


def test_rag_route_end_to_end() -> None:
    deps = make_deps(
        llm=FakeLLM(
            chat_response="华为P60支持7天无理由退货。",
            intent_response={
                "intent_type": "rag",
                "entities": {"product": "华为P60"},
                "rewritten_query": "华为P60 退货政策",
                "clarify_questions": [],
            },
        ),
        retrieve=FakeRetrievePipeline(docs=[{"content": "华为P60支持7天无理由退货。"}]),
    )
    result = run_graph(deps, {"user_query": "华为P60怎么退货"})
    assert result["final_response"] == "华为P60支持7天无理由退货。"
    assert result["route_taken"] == "answer"


def test_sql_route_end_to_end() -> None:
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
    result = run_graph(deps, {"user_query": "华为P60多少钱"})
    assert result["final_response"] == "华为P60售价6999元。"
    assert result["route_taken"] == "answer"


def test_commission_keyword_goes_sql_even_if_llm_says_chat() -> None:
    deps = make_deps(
        llm=FakeLLM(
            chat_response="黑木耳抽成 15%。",
            intent_response={
                "intent_type": "chat",
                "entities": {},
                "rewritten_query": "",
                "clarify_questions": [],
            },
        ),
        nl2sql=FakeNL2SQLPipeline(rows=[{"rate": 15}]),
    )
    result = run_graph(deps, {"user_query": "黑木耳抽成多少"})
    assert result["intent_type"] == "sql"
    assert result["final_response"] == "黑木耳抽成 15%。"
    assert result["route_taken"] == "answer"


def test_rag_sql_parallel_with_one_failure() -> None:
    deps = make_deps(
        llm=FakeLLM(
            chat_response="华为P60销量为10000台，售后支持7天无理由退货。",
            intent_response={
                "intent_type": "rag+sql",
                "entities": {"product": "华为P60"},
                "rewritten_query": "华为P60 销量和售后政策",
                "clarify_questions": [],
            },
        ),
        retrieve=FakeRetrievePipeline(result=RuntimeError("milvus down")),
        nl2sql=FakeNL2SQLPipeline(rows=[{"sales": 10000}]),
    )
    result = run_graph(deps, {"user_query": "华为P60销量和售后政策"})
    assert result["final_response"] == "华为P60销量为10000台，售后支持7天无理由退货。"
    assert result["sql_rows"] == [{"sales": 10000}]


def test_rag_sql_both_empty_falls_back() -> None:
    deps = make_deps(
        llm=FakeLLM(
            intent_response={
                "intent_type": "rag+sql",
                "entities": {},
                "rewritten_query": "查不到",
                "clarify_questions": [],
            }
        ),
        retrieve=FakeRetrievePipeline(status="no_context"),
        nl2sql=FakeNL2SQLPipeline(status="executed", rows=[]),
    )
    result = run_graph(deps, {"user_query": "查不到"})
    assert result["final_response"] == FALLBACK_TEXT
    assert result["route_taken"] == "rag_sql_empty"


def test_clarification_resume_skips_cache_and_goes_intent() -> None:
    clarify_llm = FakeLLM(
        intent_response={
            "intent_type": "sql",
            "entities": {},
            "rewritten_query": "",
            "clarify_questions": ["请问您要查询哪个商品？"],
        }
    )
    first = run_graph(make_deps(llm=clarify_llm), {"user_query": "它的价格是多少"})
    assert first["needs_clarification"] is True
    assert first["clarify_questions"] == ["请问您要查询哪个商品？"]

    cache = FakeResponseCache()
    cache.put("它是华为P60", "缓存答案")
    resolved_llm = FakeLLM(
        chat_response="华为P60售价6999元。",
        intent_response={
            "intent_type": "sql",
            "entities": {"product": "华为P60"},
            "rewritten_query": "华为P60 的价格",
            "clarify_questions": [],
        },
    )
    deps = make_deps(
        llm=resolved_llm,
        nl2sql=FakeNL2SQLPipeline(rows=[{"price": 6999}]),
        cache=cache,
    )
    second = run_graph(
        deps,
        {
            "user_query": "它是华为P60",
            "history": [
                {"role": "user", "content": "它的价格是多少"},
                {"role": "assistant", "content": "请补充以下信息：请问您要查询哪个商品？"},
            ],
            "pending_clarification": True,
            "clarification_rounds": 1,
        },
    )
    assert second["needs_clarification"] is False
    assert second["final_response"] == "华为P60售价6999元。"

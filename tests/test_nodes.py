"""节点级测试：意图/实体回填、分支容错与兜底。"""

from __future__ import annotations

import asyncio

from config.business_config import FALLBACK_TEXT

from customer_service.nodes import build_nodes

from conftest import FakeLLM, FakeNL2SQLPipeline, FakeRetrievePipeline, make_deps


def run(node, state):
    return asyncio.run(node(state))


def test_intent_resolves_pronoun_with_memory() -> None:
    llm = FakeLLM(
        intent_response={
            "intent_type": "sql",
            "entities": {"product": "华为P60"},
            "rewritten_query": "华为P60 的价格是多少",
            "clarify_questions": [],
        }
    )
    deps = make_deps(llm=llm)
    result = run(
        build_nodes(deps)["intent"],
        {
            "user_query": "那它的价格是多少",
            "history": [
                {"role": "user", "content": "帮我查一下华为P60的退货政策"},
                {"role": "assistant", "content": "华为P60支持7天无理由退货。"},
            ],
            "memory_entities": {"product": "华为P60"},
        },
    )
    assert result["intent_type"] == "sql"
    assert result["rewritten_query"] == "华为P60 的价格是多少"
    assert result["memory_entities"] == {"product": "华为P60"}


def test_intent_asks_clarification_when_entity_missing() -> None:
    llm = FakeLLM(
        intent_response={
            "intent_type": "sql",
            "entities": {},
            "rewritten_query": "",
            "clarify_questions": ["请问您要查询哪个商品？"],
        }
    )
    deps = make_deps(llm=llm)
    result = run(build_nodes(deps)["intent"], {"user_query": "它的价格是多少"})
    assert result["needs_clarification"] is True
    assert result["clarify_questions"] == ["请问您要查询哪个商品？"]
    assert result["clarification_rounds"] == 1


def test_intent_keeps_query_when_entity_present() -> None:
    llm = FakeLLM(
        intent_response={
            "intent_type": "sql",
            "entities": {"product": "华为P60"},
            "rewritten_query": "改写后的华为P60价格",
            "clarify_questions": [],
        }
    )
    deps = make_deps(llm=llm)
    result = run(
        build_nodes(deps)["intent"],
        {"user_query": "华为P60抽成多少"},
    )
    assert result["intent_type"] == "sql"
    assert result["rewritten_query"] == "华为P60抽成多少"


def test_commission_keyword_overrides_intent_to_sql() -> None:
    llm = FakeLLM(
        intent_response={
            "intent_type": "chat",
            "entities": {},
            "rewritten_query": "随便聊聊",
            "clarify_questions": [],
        }
    )
    deps = make_deps(llm=llm)
    result = run(build_nodes(deps)["intent"], {"user_query": "黑木耳抽成多少"})
    assert result["intent_type"] == "sql"
    assert result["rewritten_query"] == "黑木耳抽成多少"


def test_product_list_routes_to_sql() -> None:
    llm = FakeLLM(
        intent_response={
            "intent_type": "rag",
            "entities": {},
            "rewritten_query": "",
            "clarify_questions": [],
        }
    )
    deps = make_deps(llm=llm)
    result = run(build_nodes(deps)["intent"], {"user_query": "你们有什么产品"})
    assert result["intent_type"] == "sql"


def test_compound_commission_with_rag_goes_rag_sql() -> None:
    llm = FakeLLM(
        intent_response={
            "intent_type": "chat",
            "entities": {},
            "rewritten_query": "",
            "clarify_questions": [],
        }
    )
    deps = make_deps(llm=llm)
    result = run(
        build_nodes(deps)["intent"],
        {"user_query": "黑木耳抽成多少，它的功效是什么"},
    )
    assert result["intent_type"] == "rag+sql"


def test_product_list_with_rag_goes_rag_sql() -> None:
    llm = FakeLLM(
        intent_response={
            "intent_type": "rag",
            "entities": {},
            "rewritten_query": "",
            "clarify_questions": [],
        }
    )
    deps = make_deps(llm=llm)
    result = run(
        build_nodes(deps)["intent"],
        {"user_query": "有什么产品，羊肚菌的功效是什么"},
    )
    assert result["intent_type"] == "rag+sql"


def test_two_products_commission_stays_sql() -> None:
    llm = FakeLLM(
        intent_response={
            "intent_type": "chat",
            "entities": {},
            "rewritten_query": "",
            "clarify_questions": [],
        }
    )
    deps = make_deps(llm=llm)
    result = run(build_nodes(deps)["intent"], {"user_query": "黑木耳和香菇的抽成多少"})
    assert result["intent_type"] == "sql"


def test_intent_rewrites_with_memory_entity_after_clarification() -> None:
    llm = FakeLLM(
        intent_response={
            "intent_type": "sql",
            "entities": {},
            "rewritten_query": "华为P60 抽成多少",
            "clarify_questions": [],
        }
    )
    deps = make_deps(llm=llm)
    result = run(
        build_nodes(deps)["intent"],
        {
            "user_query": "它的抽成多少",
            "memory_entities": {"product": "华为P60"},
        },
    )
    assert result["intent_type"] == "sql"
    assert result["rewritten_query"] == "华为P60 抽成多少"


def test_rag_empty_uses_fallback() -> None:
    deps = make_deps(retrieve=FakeRetrievePipeline(status="no_context"))
    result = run(build_nodes(deps)["rag"], {"user_query": "没有文档的问题"})
    assert result["context_docs"] == []
    assert result["final_response"] == FALLBACK_TEXT


def test_sql_executed_returns_rows() -> None:
    rows = [{"product": "华为P60", "price": 6999}]
    deps = make_deps(nl2sql=FakeNL2SQLPipeline(rows=rows))
    result = run(
        build_nodes(deps)["sql"],
        {
            "user_query": "华为P60的价格",
            "rewritten_query": "华为P60 的价格",
            "tenant_id": "t1",
            "db_id": "erp",
        },
    )
    assert result["sql_rows"] == rows
    assert result["route_taken"] == "sql"


def test_sql_clarification_propagates_questions() -> None:
    deps = make_deps(
        nl2sql=FakeNL2SQLPipeline(
            status="need_clarification",
            clarify_questions=["请补充时间范围"],
        )
    )
    result = run(build_nodes(deps)["sql"], {"user_query": "上个月的销售额"})
    assert result["needs_clarification"] is True
    assert result["clarify_questions"] == ["请补充时间范围"]


def test_rag_sql_one_branch_fails_other_wins() -> None:
    deps = make_deps(
        retrieve=FakeRetrievePipeline(result=RuntimeError("milvus down")),
        nl2sql=FakeNL2SQLPipeline(rows=[{"amount": 100}]),
    )
    result = run(
        build_nodes(deps)["rag_sql"],
        {
            "user_query": "华为P60销量和售后政策",
            "rewritten_query": "华为P60 销量和售后政策",
        },
    )
    assert result["sql_rows"] == [{"amount": 100}]
    assert result["context_docs"] == []
    assert result["route_taken"] == "rag_sql"


def test_rag_sql_both_empty_uses_fallback() -> None:
    deps = make_deps(
        retrieve=FakeRetrievePipeline(status="no_context"),
        nl2sql=FakeNL2SQLPipeline(status="executed", rows=[]),
    )
    result = run(build_nodes(deps)["rag_sql"], {"user_query": "查不到的问题"})
    assert result["final_response"] == FALLBACK_TEXT
    assert result["route_taken"] == "rag_sql_empty"


def test_answer_uses_context_and_rows() -> None:
    deps = make_deps(llm=FakeLLM(chat_response="根据数据，价格是6999元。"))
    result = run(
        build_nodes(deps)["answer"],
        {
            "user_query": "华为P60价格多少",
            "context_docs": [{"content": "华为P60是旗舰机型。"}],
            "sql_rows": [{"price": 6999}],
        },
    )
    assert "6999" in result["final_response"]
    assert result["context_text"]


def test_finalize_writes_response_cache() -> None:
    cache = __import__("conftest", fromlist=["FakeResponseCache"]).FakeResponseCache()
    deps = make_deps(cache=cache)
    result = run(
        build_nodes(deps)["finalize"],
        {"user_query": "问题", "final_response": "答案", "route_taken": "rag"},
    )
    assert result["final_response"] == "答案"
    assert cache.get("问题") == "答案"

---
name: customer_service_skill
description: 智能客服主流程。当 agent 需要让用户问题走完整客服链路（缓存检查、意图识别、基于会话记忆的指代消解与实体补全、知识库检索、业务库查询、回答生成、澄清追问）时调用 customer_chat；不要在已有可复用回答时重复调用。
---

# customer_service_skill

`customer_chat` 是面向 agent 的客服工具：传入用户消息与会话 ID，返回最终回答或澄清问题。

## 调用方式

工具名：`customer_chat`

| 参数 | 必填 | 说明 |
|---|---|---|
| `message` | 是 | 用户消息 |
| `session_id` | 否 | 会话 ID；不传自动生成并返回，同一会话后续必须沿用 |
| `tenant_id` | 否 | 默认取服务端 `TENANT_ID` |
| `kb_id` | 否 | 默认取服务端 `KB_ID` |
| `db_id` | 否 | 默认取服务端 `DB_ID` |
| `request_id` | 否 | 不传自动生成 |

清空会话短期记忆：`customer_session_clear(session_id)`。

## 返回值

```json
{
  "ok": true,
  "answer": "华为P60售价6999元",
  "needs_clarification": false,
  "clarify_questions": [],
  "session_id": "s1",
  "request_id": "req-1",
  "route_taken": "answer",
  "cache_hit": false,
  "intent_type": "sql",
  "entities": {"product": "华为P60"},
  "rewritten_query": "华为P60 的价格",
  "context_docs": [],
  "sql_rows": [{"price": 6999}],
  "sql_digest": {"row_count": 1}
}
```

## 处理约定

- `needs_clarification=true`：把 `clarify_questions` 原样转给用户，用户回答后带同一 `session_id` 继续调用。
- `route_taken`：`cache / chat / rag / sql / rag_sql / answer / intent_clarify / rag_sql_empty / error` 等。
- `cache_hit=true`：`answer` 直接来自缓存，无需再加工。
- 无结果兜底话术：`这个问题我暂时回答不了，稍后有人会主动联系您，请稍等一会`。


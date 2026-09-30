"""客服业务词汇、话术与默认参数。

此处只放客服层自己的业务配置；两个 pipeline 的配置仍走各自的 .env 命名空间。
"""

from __future__ import annotations

import os

FALLBACK_TEXT = "这个问题我暂时回答不了，稍后有人会主动联系您，请稍等一会"

HISTORY_MAX_MESSAGES = int(os.getenv("HISTORY_MAX_MESSAGES", "20"))
MAX_CLARIFICATION_ROUNDS = int(os.getenv("MAX_CLARIFICATION_ROUNDS", "2"))
RESPONSE_CACHE_PREFIX = os.getenv("RESPONSE_CACHE_PREFIX", "customer_service")
RESPONSE_CACHE_TTL = int(os.getenv("RESPONSE_CACHE_TTL", "1800"))
RESPONSE_CACHE_SHORT_TTL = int(os.getenv("RESPONSE_CACHE_SHORT_TTL", "300"))

DEFAULT_TENANT_ID = os.getenv("TENANT_ID", "merchant")
DEFAULT_KB_ID = os.getenv("KB_ID", "merchant_kb")
DEFAULT_DB_ID = os.getenv("DB_ID", "erp")

MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "8000"))
MAX_DOC_CHARS = int(os.getenv("MAX_DOC_CHARS", "2000"))
MAX_SQL_JSON_CHARS = int(os.getenv("MAX_SQL_JSON_CHARS", "6000"))

# 命中即强制走 sql 分支的经营数据关键词。
COMMISSION_KEYWORDS = (
    "佣金",
    "分成",
    "抽成",
    "毛利",
    "毛利率",
    "毛利额",
    "提成",
    "返点",
    "抽佣",
    "利润分成",
    "提点",
    "抽点",
)

# 产品清单/数量类问题也强制走 sql 分支。
PRODUCT_LIST_PHRASES = (
    "有什么产品",
    "有哪些产品",
    "产品有哪些",
    "有多少产品",
    "多少个产品",
    "几个产品",
    "产品列表",
    "产品目录",
    "有哪些商品",
    "有什么商品",
    "商品有哪些",
    "商品列表",
    "商品目录",
    "有什么货",
    "有哪些货",
)

# 检索意图提示词：与 SQL 关键词同时出现时，复合问题升级为 rag+sql。
RAG_HINT_KEYWORDS = (
    "功效",
    "营养",
    "好处",
    "作用",
    "政策",
    "流程",
    "介绍",
    "说明",
    "售后",
    "退换",
    "退货",
    "是什么",
    "怎么样",
    "为什么",
    "如何",
    "怎么",
    "能否",
    "能不能",
    "吃法",
    "价值",
    "吃",
)

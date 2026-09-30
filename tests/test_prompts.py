"""prompt 契约测试：领域同义词必须进入意图识别提示词。"""

from __future__ import annotations

from customer_service.prompts import (
    ANSWER_SYSTEM_PROMPT,
    CHAT_SYSTEM_PROMPT,
    CUSTOMER_SERVICE_PERSONA,
    INTENT_SYSTEM_PROMPT,
)


def test_intent_prompt_contains_commission_synonyms() -> None:
    for keyword in ("抽成", "抽佣", "提成", "返点", "毛利", "毛利率", "分成", "佣金"):
        assert keyword in INTENT_SYSTEM_PROMPT


def test_prompts_contain_customer_service_persona() -> None:
    for prompt in (INTENT_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT, ANSWER_SYSTEM_PROMPT):
        for keyword in ("有机地标", "带货达人", "博主", "主播", "佣金分成", "蘑菇"):
            assert keyword in prompt


def test_persona_hides_ai_identity() -> None:
    for forbidden in ("智能客服助手", "AI助手", "我是AI", "我是智能助手"):
        assert forbidden not in CUSTOMER_SERVICE_PERSONA


def test_persona_proactively_invites_and_retains() -> None:
    assert "主动联系" in CUSTOMER_SERVICE_PERSONA
    assert "留在对话里" in CUSTOMER_SERVICE_PERSONA
    assert "留下来" in CHAT_SYSTEM_PROMPT

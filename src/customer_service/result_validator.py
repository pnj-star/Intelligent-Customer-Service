"""两个 pipeline 返回结果（含异常）的统一校验。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BranchOutcome:
    valid: bool = False
    docs: list[dict[str, Any]] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    digest: dict[str, Any] | None = None
    needs_clarification: bool = False
    clarify_questions: list[str] = field(default_factory=list)
    message: str = ""
    kind: str = ""


def validate_retrieve_result(result: Any) -> BranchOutcome:
    """校验 retrieve_pipeline 结果。

    retrieve() 返回候选子块列表；retrieve_context() 返回 RetrieveResult。
    任一形式下 docs 非空视为有效；异常、空结果、error 都视为无效。
    """
    if isinstance(result, BaseException):
        return BranchOutcome(
            kind="exception",
            message=f"retrieve pipeline exception: {result}",
        )
    if result is None:
        return BranchOutcome(kind="error", message="retrieve pipeline returned None")
    if isinstance(result, list):
        docs = [dict(item) for item in result]
        if docs:
            return BranchOutcome(
                valid=True,
                docs=docs,
                kind="retrieved",
                message="",
            )
        return BranchOutcome(kind="no_context", message="retrieve returned empty docs")
    status = str(getattr(result, "status", "") or "")
    docs = [dict(item) for item in (getattr(result, "docs", None) or [])]
    if status in ("retrieved", "retrieved_cache") and docs:
        return BranchOutcome(
            valid=True,
            docs=docs,
            kind=status,
            message=str(getattr(result, "message", "") or ""),
        )
    if status in ("retrieved", "retrieved_cache"):
        return BranchOutcome(kind="no_context", message="retrieve returned empty docs")
    return BranchOutcome(
        kind="error",
        message=str(getattr(result, "message", "") or status or "unknown"),
    )


def validate_nl2sql_result(result: Any) -> BranchOutcome:
    """校验 nl2sql_pipeline 结果。

    executed 且 rows 非空视为有效；need_clarification 转追问；
    rejected_guardrail 保留 message；其余空/异常视为无效。
    """
    if isinstance(result, BaseException):
        return BranchOutcome(
            kind="exception",
            message=f"nl2sql pipeline exception: {result}",
        )
    if result is None:
        return BranchOutcome(kind="error", message="nl2sql pipeline returned None")
    status = str(getattr(result, "status", "") or "")
    rows = [dict(item) for item in (getattr(result, "rows", None) or [])]
    if status == "executed":
        if rows:
            return BranchOutcome(
                valid=True,
                rows=rows,
                digest=getattr(result, "digest", None),
                kind="executed",
                message=str(getattr(result, "message", "") or ""),
            )
        return BranchOutcome(kind="empty", message="sql query returned no rows")
    if status in ("generated", "generated_cache"):
        return BranchOutcome(
            kind="generated",
            message="SQL 已生成但没有可用的查询结果",
        )
    if status == "need_clarification":
        return BranchOutcome(
            needs_clarification=True,
            clarify_questions=[
                str(item) for item in (getattr(result, "clarify_questions", None) or [])
            ],
            kind="need_clarification",
            message=str(getattr(result, "message", "") or ""),
        )
    if status == "rejected_guardrail":
        return BranchOutcome(
            kind="guardrail",
            message=str(getattr(result, "message", "") or "查询被安全护栏拦截"),
        )
    return BranchOutcome(
        kind="error",
        message=str(getattr(result, "message", "") or status or "unknown"),
    )

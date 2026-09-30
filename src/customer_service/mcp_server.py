"""构建只暴露 customer_chat / customer_session_clear 的 FastMCP 服务器。"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from common_core.auth import AuthConfig
from common_core.mcp_auth import ToolContextGuard, build_mcp_auth

from .dependencies import CustomerServiceDependencies, build_default_dependencies
from .graph import build_graph

logger = logging.getLogger(__name__)


def _transport_auth_token() -> str | None:
    """HTTP 传输层校验通过后，从 FastMCP 上下文取回原始 JWT。"""
    try:
        from mcp.server.auth.middleware.auth_context import get_access_token

        access_token = get_access_token()
    except Exception:  # noqa: BLE001 - 非 HTTP 传输/未启用鉴权时优雅降级
        return None
    return access_token.token if access_token is not None else None


def _health_payload(
    name: str,
    config_source: str | None,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": name,
        "tools": ["customer_chat", "customer_session_clear"],
        "config": {
            "complete": True,
            "source": config_source or "process-env",
        },
    }


async def _run_chat(
    deps: CustomerServiceDependencies,
    graph: Any,
    *,
    message: str,
    session_id: str,
    tenant_id: str,
    kb_id: str,
    db_id: str,
    request_id: str,
) -> dict[str, Any]:
    """执行一轮完整客服流程，并维护会话短期记忆。"""
    memory = deps.memory
    await memory.append_message(session_id, "user", message)
    pending = await memory.get_pending_clarification(session_id)
    rounds = await memory.get_clarification_rounds(session_id)
    if pending:
        await memory.set_pending_clarification(session_id, False)

    state: dict[str, Any] = {
        "user_query": message,
        "history": await memory.get_history(session_id),
        "memory_entities": await memory.get_entities(session_id),
        "pending_clarification": pending,
        "clarification_rounds": rounds,
        "session_id": session_id,
        "request_id": request_id,
        "tenant_id": tenant_id,
        "kb_id": kb_id,
        "db_id": db_id,
    }
    result = await graph.ainvoke(state)

    await memory.set_entities(
        session_id,
        result.get("memory_entities") or result.get("entities") or {},
    )
    await memory.set_clarification_rounds(
        session_id,
        result.get("clarification_rounds", rounds),
    )

    payload: dict[str, Any] = {
        "ok": True,
        "answer": "",
        "needs_clarification": bool(result.get("needs_clarification")),
        "clarify_questions": list(result.get("clarify_questions") or []),
        "session_id": session_id,
        "request_id": request_id,
        "route_taken": result.get("route_taken") or "finalize",
        "cache_hit": bool(result.get("cache_hit")),
        "intent_type": result.get("intent_type") or "",
        "entities": result.get("memory_entities") or result.get("entities") or {},
        "rewritten_query": result.get("rewritten_query") or "",
        "context_docs": list(result.get("context_docs") or []),
        "sql_rows": list(result.get("sql_rows") or []),
        "sql_digest": result.get("sql_digest"),
    }

    if payload["needs_clarification"]:
        await memory.set_pending_clarification(session_id, True)
        await memory.append_message(
            session_id,
            "assistant",
            "请补充以下信息：" + " ".join(payload["clarify_questions"]),
        )
        return payload

    answer = result.get("final_response") or ""
    await memory.append_message(session_id, "assistant", answer)
    payload["answer"] = answer
    return payload


def create_mcp_server(
    deps: CustomerServiceDependencies | None = None,
    *,
    auth: AuthConfig | None = None,
    config_source: str | None = None,
    name: str = "customer-service",
    host: str | None = None,
    port: int | None = None,
    streamable_path: str = "/streamable",
    sse_path: str = "/sse",
    log_level: str = "INFO",
    debug: bool = False,
    instructions: str = (
        "智能客服主流程工具。传入用户消息和会话 ID，自动完成回答缓存检查、"
        "意图识别、基于会话短期记忆的指代消解与实体补全，然后路由到知识库检索"
        "（rag）/ 业务库查询（sql）/ 闲聊（chat），最后生成最终回答。"
        "缺必要实体时返回 needs_clarification=true 和 clarify_questions，"
        "请原样转给用户；用户回答后携带同一 session_id 继续调用即可。"
        "若 AUTH_MODE=jwt 开启，HTTP 调用通过 Authorization Bearer 头传递 JWT，"
        "也可在工具参数里传 auth_token。"
    ),
) -> Any:
    """构建只暴露客服工具的 FastMCP 服务器。"""
    from mcp.server.fastmcp import FastMCP

    if deps is None:
        deps = build_default_dependencies()
    graph = build_graph(deps)
    auth_config = auth or AuthConfig.from_env()
    guard = ToolContextGuard(
        config=auth_config,
        require_tenant_id=True,
        require_kb_id=True,
        require_request_id=True,
    )
    token_verifier, auth_settings = build_mcp_auth(auth_config)
    mcp_kwargs: dict[str, Any] = {
        "streamable_http_path": streamable_path,
        "sse_path": sse_path,
        "log_level": log_level,
        "debug": debug,
    }
    if auth_settings is not None:
        mcp_kwargs["token_verifier"] = token_verifier
        mcp_kwargs["auth"] = auth_settings
    if host is not None:
        mcp_kwargs["host"] = host
    if port is not None:
        mcp_kwargs["port"] = port
    server = FastMCP(name=name, instructions=instructions, **mcp_kwargs)

    @server.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> JSONResponse:
        return JSONResponse(_health_payload(name, config_source))

    @server.tool()
    async def customer_chat(
        message: str,
        session_id: str = "",
        tenant_id: str = "",
        kb_id: str = "",
        db_id: str = "",
        request_id: str = "",
        auth_token: str | None = None,
    ) -> dict[str, Any]:
        """执行一轮智能客服对话，返回最终回答或澄清问题。

        Args:
            message: 用户消息，必填。
            session_id: 会话 ID；不传自动生成并返回，同一会话后续请求必须沿用。
            tenant_id: 租户 ID；不传用服务端默认值。
            kb_id: 知识库 ID；不传用服务端默认值。
            db_id: 业务数据库 ID；不传用服务端默认值。
            request_id: 请求 ID；不传自动生成。
            auth_token: JWT 令牌；HTTP 调用也可通过 Authorization Bearer 头传递。

        Returns:
            结构化字典：answer 为最终回答；needs_clarification=true 时
            clarify_questions 非空，需原样转给用户；route_taken 标识本次
            实际走的分支（cache / chat / rag / sql / rag_sql / answer 等）。
        """
        token = _transport_auth_token() or auth_token
        resolved_tenant = tenant_id or deps.tenant_id
        resolved_kb = kb_id or deps.kb_id
        resolved_db = db_id or deps.db_id
        resolved_request = request_id or uuid.uuid4().hex
        resolved_session = session_id or uuid.uuid4().hex
        context = guard.resolve(
            tenant_id=resolved_tenant,
            kb_id=resolved_kb,
            request_id=resolved_request,
            session_id=resolved_session,
            auth_token=token,
        )
        try:
            return await _run_chat(
                deps,
                graph,
                message=message,
                session_id=context.session_id or resolved_session,
                tenant_id=context.tenant_id,
                kb_id=context.kb_id,
                db_id=resolved_db,
                request_id=context.request_id,
            )
        except Exception as exc:  # noqa: BLE001 - 异常转成稳定结构，不炸给调用方
            logger.exception(
                "customer_chat failed tenant=%s kb=%s request=%s",
                context.tenant_id,
                context.kb_id,
                context.request_id,
            )
            return {
                "ok": False,
                "answer": "",
                "message": f"{type(exc).__name__}: {exc}",
                "needs_clarification": False,
                "clarify_questions": [],
                "session_id": context.session_id or resolved_session,
                "request_id": context.request_id,
                "route_taken": "error",
            }

    @server.tool()
    async def customer_session_clear(
        session_id: str,
        tenant_id: str = "",
        kb_id: str = "",
        request_id: str = "",
        auth_token: str | None = None,
    ) -> dict[str, Any]:
        """清空指定会话的内存短期记忆（历史与实体槽位）。

        Args:
            session_id: 要清空的会话 ID。
            tenant_id: 租户 ID；不传用服务端默认值。
            kb_id: 知识库 ID；不传用服务端默认值。
            request_id: 请求 ID；不传自动生成。
            auth_token: JWT 令牌；HTTP 调用也可通过 Authorization Bearer 头传递。

        Returns:
            结构化字典：cleared=true 表示清空成功。
        """
        token = _transport_auth_token() or auth_token
        context = guard.resolve(
            tenant_id=tenant_id or deps.tenant_id,
            kb_id=kb_id or deps.kb_id,
            request_id=request_id or uuid.uuid4().hex,
            session_id=session_id,
            auth_token=token,
        )
        await deps.memory.clear(context.session_id or session_id)
        return {
            "ok": True,
            "cleared": True,
            "session_id": context.session_id or session_id,
        }

    return server


__all__ = ["create_mcp_server"]


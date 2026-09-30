"""FastAPI 入口：维护会话短期记忆，并调用 LangGraph 主流程。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .dependencies import build_default_dependencies
from .graph import build_graph


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str = ""
    tenant_id: str | None = None
    kb_id: str | None = None
    db_id: str | None = None


class ChatResponse(BaseModel):
    answer: str = ""
    needs_clarification: bool = False
    clarify_questions: list[str] = []
    session_id: str
    request_id: str
    route_taken: str


def create_app(env_file: str | None = None) -> FastAPI:
    app = FastAPI(title="Intelligent Customer Service", version="0.1.0")
    holder: dict[str, Any] = {"deps": None, "graph": None}

    def ensure_ready() -> tuple[Any, Any]:
        if holder["graph"] is None:
            deps = build_default_dependencies(env_file=env_file)
            holder["deps"] = deps
            holder["graph"] = build_graph(deps)
        return holder["deps"], holder["graph"]

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest) -> ChatResponse:
        deps, graph = ensure_ready()
        session_id = request.session_id or uuid.uuid4().hex
        request_id = uuid.uuid4().hex
        memory = deps.memory

        await memory.append_message(session_id, "user", request.message)
        pending = await memory.get_pending_clarification(session_id)
        rounds = await memory.get_clarification_rounds(session_id)
        if pending:
            await memory.set_pending_clarification(session_id, False)

        state: dict[str, Any] = {
            "user_query": request.message,
            "history": await memory.get_history(session_id),
            "memory_entities": await memory.get_entities(session_id),
            "pending_clarification": pending,
            "clarification_rounds": rounds,
            "session_id": session_id,
            "request_id": request_id,
            "tenant_id": request.tenant_id or deps.tenant_id,
            "kb_id": request.kb_id or deps.kb_id,
            "db_id": request.db_id or deps.db_id,
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

        if result.get("needs_clarification"):
            questions = list(result.get("clarify_questions") or [])
            await memory.set_pending_clarification(session_id, True)
            prompt_text = "请补充以下信息：" + " ".join(questions)
            await memory.append_message(session_id, "assistant", prompt_text)
            return ChatResponse(
                answer="",
                needs_clarification=True,
                clarify_questions=questions,
                session_id=session_id,
                request_id=request_id,
                route_taken=result.get("route_taken") or "intent_clarify",
            )

        answer = result.get("final_response") or ""
        await memory.append_message(session_id, "assistant", answer)
        return ChatResponse(
            answer=answer,
            needs_clarification=False,
            clarify_questions=[],
            session_id=session_id,
            request_id=request_id,
            route_taken=result.get("route_taken") or "finalize",
        )

    return app


def main() -> None:
    import os
    import uvicorn

    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run(create_app(), host=host, port=port)


__all__ = ["ChatRequest", "ChatResponse", "create_app", "main"]

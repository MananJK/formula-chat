"""
Chat router — POST /chat (non-streaming) and POST /chat/stream (SSE streaming).
"""

import uuid
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agent import run_agent, stream_agent
from app.limiter import limiter
from app.models.schemas import ChatRequest, ChatResponse, StreamChunk
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Non-streaming endpoint
# ---------------------------------------------------------------------------

@router.post("", response_model=ChatResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """
    Send a message to the F1 agent and receive a complete answer.

    Use this endpoint for simple integrations that don't need streaming.
    For a better UX in chat interfaces, prefer POST /chat/stream.
    """
    conversation_id = body.conversation_id or str(uuid.uuid4())
    history = [m.model_dump() for m in body.history] if body.history else None

    answer = await run_agent(message=body.message, history=history)

    return ChatResponse(
        answer=answer,
        conversation_id=conversation_id,
        tool_calls=[],
    )


# ---------------------------------------------------------------------------
# Streaming endpoint (Server-Sent Events)
# ---------------------------------------------------------------------------

@router.post("/stream")
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    """
    Stream the F1 agent's response as Server-Sent Events.

    Event types:
      - `delta`      — a text chunk to append to the UI
      - `tool_call`  — the agent invoked a tool (name included)
      - `done`       — stream complete; full answer in `content`
      - `error`      — an error occurred

    Example SSE message:
      data: {"type": "delta", "content": "Lewis Hamilton"}
    """
    conversation_id = body.conversation_id or str(uuid.uuid4())
    history = [m.model_dump() for m in body.history] if body.history else None

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for event_type, payload in stream_agent(
                message=body.message, history=history
            ):
                chunk = StreamChunk(
                    type=event_type,
                    content=payload if event_type in ("delta", "done", "error") else "",
                    tool_name=payload if event_type == "tool_call" else None,
                    conversation_id=conversation_id if event_type == "done" else None,
                )
                yield f"data: {chunk.model_dump_json()}\n\n"
        except Exception as exc:
            logger.error("Stream error: %s", exc)
            error_chunk = StreamChunk(type="error", content=str(exc))
            yield f"data: {error_chunk.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

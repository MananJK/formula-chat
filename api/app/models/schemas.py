from pydantic import BaseModel, Field
from typing import Literal


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User question")
    conversation_id: str | None = Field(None, description="Optional conversation ID for multi-turn context")
    history: list[Message] = Field(default_factory=list, description="Prior conversation turns")


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    tool_calls: list[str] = Field(default_factory=list, description="Names of tools invoked during the response")


class StreamChunk(BaseModel):
    type: Literal["delta", "tool_call", "done", "error"]
    content: str = ""
    tool_name: str | None = None
    conversation_id: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    components: dict[str, str]

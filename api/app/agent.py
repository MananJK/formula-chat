"""
F1 agent — built with the OpenAI Agents SDK.

The agent is given:
  - A system prompt containing the full database schema and tool descriptions
  - Two tools: sql_query, f1_knowledge
  - Autonomy to choose which tool(s) to call, in what order, and how to
    combine results before producing a final natural-language answer.
"""

from agents import Agent, Runner, function_tool, RunConfig, RawResponsesStreamEvent, RunItemStreamEvent
from agents.models.openai_responses import OpenAIResponsesModel

from app.config import settings
from app.tools.sql_query import sql_query, SCHEMA_DESCRIPTION
from app.tools.f1_knowledge import f1_knowledge

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""
You are an expert Formula One assistant with access to three data tools.
Always use the most appropriate tool (or combination of tools) to answer
precisely and completely. Cite your sources where relevant.

## Tools

### sql_query
Runs a read-only SELECT query against a PostgreSQL database containing F1 data
from 2018 through the current **2026 season** (imported via FastF1). Use this for:
- Current 2026 championship standings and points
- 2026 race results, grid positions, qualifying times
- Driver career statistics (wins, poles, podiums) across all seasons
- Constructor statistics and team comparisons
- Lap times and pit stop data
- Historical records, season comparisons, and trends
- Always filter by `races.year` for season-specific queries

### f1_knowledge
Performs a semantic search over a curated knowledge base of F1 content
(driver profiles, team histories, regulations, race reports). Use this for:
- Driver or team background and history
- Technical or sporting regulation questions
- Race narratives and analysis
- Circuit descriptions and characteristics

## Rules
- Only SELECT statements may be generated for sql_query.
- Never fabricate data — if a tool returns no results, say so.
- Combine tool outputs when questions span multiple domains.
- Keep answers concise but complete.
- Format numbers clearly (e.g. lap times as M:SS.mmm).

## Database Schema

{SCHEMA_DESCRIPTION}
""".strip()


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

_sql_tool = function_tool(sql_query)
_knowledge_tool = function_tool(f1_knowledge)


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def create_agent() -> Agent:
    """Return a configured F1 agent instance."""
    return Agent(
        name="F1 Assistant",
        instructions=SYSTEM_PROMPT,
        model=OpenAIResponsesModel(
            model=settings.openai_model,
            openai_client=_openai_client(),
        ),
        tools=[_sql_tool, _knowledge_tool],
    )


def _openai_client():
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=settings.openai_api_key)


# ---------------------------------------------------------------------------
# Runner helpers
# ---------------------------------------------------------------------------

async def run_agent(message: str, history: list[dict] | None = None) -> str:
    """
    Run the agent for a single turn and return the final text response.

    Args:
        message: The user's current message.
        history: Optional list of prior turns as {"role": ..., "content": ...} dicts.

    Returns:
        The agent's final answer as a plain string.
    """
    agent = create_agent()
    input_messages = _build_input(message, history)

    result = await Runner.run(
        agent,
        input=input_messages,
        run_config=RunConfig(tracing_disabled=not settings.is_production),
    )
    return str(result.final_output)


async def stream_agent(message: str, history: list[dict] | None = None):
    """
    Stream the agent's response token-by-token.

    Yields:
        Tuples of (event_type, payload) where event_type is one of:
          - "delta": a text token chunk (payload is str)
          - "tool_call": a tool was invoked (payload is tool name str)
          - "done": stream complete (payload is final full text str)
    """
    agent = create_agent()
    input_messages = _build_input(message, history)

    # run_streamed returns RunResultStreaming directly (not a context manager)
    stream = Runner.run_streamed(
        agent,
        input=input_messages,
        run_config=RunConfig(tracing_disabled=not settings.is_production),
    )

    async for event in stream.stream_events():
        if isinstance(event, RawResponsesStreamEvent):
            inner_type = getattr(event.data, "type", None)
            if inner_type == "response.output_text.delta":
                delta = getattr(event.data, "delta", "")
                if delta:
                    yield ("delta", delta)

        elif isinstance(event, RunItemStreamEvent):
            if event.name == "tool_called":
                tool_name = getattr(event.item, "raw_item", None)
                name = getattr(tool_name, "name", "unknown_tool") if tool_name else "unknown_tool"
                yield ("tool_call", name)

    yield ("done", str(stream.final_output))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_input(message: str, history: list[dict] | None) -> list[dict] | str:
    """Construct the input for the Runner from message + optional history."""
    if not history:
        return message

    turns = [{"role": t["role"], "content": t["content"]} for t in history]
    turns.append({"role": "user", "content": message})
    return turns

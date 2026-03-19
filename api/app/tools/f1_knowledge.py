"""
f1_knowledge tool — semantic search over the pgvector RAG knowledge base.

Content includes driver profiles, team history, circuit guides, regulation
documents, and race reports — scraped offline and embedded with
text-embedding-3-small.
"""

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool function
# ---------------------------------------------------------------------------

async def f1_knowledge(query: str, top_k: int | None = None) -> dict[str, Any]:
    """
    Search the F1 knowledge base (pgvector RAG) for relevant context.

    Use this for questions about driver profiles, team history, circuit
    descriptions, technical/sporting regulations, and race narratives that
    are not answered by structured SQL data.

    Args:
        query: Natural language query to embed and search.
        top_k: Number of results to return (default from settings).

    Returns:
        A dict with:
          - results: list of matched chunks, each with:
              - content: the text chunk
              - source: document source / URL
              - score: cosine similarity score
          - result_count: number of results returned
    """
    import asyncpg

    k = top_k or settings.rag_top_k

    embedding = await _embed(query)
    if embedding is None:
        return {"error": "Failed to generate query embedding.", "results": [], "result_count": 0}

    try:
        conn: asyncpg.Connection = await asyncpg.connect(settings.database_url)
    except Exception as exc:
        logger.error("DB connection error: %s", exc)
        return {"error": "Failed to connect to knowledge base.", "results": [], "result_count": 0}

    try:
        # pgvector cosine distance operator: <=>
        rows = await conn.fetch(
            """
            SELECT content, source, 1 - (embedding <=> $1::vector) AS score
            FROM f1_knowledge
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            str(embedding),
            k,
        )
        results = [
            {"content": r["content"], "source": r["source"], "score": float(r["score"])}
            for r in rows
        ]
        return {"results": results, "result_count": len(results)}
    except Exception as exc:
        logger.error("RAG query error: %s", exc)
        return {"error": f"Knowledge base query failed: {exc}", "results": [], "result_count": 0}
    finally:
        await conn.close()


async def _embed(text: str) -> list[float] | None:
    """Generate an embedding vector using the OpenAI embeddings API."""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=text,
        )
        return response.data[0].embedding
    except Exception as exc:
        logger.error("Embedding error: %s", exc)
        return None

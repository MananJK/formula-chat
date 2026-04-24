"""
sql_query tool — runs read-only SQL against the F1 PostgreSQL database.

The database contains the full F1 dataset from 2018 through the current 2026
season, imported via FastF1. The agent writes its own SQL queries based on the
schema provided in its system prompt. Queries are validated with sqlglot and
executed with a 5-second timeout against a read-only database user.
"""

import asyncio
import hashlib
import logging
import time
from typing import Any

import sqlglot

from app.config import settings
from app.db import get_pool
from app.cache import cache_get, cache_set
from app.metrics import (
    increment_sql_cache_hit,
    increment_sql_cache_miss,
    record_sql_latency,
    increment_total_requests,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema context injected into the agent system prompt
# ---------------------------------------------------------------------------

SCHEMA_DESCRIPTION = """
The PostgreSQL database contains F1 data from 2018 through the current 2026
season, imported via FastF1. Use this tool for any question about race results,
standings, qualifying, or lap data — including the 2026 season.

Tables and columns:

circuits(circuitId, circuitRef, name, location, country, lat, lng, alt, url)
constructor_results(constructorResultsId, raceId, constructorId, points, status)
constructor_standings(constructorStandingsId, raceId, constructorId, points, position, positionText, wins)
constructors(constructorId, constructorRef, name, nationality, url)
driver_standings(driverStandingsId, raceId, driverId, points, position, positionText, wins)
drivers(driverId, driverRef, number, code, forename, surname, dob, nationality, url)
lap_times(raceId, driverId, lap, position, time, milliseconds)
pit_stops(raceId, driverId, stop, lap, time, duration, milliseconds)
qualifying(qualifyId, raceId, driverId, constructorId, number, position, q1, q2, q3)
races(raceId, year, round, circuitId, name, date, time, url, fp1_date, fp1_time, fp2_date, fp2_time, fp3_date, fp3_time, quali_date, quali_time, sprint_date, sprint_time)
results(resultId, raceId, driverId, constructorId, number, grid, position, positionText, positionOrder, points, laps, time, milliseconds, fastestLap, rank, fastestLapTime, fastestLapSpeed, statusId)
seasons(year, url)
sprint_results(sprintResultId, raceId, driverId, constructorId, number, grid, position, positionText, positionOrder, points, laps, time, milliseconds, fastestLap, fastestLapTime, statusId)
status(statusId, status)

Key relationships:
- races.circuitId → circuits.circuitId
- races.year → seasons.year  (filter by year for season-specific queries)
- results.raceId → races.raceId
- results.driverId → drivers.driverId
- results.constructorId → constructors.constructorId
- driver_standings.raceId → races.raceId (cumulative standings after each round)
- qualifying.raceId → races.raceId

Notes:
- Always filter by races.year when asking about a specific season (e.g. WHERE r.year = 2026).
- driver_standings and constructor_standings are cumulative: to get the current
  championship standings, join to the most recent raceId for the season.
- lap_times.time and qualifying q1/q2/q3 are stored as 'M:SS.mmm' strings.
- pit_stops.duration is stored as a decimal seconds string (e.g. '23.456').
""".strip()


# ---------------------------------------------------------------------------
# Query validation
# ---------------------------------------------------------------------------

def _validate_sql(query: str) -> str:
    """Parse and validate SQL with sqlglot; raise ValueError if invalid or mutating."""
    try:
        statements = sqlglot.parse(query, dialect="postgres")
    except sqlglot.errors.ParseError as exc:
        raise ValueError(f"SQL parse error: {exc}") from exc

    if not statements:
        raise ValueError("Empty SQL query.")

    if len(statements) > 1:
        raise ValueError("Only a single SQL statement is allowed per query.")

    stmt = statements[0]
    if not isinstance(stmt, sqlglot.expressions.Select):
        raise ValueError("Only SELECT statements are permitted.")

    return query.strip()


# ---------------------------------------------------------------------------
# Tool function
# ---------------------------------------------------------------------------

async def sql_query(query: str) -> dict[str, Any]:
    print('Using sql_query tool with query:', query)
    start_time = time.perf_counter()
    await increment_total_requests()
    """
    Execute a read-only SQL SELECT against the F1 PostgreSQL database (2018–2026).

    Args:
        query: A SELECT statement. The full schema is provided in the system
               prompt. Only SELECT is allowed — no mutations.

    Returns:
        A dict with keys:
          - rows: list of result rows (each row is a dict)
          - row_count: number of rows returned
          - columns: list of column names
    """
    try:
        validated = _validate_sql(query)
    except ValueError as exc:
        return {"error": str(exc), "rows": [], "row_count": 0, "columns": []}

    cache_key = f"sql:{hashlib.sha256(validated.encode()).hexdigest()}"
    cached = await cache_get(cache_key)
    if cached:
        await increment_sql_cache_hit()
        latency_ms = (time.perf_counter() - start_time) * 1000
        await record_sql_latency(latency_ms)
        return cached

    await increment_sql_cache_miss()

    try:
        pool = get_pool()
    except RuntimeError as exc:
        logger.error("DB pool not available: %s", exc)
        return {"error": "Database pool not available.", "rows": [], "row_count": 0, "columns": []}

    try:
        async with pool.acquire() as conn:
            records = await asyncio.wait_for(
                conn.fetch(validated),
                timeout=settings.database_query_timeout,
            )
        columns = list(records[0].keys()) if records else []
        rows = [dict(r) for r in records]
        result = {"rows": rows, "row_count": len(rows), "columns": columns}

        ttl = _determine_cache_ttl(validated)
        await cache_set(cache_key, result, ttl)

        latency_ms = (time.perf_counter() - start_time) * 1000
        await record_sql_latency(latency_ms)

        return result
    except asyncio.TimeoutError:
        return {"error": "Query timed out (5s limit).", "rows": [], "row_count": 0, "columns": []}
    except Exception as exc:
        logger.error("Query execution error: %s", exc)
        return {"error": f"Query error: {exc}", "rows": [], "row_count": 0, "columns": []}


def _determine_cache_ttl(query: str) -> int:
    query_lower = query.lower()
    if "standings" in query_lower or "championship" in query_lower:
        return 300
    elif "races.year" in query_lower or "round" in query_lower:
        return 3600
    elif "current" in query_lower:
        return 60
    return settings.sql_cache_ttl

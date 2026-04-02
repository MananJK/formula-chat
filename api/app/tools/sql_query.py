"""
sql_query tool — runs read-only SQL against the F1 PostgreSQL database.

The database contains the full F1 dataset from 2018 through the current 2026
season, imported via FastF1. The agent writes its own SQL queries based on the
schema provided in its system prompt. Queries are validated with sqlglot and
executed with a 5-second timeout against a read-only database user.
"""

import asyncio
import logging
from typing import Any

import sqlglot
import asyncpg

from app.config import settings

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

    try:
        conn: asyncpg.Connection = await asyncio.wait_for(
            asyncpg.connect(settings.database_url),
            timeout=settings.database_query_timeout,
        )
    except asyncio.TimeoutError:
        return {"error": "Database connection timed out.", "rows": [], "row_count": 0, "columns": []}
    except Exception as exc:
        logger.error("DB connection error: %s", exc)
        return {"error": "Failed to connect to database.", "rows": [], "row_count": 0, "columns": []}

    try:
        records = await asyncio.wait_for(
            conn.fetch(validated),
            timeout=settings.database_query_timeout,
        )
        columns = list(records[0].keys()) if records else []
        rows = [dict(r) for r in records]
        return {"rows": rows, "row_count": len(rows), "columns": columns}
    except asyncio.TimeoutError:
        return {"error": "Query timed out (5s limit).", "rows": [], "row_count": 0, "columns": []}
    except Exception as exc:
        logger.error("Query execution error: %s", exc)
        return {"error": f"Query error: {exc}", "rows": [], "row_count": 0, "columns": []}
    finally:
        await conn.close()

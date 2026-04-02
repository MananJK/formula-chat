"""
build_db.py — Full historical F1 database import using FastF1.

Downloads Race and Qualifying sessions for each round via FastF1 (which
caches data locally) and upserts into the local PostgreSQL database.
FastF1 reliably covers 2018–present. Safe to re-run: all inserts use
ON CONFLICT DO NOTHING or ON CONFLICT DO UPDATE.

Usage:
    python scripts/build_db.py                        # 2018–current
    python scripts/build_db.py --season 2024          # single season
    python scripts/build_db.py --from-season 2022 --to-season 2024

Environment variables (or .env file in repo root):
    DATABASE_URL          — e.g. postgresql://f1_user:pass@localhost:5433/f1
    FASTF1_CACHE_DIR      — path to FastF1 cache (default: .fastf1_cache)
    ROUND_DELAY           — seconds to sleep between rounds (default: 10.0)
    SESSION_DELAY         — seconds to sleep between Q and R sessions (default: 5.0)
    RETRY_ATTEMPTS        — max retries per session load (default: 5)
    RETRY_BACKOFF_MAX     — cap on exponential backoff in seconds (default: 120.0)

"""

import asyncio
import argparse
import logging
import math
import os
import random
import re
import sys
from datetime import date
from typing import Any

import asyncpg
import fastf1
import fastf1.req
import pandas as pd
from dotenv import load_dotenv

# Load scripts/.env first (local overrides), then fall back to api/.env
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(_scripts_dir, ".env"))
load_dotenv(dotenv_path=os.path.join(_scripts_dir, "../api/.env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

CACHE_DIR = os.environ.get("FASTF1_CACHE_DIR", ".fastf1_cache")
DEFAULT_FROM = 2021  # FastF1 reliable coverage starts here
ROUND_DELAY = float(os.environ.get("ROUND_DELAY", "10.0"))  # seconds between rounds
SESSION_DELAY = float(os.environ.get("SESSION_DELAY", "5.0"))   # seconds between Q and R within a round
RETRY_ATTEMPTS = int(os.environ.get("RETRY_ATTEMPTS", "5"))     # retries before stopping
RETRY_BACKOFF_MAX = float(os.environ.get("RETRY_BACKOFF_MAX", "120.0"))  # cap on backoff (seconds)


class RateLimitError(Exception):
    """Raised when a FastF1 session load fails persistently (rate limit or server error)."""


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

async def _load_session_with_retry(session: fastf1.core.Session, **load_kwargs) -> None:
    """Load a FastF1 session with exponential backoff and jitter.

    Detects rate-limit responses (HTTP 429 / "too many requests") and applies
    a longer initial pause before retrying. Any persistent failure after all
    retries is raised as a RateLimitError so the caller can stop cleanly and
    report where to resume from.
    """
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: session.load(**load_kwargs)
            )
            return
        except fastf1.req.RateLimitExceededError as exc:
            if attempt == RETRY_ATTEMPTS:
                raise RateLimitError(str(exc)) from exc

            # Back off more aggressively on an explicit rate-limit signal
            base_wait = min(RETRY_BACKOFF_MAX, 2 ** attempt)
            jitter = random.uniform(0, base_wait * 0.25)
            wait = min(RETRY_BACKOFF_MAX, (base_wait + jitter) * 2)
            log.warning(
                "    Rate limit exceeded (attempt %d/%d): %s — retrying in %.0fs",
                attempt, RETRY_ATTEMPTS, exc, wait,
            )
            await asyncio.sleep(wait)
        except Exception as exc:
            if attempt == RETRY_ATTEMPTS:
                raise RateLimitError(str(exc)) from exc

            err_lower = str(exc).lower()
            is_rate_limit = any(
                kw in err_lower for kw in ("429", "rate limit", "too many requests", "ratelimit")
            )

            # Exponential backoff capped at RETRY_BACKOFF_MAX, plus random jitter
            base_wait = min(RETRY_BACKOFF_MAX, 2 ** attempt)
            jitter = random.uniform(0, base_wait * 0.25)
            wait = base_wait + jitter

            if is_rate_limit:
                wait = min(RETRY_BACKOFF_MAX, wait * 2)
                log.warning(
                    "    Rate limit detected (attempt %d/%d): %s — retrying in %.0fs",
                    attempt, RETRY_ATTEMPTS, exc, wait,
                )
            else:
                log.warning(
                    "    Session load failed (attempt %d/%d): %s — retrying in %.0fs",
                    attempt, RETRY_ATTEMPTS, exc, wait,
                )
            await asyncio.sleep(wait)


# ---------------------------------------------------------------------------
# Type coercion helpers (also imported by sync_current.py)
# ---------------------------------------------------------------------------

def _int(val: Any) -> int | None:
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _date(val: Any):
    if not val:
        return None
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def _float_safe(val) -> float | None:
    """Convert to float, returning None for NaN/None/invalid values."""
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _timedelta_str(td) -> str | None:
    """Convert a pandas Timedelta to a lap-time string (M:SS.mmm or H:MM:SS.mmm)."""
    try:
        if td is None or pd.isna(td):
            return None
    except (TypeError, ValueError):
        pass
    if not hasattr(td, "total_seconds"):
        return None
    total_s = td.total_seconds()
    if total_s <= 0:
        return None
    h = int(total_s // 3600)
    m = int((total_s % 3600) // 60)
    s = total_s % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:06.3f}"
    return f"{m}:{s:06.3f}"


# ---------------------------------------------------------------------------
# Upsert helpers
# ---------------------------------------------------------------------------

async def upsert_season(conn: asyncpg.Connection, year: int, url: str) -> None:
    await conn.execute(
        "INSERT INTO seasons(year, url) VALUES($1, $2) ON CONFLICT (year) DO NOTHING",
        year, url,
    )


async def upsert_circuit(conn: asyncpg.Connection, c: dict) -> None:
    """Upsert a circuit from a FastF1 event row dict."""
    circuit_id = c["circuitId"]
    await conn.execute(
        """
        INSERT INTO circuits(circuitId, circuitRef, name, location, country, lat, lng)
        VALUES($1,$2,$3,$4,$5,$6,$7)
        ON CONFLICT (circuitId) DO UPDATE SET
            name=EXCLUDED.name, location=EXCLUDED.location,
            country=EXCLUDED.country
        """,
        circuit_id, circuit_id, c.get("name", circuit_id),
        c.get("location"), c.get("country"),
        _float_safe(c.get("lat")), _float_safe(c.get("lng")),
    )


async def upsert_driver(conn: asyncpg.Connection, d: dict) -> None:
    await conn.execute(
        """
        INSERT INTO drivers(driverId, driverRef, number, code, forename, surname, dob, nationality, url)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)
        ON CONFLICT (driverId) DO UPDATE SET
            number=EXCLUDED.number, code=EXCLUDED.code,
            forename=EXCLUDED.forename, surname=EXCLUDED.surname,
            nationality=EXCLUDED.nationality
        """,
        d["driverId"], d["driverId"],
        _int(d.get("permanentNumber")), d.get("code"),
        d.get("givenName"), d.get("familyName"),
        _date(d.get("dateOfBirth")), d.get("nationality"),
        d.get("url"),
    )


async def upsert_constructor(conn: asyncpg.Connection, c: dict) -> None:
    await conn.execute(
        """
        INSERT INTO constructors(constructorId, constructorRef, name, nationality, url)
        VALUES($1,$2,$3,$4,$5)
        ON CONFLICT (constructorId) DO UPDATE SET
            name=EXCLUDED.name, nationality=EXCLUDED.nationality
        """,
        c["constructorId"], c["constructorId"],
        c.get("name"), c.get("nationality"), c.get("url"),
    )


async def upsert_status(conn: asyncpg.Connection, status_text: str) -> int:
    row = await conn.fetchrow(
        "INSERT INTO status(status) VALUES($1) ON CONFLICT (status) DO NOTHING RETURNING statusId",
        status_text,
    )
    if row:
        return row["statusid"]
    return await conn.fetchval("SELECT statusId FROM status WHERE status=$1", status_text)


async def upsert_race_from_event(
    conn: asyncpg.Connection,
    year: int,
    round_num: int,
    event: pd.Series,
) -> int:
    """Upsert a race record from a FastF1 event row and return its raceId."""
    await upsert_season(conn, year, f"https://en.wikipedia.org/wiki/{year}_Formula_One_season")

    location = str(event.get("Location", ""))
    country = str(event.get("Country", ""))
    circuit_id = re.sub(r"[^a-z0-9]+", "_", location.lower()).strip("_") or f"circuit_{round_num}"

    # Match existing circuit by location to avoid duplicates across seasons
    existing_circuit = await conn.fetchval(
        "SELECT circuitId FROM circuits WHERE location ILIKE $1 LIMIT 1",
        f"%{location}%",
    )
    if existing_circuit:
        circuit_id = existing_circuit
    else:
        await upsert_circuit(conn, {
            "circuitId": circuit_id,
            "name": location,
            "location": location,
            "country": country,
        })

    row = await conn.fetchrow(
        """
        INSERT INTO races(year, round, circuitId, name, date)
        VALUES($1,$2,$3,$4,$5)
        ON CONFLICT (year, round) DO UPDATE SET
            circuitId=EXCLUDED.circuitId, name=EXCLUDED.name, date=EXCLUDED.date
        RETURNING raceId
        """,
        year, round_num, circuit_id,
        str(event.get("EventName", f"Round {round_num}")),
        _date(str(event["EventDate"])[:10]),
    )
    return row["raceid"]



# ---------------------------------------------------------------------------
# FastF1 constructor ID mapping (team name → Ergast-compatible id)
# ---------------------------------------------------------------------------

TEAM_CONSTRUCTOR_MAP: dict[str, str] = {
    # Current teams (2024–2026)
    "Red Bull Racing": "red_bull",
    "Mercedes": "mercedes",
    "Ferrari": "ferrari",
    "McLaren": "mclaren",
    "Aston Martin": "aston_martin",
    "Alpine": "alpine",
    "Williams": "williams",
    "Haas F1 Team": "haas",
    "Haas F1": "haas",
    "MoneyGram Haas F1 Team": "haas",
    "RB": "rb",
    "Racing Bulls": "racing_bulls",
    "Visa Cash App RB": "rb",
    "Kick Sauber": "sauber",
    # 2026 new entrants
    "Audi": "audi",
    "Cadillac": "cadillac",
    # 2019–2023: Alfa Romeo era (same Hinwil chassis, different branding)
    "AlphaTauri": "alphatauri",
    "Scuderia AlphaTauri": "alphatauri",
    "Alfa Romeo": "alfa",
    "Alfa Romeo Racing": "alfa",
    "Alfa Romeo Racing ORLEN": "alfa",
    "Alfa Romeo F1 Team ORLEN": "alfa",
    # 2018–2020: Force India → Racing Point
    "Racing Point": "racing_point",
    "Racing Point Force India": "racing_point",
    "BWT Racing Point F1 Team": "racing_point",
    # 2012–2018: Force India / Sahara Force India
    "Force India": "force_india",
    "Sahara Force India": "force_india",
    # 2016–2020: Renault works team return
    "Renault": "renault",
    # 2006–2015: Toro Rosso (Red Bull junior team)
    "Toro Rosso": "toro_rosso",
    "Scuderia Toro Rosso": "toro_rosso",
    # 2012–2014: Caterham (ex-Team Lotus)
    "Caterham": "caterham",
    # 2012–2015: Lotus F1 Team (ex-Renault)
    "Lotus F1": "lotus_f1",
    "Lotus F1 Team": "lotus_f1",
    # 2011: Team Lotus (became Caterham in 2012)
    "Team Lotus": "team_lotus",
    # 2010: Lotus Racing (became Team Lotus in 2011)
    "Lotus Racing": "lotus_racing",
    # 2012–2015: Marussia (ex-Virgin)
    "Marussia": "marussia",
    "Marussia F1 Team": "marussia",
    # 2015–2016: Manor (ex-Marussia)
    "Manor": "manor",
    "Manor Racing": "manor",
    "Manor Marussia": "manor",
    "Manor Racing MRT": "manor",
    # 2010–2012: HRT / Hispania Racing
    "HRT": "hrt",
    "Hispania Racing F1 Team": "hrt",
    "Hispania Racing": "hrt",
    # 2010–2011: Virgin Racing (became Marussia in 2012)
    "Virgin": "virgin",
    "Virgin Racing": "virgin",
    # 2009: Brawn GP (became Mercedes in 2010)
    "Brawn GP": "brawn_gp",
    "Brawn": "brawn_gp",
    # 2006–2009: BMW Sauber
    "BMW Sauber": "bmw_sauber",
    # 2002–2009: Toyota
    "Toyota": "toyota",
    # 2006–2008: Honda (became Brawn GP in 2009)
    "Honda": "honda",
    # 2006–2008: Super Aguri
    "Super Aguri": "super_aguri",
    # 2007: Spyker (ex-Midland, became Force India in 2008)
    "Spyker": "spyker",
    "Spyker F1": "spyker",
    # 2006: Midland F1 (became Spyker in 2007)
    "Midland": "midland",
    "Midland F1": "midland",
    "MF1 Racing": "midland",
    # Independent Sauber (before BMW and after BMW branding)
    "Sauber": "sauber",
    "Sauber F1 Team": "sauber",
}


def _constructor_id(team_name: str) -> str:
    if team_name in TEAM_CONSTRUCTOR_MAP:
        return TEAM_CONSTRUCTOR_MAP[team_name]
    return re.sub(r"[^a-z0-9]+", "_", team_name.lower()).strip("_")


# ---------------------------------------------------------------------------
# FastF1-based upsert functions
# ---------------------------------------------------------------------------

async def _upsert_results_from_session(
    conn: asyncpg.Connection,
    race_id: int,
    race_session: fastf1.core.Session,
) -> dict[str, str]:
    """
    Upsert race results from a FastF1 Race session.
    Returns a mapping of driver abbreviation → driverId.
    """
    results = race_session.results
    if results is None or results.empty:
        return {}

    laps_by_abbr: dict[str, int] = {}
    if race_session.laps is not None and not race_session.laps.empty:
        laps_by_abbr = (
            race_session.laps.groupby("Driver")["LapNumber"]
            .max().astype(int).to_dict()
        )

    abbr_to_driver_id: dict[str, str] = {}
    for _, row in results.iterrows():
        driver_id = str(row.get("DriverId") or "")
        team_name = str(row.get("TeamName") or "")
        cid = _constructor_id(team_name)
        abbr = str(row.get("Abbreviation", ""))
        if driver_id:
            abbr_to_driver_id[abbr] = driver_id

        await upsert_driver(conn, {
            "driverId": driver_id,
            "permanentNumber": str(row.get("DriverNumber", "")),
            "code": row.get("Abbreviation"),
            "givenName": row.get("FirstName", ""),
            "familyName": row.get("LastName", ""),
            "nationality": row.get("CountryCode", ""),
        })
        await upsert_constructor(conn, {
            "constructorId": cid,
            "name": team_name,
            "nationality": "",
        })

        classified = str(row.get("ClassifiedPosition") or "")
        finish_pos = _int(row.get("Position")) if classified not in ("R", "D", "W", "E", "N") else None
        status_id = await upsert_status(conn, str(row.get("Status") or "Unknown"))

        await conn.execute(
            """
            INSERT INTO results(
                raceId, driverId, constructorId, number, grid,
                position, positionText, positionOrder, points, laps,
                time, milliseconds, fastestLap, rank,
                fastestLapTime, fastestLapSpeed, statusId
            ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
            ON CONFLICT (raceId, driverId) DO UPDATE SET
                position=EXCLUDED.position, positionText=EXCLUDED.positionText,
                points=EXCLUDED.points, laps=EXCLUDED.laps,
                time=EXCLUDED.time, statusId=EXCLUDED.statusId
            """,
            race_id, driver_id, cid,
            _int(row.get("DriverNumber")), _int(row.get("GridPosition")),
            finish_pos, classified or str(finish_pos or ""),
            _int(row.get("Position")),
            _float_safe(row.get("Points")),
            laps_by_abbr.get(abbr),
            _timedelta_str(row.get("Time")), None,
            None, None, None, None,
            status_id,
        )

    return abbr_to_driver_id


async def _upsert_qualifying_from_session(
    conn: asyncpg.Connection,
    race_id: int,
    quali_session: fastf1.core.Session,
) -> None:
    """Upsert qualifying results from a FastF1 Qualifying session."""
    results = quali_session.results
    if results is None or results.empty:
        return

    for _, row in results.iterrows():
        driver_id = str(row.get("DriverId") or "")
        team_name = str(row.get("TeamName") or "")
        cid = _constructor_id(team_name)

        await upsert_driver(conn, {
            "driverId": driver_id,
            "permanentNumber": str(row.get("DriverNumber", "")),
            "code": row.get("Abbreviation"),
            "givenName": row.get("FirstName", ""),
            "familyName": row.get("LastName", ""),
            "nationality": row.get("CountryCode", ""),
        })
        await upsert_constructor(conn, {
            "constructorId": cid,
            "name": team_name,
            "nationality": "",
        })

        await conn.execute(
            """
            INSERT INTO qualifying(raceId, driverId, constructorId, number, position, q1, q2, q3)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (raceId, driverId) DO UPDATE SET
                position=EXCLUDED.position, q1=EXCLUDED.q1,
                q2=EXCLUDED.q2, q3=EXCLUDED.q3
            """,
            race_id, driver_id, cid,
            _int(row.get("DriverNumber")),
            _int(row.get("Position")),
            _timedelta_str(row.get("Q1")),
            _timedelta_str(row.get("Q2")),
            _timedelta_str(row.get("Q3")),
        )


async def _upsert_lap_times_from_session(
    conn: asyncpg.Connection,
    race_id: int,
    race_session: fastf1.core.Session,
    abbr_to_driver_id: dict[str, str],
) -> int:
    """Upsert per-lap times from a FastF1 Race session."""
    laps = race_session.laps
    if laps is None or laps.empty:
        return 0

    rows = []
    for _, lap in laps.iterrows():
        driver_id = abbr_to_driver_id.get(str(lap.get("Driver", "")))
        lap_num = _int(lap.get("LapNumber"))
        if not driver_id or lap_num is None:
            continue
        rows.append((race_id, driver_id, lap_num, None, _timedelta_str(lap.get("LapTime")), None))

    if rows:
        await conn.executemany(
            """
            INSERT INTO lap_times(raceId, driverId, lap, position, time, milliseconds)
            VALUES($1,$2,$3,$4,$5,$6)
            ON CONFLICT (raceId, driverId, lap) DO NOTHING
            """,
            rows,
        )
    return len(rows)


async def _upsert_pit_stops_from_session(
    conn: asyncpg.Connection,
    race_id: int,
    race_session: fastf1.core.Session,
    abbr_to_driver_id: dict[str, str],
) -> int:
    """Reconstruct and upsert pit stops from FastF1 stint changes."""
    laps = race_session.laps
    if laps is None or laps.empty:
        return 0

    rows = []
    for abbr, driver_laps in laps.groupby("Driver"):
        driver_id = abbr_to_driver_id.get(abbr)
        if not driver_id:
            continue

        driver_laps = driver_laps.sort_values("LapNumber")
        pit_in_laps = driver_laps[driver_laps["PitInTime"].notna()]

        for stop_num, (_, in_lap) in enumerate(pit_in_laps.iterrows(), start=1):
            lap_num = _int(in_lap.get("LapNumber"))
            pit_in = in_lap.get("PitInTime")
            next_stint = driver_laps[driver_laps["Stint"] == in_lap["Stint"] + 1]
            pit_out = next_stint["PitOutTime"].iloc[0] if not next_stint.empty else None

            duration = None
            if pit_in is not None and pit_out is not None:
                try:
                    dur_s = (pit_out - pit_in).total_seconds()
                    if dur_s > 0:
                        duration = f"{dur_s:.3f}"
                except Exception:
                    pass

            rows.append((race_id, driver_id, stop_num, lap_num, None, duration, None))

    if rows:
        await conn.executemany(
            """
            INSERT INTO pit_stops(raceId, driverId, stop, lap, time, duration, milliseconds)
            VALUES($1,$2,$3,$4,$5::time,$6,$7)
            ON CONFLICT (raceId, driverId, stop) DO NOTHING
            """,
            rows,
        )
    return len(rows)


async def _recompute_standings(
    conn: asyncpg.Connection,
    race_id: int,
    year: int,
    round_num: int,
) -> None:
    """Recompute driver and constructor standings from accumulated DB results."""
    driver_rows = await conn.fetch(
        """
        WITH totals AS (
            SELECT res.driverId,
                   COALESCE(SUM(res.points), 0) AS points,
                   COUNT(CASE WHEN res.position = 1 THEN 1 END) AS wins
            FROM results res
            JOIN races r ON res.raceId = r.raceId
            WHERE r.year = $1 AND r.round <= $2
            GROUP BY res.driverId
        )
        SELECT driverId, points, wins,
               RANK() OVER (ORDER BY points DESC, wins DESC) AS position
        FROM totals ORDER BY position
        """,
        year, round_num,
    )
    for row in driver_rows:
        pos = int(row["position"])
        await conn.execute(
            """
            INSERT INTO driver_standings(raceId, driverId, points, position, positionText, wins)
            VALUES($1,$2,$3,$4,$5,$6)
            ON CONFLICT (raceId, driverId) DO UPDATE SET
                points=EXCLUDED.points, position=EXCLUDED.position,
                positionText=EXCLUDED.positionText, wins=EXCLUDED.wins
            """,
            race_id, row["driverid"], float(row["points"]), pos, str(pos), int(row["wins"]),
        )

    constructor_rows = await conn.fetch(
        """
        WITH totals AS (
            SELECT res.constructorId,
                   COALESCE(SUM(res.points), 0) AS points,
                   COUNT(CASE WHEN res.position = 1 THEN 1 END) AS wins
            FROM results res
            JOIN races r ON res.raceId = r.raceId
            WHERE r.year = $1 AND r.round <= $2
            GROUP BY res.constructorId
        )
        SELECT constructorId, points, wins,
               RANK() OVER (ORDER BY points DESC, wins DESC) AS position
        FROM totals ORDER BY position
        """,
        year, round_num,
    )
    for row in constructor_rows:
        pos = int(row["position"])
        await conn.execute(
            """
            INSERT INTO constructor_standings(raceId, constructorId, points, position, positionText, wins)
            VALUES($1,$2,$3,$4,$5,$6)
            ON CONFLICT (raceId, constructorId) DO UPDATE SET
                points=EXCLUDED.points, position=EXCLUDED.position,
                positionText=EXCLUDED.positionText, wins=EXCLUDED.wins
            """,
            race_id, row["constructorid"], float(row["points"]), pos, str(pos), int(row["wins"]),
        )


# ---------------------------------------------------------------------------
# Per-season import
# ---------------------------------------------------------------------------

async def import_season(conn: asyncpg.Connection, year: int, from_round: int = 1) -> None:
    log.info("=== Season %d (starting from round %d) ===", year, from_round)

    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
    except Exception as exc:
        log.error("  Could not fetch %d schedule: %s — skipping", year, exc)
        return

    if schedule.empty:
        log.info("  No events found for %d — skipping", year)
        return

    for _, event in schedule.iterrows():
        round_num = int(event["RoundNumber"])
        event_name = str(event["EventName"])

        if round_num < from_round:
            log.info("  Round %d — %s (skipping, before --from-round)", round_num, event_name)
            continue

        # If event date is in the future, skip to avoid incomplete data and unnecessary retries
        event_date = _date(str(event["EventDate"])[:10])
        if event_date and event_date > date.today():
            log.info("  Round %d — %s (skipping, event date %s in the future)", round_num, event_name, event_date)
            continue

        try:
            race_id = await upsert_race_from_event(conn, year, round_num, event)
            log.info("  Round %d — %s (raceId=%d)", round_num, event_name, race_id)
        except Exception as exc:
            log.warning("  Round %d race record error: %s — skipping", round_num, exc)
            continue

        # Qualifying
        try:
            quali = fastf1.get_session(year, round_num, "Q")
            await _load_session_with_retry(quali, telemetry=False, weather=False, messages=False)
            await _upsert_qualifying_from_session(conn, race_id, quali)
            log.info("    Qualifying: %d results", len(quali.results) if quali.results is not None else 0)
        except RateLimitError:
            raise
        except Exception as exc:
            log.warning("    Qualifying error for Round %d: %s", round_num, exc)

        await asyncio.sleep(SESSION_DELAY)

        # Race results, laps, pit stops
        try:
            race_sess = fastf1.get_session(year, round_num, "R")
            await _load_session_with_retry(race_sess, telemetry=False, weather=False, messages=False)
            abbr_map = await _upsert_results_from_session(conn, race_id, race_sess)
            log.info("    Race results: %d", len(race_sess.results) if race_sess.results is not None else 0)

            lap_count = await _upsert_lap_times_from_session(conn, race_id, race_sess, abbr_map)
            log.info("    Lap times: %d", lap_count)

            pit_count = await _upsert_pit_stops_from_session(conn, race_id, race_sess, abbr_map)
            log.info("    Pit stops: %d", pit_count)

            await _recompute_standings(conn, race_id, year, round_num)
            log.info("    Standings recomputed")
        except RateLimitError:
            raise
        except Exception as exc:
            log.warning("    Race session error for Round %d: %s", round_num, exc)

        await asyncio.sleep(ROUND_DELAY)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main(from_season: int, to_season: int, from_round: int = 1) -> None:
    db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
    if not db_url:
        log.error("DATABASE_URL environment variable not set.")
        sys.exit(1)

    os.makedirs(CACHE_DIR, exist_ok=True)
    fastf1.Cache.enable_cache(CACHE_DIR)
    log.info("FastF1 cache: %s", CACHE_DIR)

    conn = await asyncpg.connect(db_url)
    log.info("Connected to database.")

    seasons = list(range(from_season, to_season + 1))
    log.info("Importing %d seasons (%d–%d)", len(seasons), from_season, to_season)

    for year in seasons:
        # from_round only applies to the first season being imported
        start_round = from_round if year == from_season else 1
        try:
            await import_season(conn, year, from_round=start_round)
        except RateLimitError as exc:
            log.error("Persistent failure (rate limit / server error): %s", exc)
            last = await conn.fetchrow(
                "SELECT raceId, year, round, name FROM races ORDER BY year DESC, round DESC LIMIT 1"
            )
            if last:
                next_round = last["round"] + 1
                print(
                    f"\n\033[1mStopped due to repeated failures. Last record saved:\033[0m\n"
                    f"  Season : {last['year']}\n"
                    f"  Round  : {last['round']}\n"
                    f"  Race   : {last['name']}\n"
                    f"\nRestart with:\n"
                    f"  python build_db.py --from-season {last['year']} --from-round {next_round}\n"
                )
            else:
                print("\nStopped due to repeated failures. No records were saved yet.\n")
            break
        except Exception as exc:
            log.error("Season %d failed: %s — continuing", year, exc)

    await conn.close()
    log.info("Import complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import F1 history from FastF1 into PostgreSQL")
    parser.add_argument("--season", type=int, help="Import a single season")
    parser.add_argument(
        "--from-season", type=int, default=DEFAULT_FROM,
        help=f"Start year (default: {DEFAULT_FROM})",
    )
    parser.add_argument("--to-season", type=int, default=date.today().year, help="End year (default: current year)")
    parser.add_argument("--from-round", type=int, default=1, help="Start from this round number within the first season (default: 1)")
    args = parser.parse_args()

    if args.season:
        args.from_season = args.season
        args.to_season = args.season

    asyncio.run(main(args.from_season, args.to_season, args.from_round))

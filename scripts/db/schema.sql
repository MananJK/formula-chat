-- =============================================================================
-- Formula Chat — PostgreSQL Schema
-- =============================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for text search on names

-- =============================================================================
-- Reference tables
-- =============================================================================

CREATE TABLE IF NOT EXISTS seasons (
    year        INT PRIMARY KEY,
    url         TEXT
);

CREATE TABLE IF NOT EXISTS circuits (
    circuitId   TEXT PRIMARY KEY,
    circuitRef  TEXT NOT NULL,
    name        TEXT NOT NULL,
    location    TEXT,
    country     TEXT,
    lat         NUMERIC(9, 6),
    lng         NUMERIC(9, 6),
    alt         INT,
    url         TEXT
);

CREATE TABLE IF NOT EXISTS drivers (
    driverId        TEXT PRIMARY KEY,
    driverRef       TEXT NOT NULL,
    number          INT,
    code            CHAR(3),
    forename        TEXT NOT NULL,
    surname         TEXT NOT NULL,
    dob             DATE,
    nationality     TEXT,
    url             TEXT
);

CREATE TABLE IF NOT EXISTS constructors (
    constructorId   TEXT PRIMARY KEY,
    constructorRef  TEXT NOT NULL,
    name            TEXT NOT NULL,
    nationality     TEXT,
    url             TEXT
);

CREATE TABLE IF NOT EXISTS status (
    statusId    SERIAL PRIMARY KEY,
    status      TEXT NOT NULL UNIQUE
);

-- =============================================================================
-- Race calendar
-- =============================================================================

CREATE TABLE IF NOT EXISTS races (
    raceId          SERIAL PRIMARY KEY,
    year            INT NOT NULL REFERENCES seasons(year),
    round           INT NOT NULL,
    circuitId       TEXT NOT NULL REFERENCES circuits(circuitId),
    name            TEXT NOT NULL,
    date            DATE,
    time            TIME,
    url             TEXT,
    fp1_date        DATE,
    fp1_time        TIME,
    fp2_date        DATE,
    fp2_time        TIME,
    fp3_date        DATE,
    fp3_time        TIME,
    quali_date      DATE,
    quali_time      TIME,
    sprint_date     DATE,
    sprint_time     TIME,
    UNIQUE (year, round)
);

-- =============================================================================
-- Session results
-- =============================================================================

CREATE TABLE IF NOT EXISTS results (
    resultId            SERIAL PRIMARY KEY,
    raceId              INT NOT NULL REFERENCES races(raceId),
    driverId            TEXT NOT NULL REFERENCES drivers(driverId),
    constructorId       TEXT NOT NULL REFERENCES constructors(constructorId),
    number              INT,
    grid                INT,
    position            INT,
    positionText        TEXT,
    positionOrder       INT,
    points              NUMERIC(5, 2),
    laps                INT,
    time                TEXT,           -- e.g. "1:35:35.617" or "+5.123s"
    milliseconds        BIGINT,
    fastestLap          INT,
    rank                INT,
    fastestLapTime      TEXT,
    fastestLapSpeed     NUMERIC(7, 3),
    statusId            INT REFERENCES status(statusId),
    UNIQUE (raceId, driverId)
);

CREATE TABLE IF NOT EXISTS qualifying (
    qualifyId       SERIAL PRIMARY KEY,
    raceId          INT NOT NULL REFERENCES races(raceId),
    driverId        TEXT NOT NULL REFERENCES drivers(driverId),
    constructorId   TEXT NOT NULL REFERENCES constructors(constructorId),
    number          INT,
    position        INT,
    q1              TEXT,
    q2              TEXT,
    q3              TEXT,
    UNIQUE (raceId, driverId)
);

CREATE TABLE IF NOT EXISTS sprint_results (
    sprintResultId  SERIAL PRIMARY KEY,
    raceId          INT NOT NULL REFERENCES races(raceId),
    driverId        TEXT NOT NULL REFERENCES drivers(driverId),
    constructorId   TEXT NOT NULL REFERENCES constructors(constructorId),
    number          INT,
    grid            INT,
    position        INT,
    positionText    TEXT,
    positionOrder   INT,
    points          NUMERIC(5, 2),
    laps            INT,
    time            TEXT,
    milliseconds    BIGINT,
    fastestLap      INT,
    fastestLapTime  TEXT,
    statusId        INT REFERENCES status(statusId),
    UNIQUE (raceId, driverId)
);

-- =============================================================================
-- Lap-level data
-- =============================================================================

CREATE TABLE IF NOT EXISTS lap_times (
    raceId          INT NOT NULL REFERENCES races(raceId),
    driverId        TEXT NOT NULL REFERENCES drivers(driverId),
    lap             INT NOT NULL,
    position        INT,
    time            TEXT,           -- e.g. "1:32.456"
    milliseconds    INT,
    PRIMARY KEY (raceId, driverId, lap)
);

CREATE TABLE IF NOT EXISTS pit_stops (
    raceId          INT NOT NULL REFERENCES races(raceId),
    driverId        TEXT NOT NULL REFERENCES drivers(driverId),
    stop            INT NOT NULL,
    lap             INT NOT NULL,
    time            TIME,           -- time of day of pit stop
    duration        TEXT,           -- e.g. "23.456"
    milliseconds    INT,
    PRIMARY KEY (raceId, driverId, stop)
);

-- =============================================================================
-- Standings
-- =============================================================================

CREATE TABLE IF NOT EXISTS driver_standings (
    driverStandingsId   SERIAL PRIMARY KEY,
    raceId              INT NOT NULL REFERENCES races(raceId),
    driverId            TEXT NOT NULL REFERENCES drivers(driverId),
    points              NUMERIC(7, 2),
    position            INT,
    positionText        TEXT,
    wins                INT,
    UNIQUE (raceId, driverId)
);

CREATE TABLE IF NOT EXISTS constructor_standings (
    constructorStandingsId  SERIAL PRIMARY KEY,
    raceId                  INT NOT NULL REFERENCES races(raceId),
    constructorId           TEXT NOT NULL REFERENCES constructors(constructorId),
    points                  NUMERIC(7, 2),
    position                INT,
    positionText            TEXT,
    wins                    INT,
    UNIQUE (raceId, constructorId)
);

CREATE TABLE IF NOT EXISTS constructor_results (
    constructorResultsId    SERIAL PRIMARY KEY,
    raceId                  INT NOT NULL REFERENCES races(raceId),
    constructorId           TEXT NOT NULL REFERENCES constructors(constructorId),
    points                  NUMERIC(5, 2),
    status                  TEXT,
    UNIQUE (raceId, constructorId)
);

-- =============================================================================
-- RAG knowledge base
-- =============================================================================

CREATE TABLE IF NOT EXISTS f1_knowledge (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    category        TEXT NOT NULL,      -- driver | team | circuit | regulation | race_report
    title           TEXT,
    content         TEXT NOT NULL,
    content_hash    TEXT NOT NULL,      -- SHA-256 of content for idempotent upsert
    embedding       VECTOR(1536) NOT NULL,
    token_count     INT,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    season          INT,
    event_name      TEXT,
    UNIQUE (source, content_hash)
);

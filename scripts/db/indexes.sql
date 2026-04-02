-- =============================================================================
-- Formula Chat — Index Definitions
-- Run after schema.sql and after data import for best performance
-- =============================================================================

-- races
CREATE INDEX IF NOT EXISTS idx_races_year           ON races(year);
CREATE INDEX IF NOT EXISTS idx_races_circuitid      ON races(circuitId);

-- results
CREATE INDEX IF NOT EXISTS idx_results_raceid           ON results(raceId);
CREATE INDEX IF NOT EXISTS idx_results_driverid         ON results(driverId);
CREATE INDEX IF NOT EXISTS idx_results_constructorid    ON results(constructorId);
CREATE INDEX IF NOT EXISTS idx_results_position         ON results(position);

-- qualifying
CREATE INDEX IF NOT EXISTS idx_qualifying_raceid        ON qualifying(raceId);
CREATE INDEX IF NOT EXISTS idx_qualifying_driverid      ON qualifying(driverId);

-- lap_times
CREATE INDEX IF NOT EXISTS idx_lap_times_raceid         ON lap_times(raceId);
CREATE INDEX IF NOT EXISTS idx_lap_times_driverid       ON lap_times(driverId);

-- pit_stops
CREATE INDEX IF NOT EXISTS idx_pit_stops_raceid         ON pit_stops(raceId);
CREATE INDEX IF NOT EXISTS idx_pit_stops_driverid       ON pit_stops(driverId);

-- standings
CREATE INDEX IF NOT EXISTS idx_driver_standings_raceid  ON driver_standings(raceId);
CREATE INDEX IF NOT EXISTS idx_driver_standings_driverid ON driver_standings(driverId);
CREATE INDEX IF NOT EXISTS idx_constructor_standings_raceid ON constructor_standings(raceId);

-- driver name search (trigram for fuzzy matching e.g. "Lewis" → Hamilton)
CREATE INDEX IF NOT EXISTS idx_drivers_surname_trgm     ON drivers USING gin(surname gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_drivers_forename_trgm    ON drivers USING gin(forename gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_constructors_name_trgm   ON constructors USING gin(name gin_trgm_ops);

-- f1_knowledge — HNSW vector index for fast approximate nearest-neighbour search
CREATE INDEX IF NOT EXISTS idx_knowledge_embedding
    ON f1_knowledge
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_knowledge_category   ON f1_knowledge(category);
CREATE INDEX IF NOT EXISTS idx_knowledge_season     ON f1_knowledge(season);
CREATE INDEX IF NOT EXISTS idx_knowledge_source     ON f1_knowledge(source);

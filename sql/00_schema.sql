-- ModivCare Rides Efficiency
-- Schema DDL for analytical tables
-- Target: Data warehouse (Snowflake, BigQuery, Redshift, PostgreSQL)

-- ============================================
-- DIMENSION: Drivers
-- ============================================
CREATE TABLE dim_drivers (
    driver_id VARCHAR(50) PRIMARY KEY,
    driver_name VARCHAR(255),
    vehicle_capacity INTEGER,
    home_region VARCHAR(50),
    hire_date DATE,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_drivers_region ON dim_drivers(home_region);

-- ============================================
-- DIMENSION: Regions
-- ============================================
CREATE TABLE dim_regions (
    region_id VARCHAR(50) PRIMARY KEY,
    region_name VARCHAR(100),
    center_lat DECIMAL(10, 6),
    center_lng DECIMAL(10, 6),
    area_sq_miles DECIMAL(10, 2)
);

-- ============================================
-- DIMENSION: Trip Types
-- ============================================
CREATE TABLE dim_trip_types (
    trip_type_id SERIAL PRIMARY KEY,
    trip_type VARCHAR(50) UNIQUE NOT NULL,
    priority_level INTEGER DEFAULT 1,
    typical_duration_minutes INTEGER
);

-- ============================================
-- FACT: Trips
-- ============================================
CREATE TABLE fact_trips (
    trip_id VARCHAR(100) PRIMARY KEY,
    member_id VARCHAR(100) NOT NULL,
    driver_id VARCHAR(50) REFERENCES dim_drivers(driver_id),
    region VARCHAR(50),
    trip_type VARCHAR(50),

    -- Location data
    pickup_lat DECIMAL(10, 6),
    pickup_lng DECIMAL(10, 6),
    dropoff_lat DECIMAL(10, 6),
    dropoff_lng DECIMAL(10, 6),

    -- Time data
    requested_pickup_time TIMESTAMP,
    scheduled_pickup_time TIMESTAMP,
    actual_pickup_time TIMESTAMP,
    actual_dropoff_time TIMESTAMP,

    -- Distance metrics
    planned_distance_miles DECIMAL(10, 2),
    actual_distance_miles DECIMAL(10, 2),

    -- Capacity
    vehicle_capacity INTEGER,
    num_passengers INTEGER DEFAULT 1,

    -- Status flags
    late_pickup_flag BOOLEAN DEFAULT FALSE,
    late_dropoff_flag BOOLEAN DEFAULT FALSE,
    cancellation_reason VARCHAR(255),

    -- Calculated metrics (populated by ETL)
    pickup_delay_minutes INTEGER,
    route_deviation_ratio DECIMAL(5, 3),
    capacity_utilization DECIMAL(5, 3),

    -- Metadata
    trip_date DATE,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trips_driver ON fact_trips(driver_id);
CREATE INDEX idx_trips_region ON fact_trips(region);
CREATE INDEX idx_trips_date ON fact_trips(trip_date);
CREATE INDEX idx_trips_type ON fact_trips(trip_type);

-- ============================================
-- FACT: Trip Efficiency Scores
-- One row per trip with calculated efficiency index
-- ============================================
CREATE TABLE fact_trip_efficiency (
    trip_id VARCHAR(100) PRIMARY KEY REFERENCES fact_trips(trip_id),

    -- Component scores (0-100 scale)
    on_time_score DECIMAL(5, 2),
    route_deviation_score DECIMAL(5, 2),
    capacity_utilization_score DECIMAL(5, 2),
    idle_time_score DECIMAL(5, 2),

    -- Weighted composite index
    efficiency_index DECIMAL(5, 2),

    -- Classification
    efficiency_tier VARCHAR(20),  -- High, Medium, Low

    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- VIEW: Trip Details with Efficiency
-- ============================================
CREATE OR REPLACE VIEW v_trip_details AS
SELECT
    t.trip_id,
    t.member_id,
    t.driver_id,
    t.region,
    t.trip_type,
    t.trip_date,
    t.scheduled_pickup_time,
    t.actual_pickup_time,
    t.pickup_delay_minutes,
    t.planned_distance_miles,
    t.actual_distance_miles,
    t.route_deviation_ratio,
    t.num_passengers,
    t.vehicle_capacity,
    t.capacity_utilization,
    t.late_pickup_flag,
    t.late_dropoff_flag,
    e.efficiency_index,
    e.efficiency_tier
FROM fact_trips t
LEFT JOIN fact_trip_efficiency e ON t.trip_id = e.trip_id
WHERE t.cancellation_reason IS NULL;

-- ============================================
-- VIEW: Driver Performance Summary
-- ============================================
CREATE OR REPLACE VIEW v_driver_performance AS
SELECT
    t.driver_id,
    COUNT(*) AS total_trips,
    ROUND(AVG(e.efficiency_index), 1) AS avg_efficiency,
    ROUND(100.0 * SUM(CASE WHEN t.late_pickup_flag THEN 1 ELSE 0 END) / COUNT(*), 1) AS late_pickup_pct,
    ROUND(AVG(t.actual_distance_miles), 1) AS avg_miles_per_trip,
    ROUND(AVG(t.capacity_utilization), 2) AS avg_capacity_util,
    SUM(t.actual_distance_miles) AS total_miles
FROM fact_trips t
LEFT JOIN fact_trip_efficiency e ON t.trip_id = e.trip_id
WHERE t.cancellation_reason IS NULL
GROUP BY t.driver_id;

-- ============================================
-- VIEW: Region Performance Summary
-- ============================================
CREATE OR REPLACE VIEW v_region_performance AS
SELECT
    t.region,
    COUNT(*) AS total_trips,
    COUNT(DISTINCT t.driver_id) AS unique_drivers,
    ROUND(AVG(e.efficiency_index), 1) AS avg_efficiency,
    ROUND(100.0 * SUM(CASE WHEN t.late_pickup_flag THEN 1 ELSE 0 END) / COUNT(*), 1) AS late_pickup_pct,
    ROUND(AVG(t.route_deviation_ratio), 3) AS avg_route_deviation,
    SUM(t.actual_distance_miles) AS total_miles
FROM fact_trips t
LEFT JOIN fact_trip_efficiency e ON t.trip_id = e.trip_id
WHERE t.cancellation_reason IS NULL
GROUP BY t.region;

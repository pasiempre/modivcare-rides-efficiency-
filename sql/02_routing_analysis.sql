-- ModivCare Rides Efficiency
-- Routing Simulation Analysis Queries
-- Compare routing strategies and identify optimization opportunities

-- ============================================
-- 1. Executive Summary KPIs
-- ============================================
SELECT
    COUNT(*) AS total_trips,
    COUNT(DISTINCT driver_id) AS active_drivers,
    COUNT(DISTINCT region) AS regions_served,

    -- On-time performance
    ROUND(100.0 * SUM(CASE WHEN late_pickup_flag = FALSE THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct,

    -- Distance metrics
    ROUND(SUM(actual_distance_miles), 0) AS total_miles_driven,
    ROUND(AVG(actual_distance_miles), 1) AS avg_miles_per_trip,

    -- Route efficiency
    ROUND(AVG(route_deviation_ratio), 3) AS avg_route_deviation,

    -- Wasted miles (excess over planned)
    ROUND(SUM(actual_distance_miles - planned_distance_miles), 0) AS total_wasted_miles,
    ROUND(100.0 * SUM(actual_distance_miles - planned_distance_miles) / SUM(planned_distance_miles), 1) AS wasted_miles_pct,

    -- Capacity utilization
    ROUND(AVG(capacity_utilization) * 100, 1) AS avg_capacity_util_pct

FROM fact_trips
WHERE cancellation_reason IS NULL;


-- ============================================
-- 2. Hour-of-Day Analysis
-- Identify peak inefficiency windows
-- ============================================
SELECT
    EXTRACT(HOUR FROM scheduled_pickup_time) AS hour_of_day,
    COUNT(*) AS trip_count,

    -- On-time by hour
    ROUND(100.0 * SUM(CASE WHEN late_pickup_flag = FALSE THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct,

    -- Avg delay
    ROUND(AVG(pickup_delay_minutes), 1) AS avg_delay_minutes,

    -- Route efficiency
    ROUND(AVG(route_deviation_ratio), 3) AS avg_route_deviation,

    -- Drivers active
    COUNT(DISTINCT driver_id) AS drivers_active

FROM fact_trips
WHERE cancellation_reason IS NULL
GROUP BY EXTRACT(HOUR FROM scheduled_pickup_time)
ORDER BY hour_of_day;


-- ============================================
-- 3. Driver Utilization Analysis
-- Identify over/under-utilized drivers
-- ============================================
WITH driver_daily AS (
    SELECT
        driver_id,
        trip_date,
        COUNT(*) AS trips_per_day,
        SUM(actual_distance_miles) AS miles_per_day,
        ROUND(AVG(capacity_utilization) * 100, 1) AS avg_capacity_util
    FROM fact_trips
    WHERE cancellation_reason IS NULL
    GROUP BY driver_id, trip_date
)
SELECT
    driver_id,
    COUNT(DISTINCT trip_date) AS days_active,
    ROUND(AVG(trips_per_day), 1) AS avg_trips_per_day,
    ROUND(AVG(miles_per_day), 1) AS avg_miles_per_day,
    ROUND(AVG(avg_capacity_util), 1) AS avg_capacity_util,

    -- Utilization tier
    CASE
        WHEN AVG(trips_per_day) < 5 THEN 'Underutilized'
        WHEN AVG(trips_per_day) > 12 THEN 'Overloaded'
        ELSE 'Balanced'
    END AS utilization_tier

FROM driver_daily
GROUP BY driver_id
ORDER BY avg_trips_per_day DESC;


-- ============================================
-- 4. Route Deviation Hotspots
-- Regions/times with worst routing
-- ============================================
SELECT
    region,
    trip_type,
    COUNT(*) AS trips,
    ROUND(AVG(route_deviation_ratio), 3) AS avg_deviation,
    ROUND(AVG(actual_distance_miles - planned_distance_miles), 2) AS avg_excess_miles,
    SUM(actual_distance_miles - planned_distance_miles) AS total_excess_miles,
    'Routing optimization target' AS recommendation
FROM fact_trips
WHERE cancellation_reason IS NULL
  AND route_deviation_ratio > 1.1  -- More than 10% deviation
GROUP BY region, trip_type
HAVING COUNT(*) >= 10
ORDER BY total_excess_miles DESC
LIMIT 15;


-- ============================================
-- 5. Cancellation Analysis
-- ============================================
SELECT
    cancellation_reason,
    COUNT(*) AS cancellation_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_cancellations
FROM fact_trips
WHERE cancellation_reason IS NOT NULL
GROUP BY cancellation_reason
ORDER BY cancellation_count DESC;


-- ============================================
-- 6. Dialysis Trip Performance (High Priority)
-- ============================================
SELECT
    region,
    COUNT(*) AS dialysis_trips,
    ROUND(100.0 * SUM(CASE WHEN late_pickup_flag = FALSE THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct,
    ROUND(AVG(pickup_delay_minutes), 1) AS avg_delay_min,
    ROUND(AVG(route_deviation_ratio), 3) AS avg_deviation,
    CASE
        WHEN SUM(CASE WHEN late_pickup_flag = FALSE THEN 1 ELSE 0 END) * 1.0 / COUNT(*) >= 0.95
            THEN 'Meeting SLA'
        ELSE 'Below SLA - immediate attention needed'
    END AS sla_status
FROM fact_trips
WHERE trip_type = 'dialysis'
  AND cancellation_reason IS NULL
GROUP BY region
ORDER BY on_time_pct ASC;


-- ============================================
-- 7. Routing Strategy Simulation Comparison
-- Compare hypothetical outcomes
-- ============================================
-- This query would compare actual results against simulated strategies
-- In practice, simulation results are stored in a separate table

WITH actual_performance AS (
    SELECT
        'Actual' AS strategy,
        ROUND(100.0 * SUM(CASE WHEN late_pickup_flag = FALSE THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct,
        ROUND(SUM(actual_distance_miles), 0) AS total_miles,
        ROUND(AVG(capacity_utilization) * 100, 1) AS avg_capacity_pct
    FROM fact_trips
    WHERE cancellation_reason IS NULL
)
SELECT * FROM actual_performance;

-- Additional rows would come from simulation results table:
-- UNION ALL SELECT 'FCFS' AS strategy, on_time_pct, total_miles, capacity_pct FROM simulation_results WHERE strategy = 'fcfs'
-- UNION ALL SELECT 'Shortest-Distance-Next' AS strategy, ... FROM simulation_results WHERE strategy = 'sdn'
-- UNION ALL SELECT 'Time-Window-Aware' AS strategy, ... FROM simulation_results WHERE strategy = 'twa'


-- ============================================
-- 8. Potential Savings Analysis
-- ============================================
SELECT
    'Total Wasted Miles (>10% deviation)' AS metric,
    ROUND(SUM(actual_distance_miles - planned_distance_miles), 0) AS value,
    'miles' AS unit
FROM fact_trips
WHERE cancellation_reason IS NULL
  AND route_deviation_ratio > 1.1

UNION ALL

SELECT
    'Est. Fuel Cost Savings ($3/gal, 15mpg)' AS metric,
    ROUND(SUM(actual_distance_miles - planned_distance_miles) / 15 * 3, 0) AS value,
    'dollars' AS unit
FROM fact_trips
WHERE cancellation_reason IS NULL
  AND route_deviation_ratio > 1.1

UNION ALL

SELECT
    'Late Trips (addressable)' AS metric,
    COUNT(*) AS value,
    'trips' AS unit
FROM fact_trips
WHERE late_pickup_flag = TRUE
  AND cancellation_reason IS NULL;


-- ============================================
-- 9. Week-over-Week Performance
-- ============================================
SELECT
    DATE_TRUNC('week', trip_date) AS week_start,
    COUNT(*) AS trips,
    ROUND(100.0 * SUM(CASE WHEN late_pickup_flag = FALSE THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct,
    ROUND(AVG(route_deviation_ratio), 3) AS avg_deviation,
    ROUND(AVG(capacity_utilization) * 100, 1) AS avg_capacity_pct,

    -- Week-over-week change in on-time %
    ROUND(
        100.0 * SUM(CASE WHEN late_pickup_flag = FALSE THEN 1 ELSE 0 END) / COUNT(*) -
        LAG(100.0 * SUM(CASE WHEN late_pickup_flag = FALSE THEN 1 ELSE 0 END) / COUNT(*))
            OVER (ORDER BY DATE_TRUNC('week', trip_date)),
        1
    ) AS on_time_wow_change

FROM fact_trips
WHERE cancellation_reason IS NULL
GROUP BY DATE_TRUNC('week', trip_date)
ORDER BY week_start;

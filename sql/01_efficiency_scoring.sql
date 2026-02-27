-- ModivCare Rides Efficiency
-- Efficiency Scoring Queries
-- Implements the weighted efficiency index (35/25/20/20)

-- ============================================
-- Scoring Weight Configuration
-- ============================================
-- on_time_performance: 35%
-- route_deviation:     25%
-- capacity_utilization: 20%
-- idle_time:           20%

-- ============================================
-- 1. Calculate Trip-Level Efficiency Scores
-- ============================================
WITH trip_metrics AS (
    SELECT
        trip_id,
        driver_id,
        region,
        trip_type,
        trip_date,

        -- On-time performance (higher is better)
        -- Score based on pickup delay: 0 min = 100, 10+ min late = 0
        CASE
            WHEN pickup_delay_minutes <= 0 THEN 100
            WHEN pickup_delay_minutes >= 10 THEN 0
            ELSE 100 - (pickup_delay_minutes * 10)
        END AS on_time_score,

        -- Route deviation (lower deviation is better)
        -- Score: 1.0 ratio = 100, 1.5+ ratio = 0
        CASE
            WHEN route_deviation_ratio <= 1.0 THEN 100
            WHEN route_deviation_ratio >= 1.5 THEN 0
            ELSE 100 - ((route_deviation_ratio - 1.0) * 200)
        END AS route_deviation_score,

        -- Capacity utilization (higher is better)
        -- Score: 100% util = 100, 0% = 0
        ROUND(capacity_utilization * 100, 0) AS capacity_score,

        -- Idle time score (calculated separately if idle_minutes available)
        -- Placeholder: assume 80 if not calculated
        80 AS idle_time_score

    FROM fact_trips
    WHERE cancellation_reason IS NULL
),
weighted_scores AS (
    SELECT
        trip_id,
        driver_id,
        region,
        trip_type,
        trip_date,
        on_time_score,
        route_deviation_score,
        capacity_score,
        idle_time_score,

        -- Apply weights (35/25/20/20)
        ROUND(
            (on_time_score * 0.35) +
            (route_deviation_score * 0.25) +
            (capacity_score * 0.20) +
            (idle_time_score * 0.20),
            1
        ) AS efficiency_index
    FROM trip_metrics
)
SELECT
    trip_id,
    driver_id,
    region,
    trip_type,
    trip_date,
    on_time_score,
    route_deviation_score,
    capacity_score,
    idle_time_score,
    efficiency_index,
    CASE
        WHEN efficiency_index >= 80 THEN 'High'
        WHEN efficiency_index >= 60 THEN 'Medium'
        ELSE 'Low'
    END AS efficiency_tier
FROM weighted_scores;


-- ============================================
-- 2. Driver Efficiency Summary
-- ============================================
SELECT
    t.driver_id,
    COUNT(*) AS total_trips,

    -- Efficiency metrics
    ROUND(AVG(e.efficiency_index), 1) AS avg_efficiency_index,
    ROUND(MIN(e.efficiency_index), 1) AS min_efficiency,
    ROUND(MAX(e.efficiency_index), 1) AS max_efficiency,

    -- Component averages
    ROUND(AVG(e.on_time_score), 1) AS avg_on_time_score,
    ROUND(AVG(e.route_deviation_score), 1) AS avg_route_score,
    ROUND(AVG(e.capacity_utilization_score), 1) AS avg_capacity_score,

    -- On-time performance
    ROUND(100.0 * SUM(CASE WHEN t.late_pickup_flag = FALSE THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct,

    -- Miles metrics
    ROUND(SUM(t.actual_distance_miles), 0) AS total_miles,
    ROUND(AVG(t.actual_distance_miles), 1) AS avg_miles_per_trip,

    -- Tier distribution
    SUM(CASE WHEN e.efficiency_tier = 'High' THEN 1 ELSE 0 END) AS high_tier_trips,
    SUM(CASE WHEN e.efficiency_tier = 'Low' THEN 1 ELSE 0 END) AS low_tier_trips

FROM fact_trips t
JOIN fact_trip_efficiency e ON t.trip_id = e.trip_id
WHERE t.cancellation_reason IS NULL
GROUP BY t.driver_id
ORDER BY avg_efficiency_index DESC;


-- ============================================
-- 3. Region Efficiency Comparison
-- ============================================
SELECT
    t.region,
    COUNT(*) AS total_trips,
    COUNT(DISTINCT t.driver_id) AS unique_drivers,

    -- Efficiency metrics
    ROUND(AVG(e.efficiency_index), 1) AS avg_efficiency,
    ROUND(STDDEV(e.efficiency_index), 1) AS efficiency_stddev,

    -- On-time performance
    ROUND(100.0 * SUM(CASE WHEN t.late_pickup_flag = FALSE THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct,

    -- Route metrics
    ROUND(AVG(t.route_deviation_ratio), 3) AS avg_route_deviation,
    ROUND(AVG(t.actual_distance_miles), 1) AS avg_trip_distance,

    -- Capacity utilization
    ROUND(AVG(t.capacity_utilization) * 100, 1) AS avg_capacity_util_pct

FROM fact_trips t
JOIN fact_trip_efficiency e ON t.trip_id = e.trip_id
WHERE t.cancellation_reason IS NULL
GROUP BY t.region
ORDER BY avg_efficiency DESC;


-- ============================================
-- 4. Trip Type Efficiency Analysis
-- ============================================
SELECT
    t.trip_type,
    COUNT(*) AS total_trips,

    -- Efficiency
    ROUND(AVG(e.efficiency_index), 1) AS avg_efficiency,

    -- On-time (critical for dialysis)
    ROUND(100.0 * SUM(CASE WHEN t.late_pickup_flag = FALSE THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct,

    -- Distance
    ROUND(AVG(t.actual_distance_miles), 1) AS avg_miles,

    -- Capacity
    ROUND(AVG(t.capacity_utilization) * 100, 1) AS avg_capacity_pct

FROM fact_trips t
JOIN fact_trip_efficiency e ON t.trip_id = e.trip_id
WHERE t.cancellation_reason IS NULL
GROUP BY t.trip_type
ORDER BY avg_efficiency DESC;


-- ============================================
-- 5. Daily Efficiency Trend
-- ============================================
SELECT
    t.trip_date,
    COUNT(*) AS total_trips,
    ROUND(AVG(e.efficiency_index), 1) AS avg_efficiency,
    ROUND(100.0 * SUM(CASE WHEN t.late_pickup_flag = FALSE THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_pct,
    SUM(t.actual_distance_miles) AS total_miles,
    COUNT(DISTINCT t.driver_id) AS active_drivers
FROM fact_trips t
JOIN fact_trip_efficiency e ON t.trip_id = e.trip_id
WHERE t.cancellation_reason IS NULL
GROUP BY t.trip_date
ORDER BY t.trip_date;


-- ============================================
-- 6. Bottom Performers - Improvement Targets
-- ============================================
SELECT
    driver_id,
    COUNT(*) AS total_trips,
    ROUND(AVG(efficiency_index), 1) AS avg_efficiency,
    ROUND(100.0 * SUM(CASE WHEN efficiency_tier = 'Low' THEN 1 ELSE 0 END) / COUNT(*), 1) AS low_tier_pct,
    'Coaching candidate - review routing patterns' AS recommendation
FROM fact_trips t
JOIN fact_trip_efficiency e USING (trip_id)
WHERE cancellation_reason IS NULL
GROUP BY driver_id
HAVING AVG(efficiency_index) < 60
   AND COUNT(*) >= 10  -- Minimum sample
ORDER BY avg_efficiency ASC
LIMIT 10;


-- ============================================
-- 7. Efficiency Index Distribution
-- ============================================
SELECT
    CASE
        WHEN efficiency_index >= 90 THEN '90-100 (Excellent)'
        WHEN efficiency_index >= 80 THEN '80-89 (Good)'
        WHEN efficiency_index >= 70 THEN '70-79 (Acceptable)'
        WHEN efficiency_index >= 60 THEN '60-69 (Needs Improvement)'
        ELSE 'Below 60 (Critical)'
    END AS efficiency_bucket,
    COUNT(*) AS trip_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_total
FROM fact_trip_efficiency
GROUP BY 1
ORDER BY 1 DESC;

"""Efficiency scoring algorithm for NEMT trips."""

import pandas as pd
import numpy as np
from typing import Dict, Optional

from .config import EFFICIENCY_WEIGHTS, PROCESSED_DIR


def calculate_on_time_score(df: pd.DataFrame) -> pd.Series:
    """
    Calculate on-time performance score (0-100).
    
    Higher is better. Based on pickup delay.
    Cancelled trips get NaN score (not included in aggregates).
    """
    # Start with NaN for all rows
    score = pd.Series(np.nan, index=df.index)
    
    # Only score non-cancelled trips
    non_cancelled = ~df["is_cancelled"]
    
    # Convert delay to score: 0 delay = 100, 30+ min delay = 0
    delay = df.loc[non_cancelled, "pickup_delay_minutes"].fillna(0).clip(lower=-10, upper=30)
    score.loc[non_cancelled] = (100 - ((delay + 10) / 40 * 100)).clip(0, 100)
    
    return score


def calculate_route_deviation_score(df: pd.DataFrame) -> pd.Series:
    """
    Calculate route efficiency score (0-100).
    
    Compares actual travel time to expected based on distance.
    """
    # Expected time at 25 mph average
    expected_minutes = (df["distance_miles"] / 25) * 60
    actual_minutes = df["trip_duration_minutes"]
    
    # Deviation ratio
    deviation = (actual_minutes - expected_minutes) / expected_minutes.replace(0, 1)
    
    # Score: 0% deviation = 100, 100%+ deviation = 0
    score = 100 - (deviation.clip(0, 1) * 100)
    return score.clip(0, 100)


def calculate_capacity_score(df: pd.DataFrame) -> pd.Series:
    """
    Calculate capacity utilization score (0-100).
    
    Based on passenger-to-capacity ratio.
    """
    utilization = df["capacity_utilization"].fillna(0)
    # Score directly from utilization percentage
    return (utilization * 100).clip(0, 100)


def calculate_idle_score(df: pd.DataFrame) -> pd.Series:
    """
    Calculate idle time score (0-100).
    
    Based on ratio of productive time vs idle time per driver-day.
    """
    # Productive ratio: trip minutes / total minutes in shift (assume 8 hours)
    shift_minutes = 480  # 8 hours
    productive_ratio = df["daily_minutes"].fillna(0) / shift_minutes
    
    # Score based on productive ratio (50%+ productive = 100)
    score = (productive_ratio / 0.5 * 100).clip(0, 100)
    return score


def calculate_efficiency_index(
    df: pd.DataFrame,
    weights: Optional[Dict[str, float]] = None
) -> pd.DataFrame:
    """
    Calculate overall efficiency index for each trip.
    
    Args:
        df: DataFrame with trip features
        weights: Custom weights for scoring components
        
    Returns:
        DataFrame with efficiency scores added
    """
    if weights is None:
        weights = EFFICIENCY_WEIGHTS
    
    df = df.copy()
    
    # Calculate component scores
    df["score_on_time"] = calculate_on_time_score(df)
    df["score_route"] = calculate_route_deviation_score(df)
    df["score_capacity"] = calculate_capacity_score(df)
    df["score_idle"] = calculate_idle_score(df)
    
    # Weighted average
    df["efficiency_index"] = (
        df["score_on_time"] * weights["on_time_performance"] +
        df["score_route"] * weights["route_deviation"] +
        df["score_capacity"] * weights["capacity_utilization"] +
        df["score_idle"] * weights["idle_time"]
    )
    
    return df


def score_drivers(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate efficiency scores by driver."""
    active = df[~df["is_cancelled"]]
    
    driver_scores = active.groupby("driver_id").agg({
        "efficiency_index": "mean",
        "score_on_time": "mean",
        "score_route": "mean",
        "score_capacity": "mean",
        "score_idle": "mean",
        "trip_id": "count",
        "is_late_pickup": "mean",
    }).reset_index()
    
    driver_scores.columns = [
        "driver_id", "avg_efficiency", "avg_on_time_score",
        "avg_route_score", "avg_capacity_score", "avg_idle_score",
        "total_trips", "late_pickup_rate"
    ]
    
    driver_scores = driver_scores.sort_values("avg_efficiency", ascending=False)
    driver_scores["efficiency_rank"] = range(1, len(driver_scores) + 1)
    
    return driver_scores


def score_regions(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate efficiency scores by region."""
    active = df[~df["is_cancelled"]]
    
    region_scores = active.groupby("region").agg({
        "efficiency_index": "mean",
        "score_on_time": "mean",
        "trip_id": "count",
        "is_late_pickup": "mean",
        "distance_miles": "mean",
    }).reset_index()
    
    region_scores.columns = [
        "region", "avg_efficiency", "avg_on_time_score",
        "total_trips", "late_pickup_rate", "avg_distance"
    ]
    
    region_scores = region_scores.sort_values("avg_efficiency", ascending=False)
    
    return region_scores


def save_scored_data(
    trips_df: pd.DataFrame,
    drivers_df: pd.DataFrame,
    regions_df: pd.DataFrame
) -> None:
    """Save all scored data."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    
    trips_df.to_csv(PROCESSED_DIR / "trips_scored.csv", index=False)
    drivers_df.to_csv(PROCESSED_DIR / "driver_scores.csv", index=False)
    regions_df.to_csv(PROCESSED_DIR / "region_scores.csv", index=False)
    
    print(f"Saved scored data to {PROCESSED_DIR}")


def run_scoring_pipeline(input_file: str = "trips_features.csv") -> tuple:
    """Run full scoring pipeline."""
    filepath = PROCESSED_DIR / input_file
    df = pd.read_csv(filepath, parse_dates=[
        "requested_pickup_time",
        "scheduled_pickup_time",
        "actual_pickup_time",
        "actual_dropoff_time",
    ])
    
    print("Calculating efficiency index...")
    df_scored = calculate_efficiency_index(df)
    
    print("Scoring drivers...")
    drivers = score_drivers(df_scored)
    
    print("Scoring regions...")
    regions = score_regions(df_scored)
    
    save_scored_data(df_scored, drivers, regions)
    
    return df_scored, drivers, regions


if __name__ == "__main__":
    run_scoring_pipeline()

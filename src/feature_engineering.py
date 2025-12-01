"""Feature engineering for NEMT efficiency analysis."""

import pandas as pd
import numpy as np
from typing import Optional

from .config import INTERIM_DIR, PROCESSED_DIR


def load_cleaned_trips(filename: str = "trips_cleaned.csv") -> pd.DataFrame:
    """Load cleaned trip data."""
    filepath = INTERIM_DIR / filename
    df = pd.read_csv(filepath, parse_dates=[
        "requested_pickup_time",
        "scheduled_pickup_time",
        "actual_pickup_time",
        "actual_dropoff_time",
    ])
    return df


def add_trip_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add trip-level features."""
    df = df.copy()
    
    # Speed estimate (actual)
    df["avg_speed_mph"] = np.where(
        df["trip_duration_minutes"] > 0,
        df["distance_miles"] / (df["trip_duration_minutes"] / 60),
        np.nan
    )
    
    # Capacity utilization
    df["capacity_utilization"] = df["num_passengers"] / df["vehicle_capacity"]
    
    # Distance efficiency (actual vs straight-line)
    # Assume actual driven distance is ~1.3x straight-line in urban areas
    df["estimated_driven_miles"] = df["distance_miles_calc"] * 1.3
    
    # Time of day categories
    df["time_of_day"] = pd.cut(
        df["scheduled_hour"],
        bins=[0, 6, 12, 17, 21, 24],
        labels=["early_morning", "morning", "afternoon", "evening", "night"],
        include_lowest=True
    )
    
    return df


def add_driver_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add driver-level aggregated features."""
    df = df.copy()
    
    # Non-cancelled trips only for driver stats
    active_trips = df[~df["is_cancelled"]]
    
    # Driver daily stats
    driver_daily = active_trips.groupby(["driver_id", "scheduled_date"]).agg({
        "trip_id": "count",
        "distance_miles": "sum",
        "trip_duration_minutes": "sum",
        "is_late_pickup": "mean",
        "capacity_utilization": "mean",
    }).reset_index()
    
    driver_daily.columns = [
        "driver_id", "scheduled_date", 
        "daily_trips", "daily_miles", "daily_minutes",
        "daily_late_rate", "daily_capacity_util"
    ]
    
    # Merge back
    df = df.merge(
        driver_daily,
        on=["driver_id", "scheduled_date"],
        how="left"
    )
    
    return df


def add_region_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add region-level aggregated features."""
    df = df.copy()
    
    # Region daily stats
    active_trips = df[~df["is_cancelled"]]
    
    region_daily = active_trips.groupby(["region", "scheduled_date"]).agg({
        "trip_id": "count",
        "is_late_pickup": "mean",
        "avg_speed_mph": "mean",
    }).reset_index()
    
    region_daily.columns = [
        "region", "scheduled_date",
        "region_daily_trips", "region_late_rate", "region_avg_speed"
    ]
    
    df = df.merge(
        region_daily,
        on=["region", "scheduled_date"],
        how="left"
    )
    
    return df


def create_feature_set(df: pd.DataFrame) -> pd.DataFrame:
    """Create full feature set."""
    print("Adding trip features...")
    df = add_trip_features(df)
    
    print("Adding driver features...")
    df = add_driver_features(df)
    
    print("Adding region features...")
    df = add_region_features(df)
    
    return df


def save_features(df: pd.DataFrame, filename: str = "trips_features.csv") -> None:
    """Save feature-engineered data."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    filepath = PROCESSED_DIR / filename
    df.to_csv(filepath, index=False)
    print(f"Saved {len(df)} trips with features to {filepath}")


def run_feature_pipeline(
    input_file: str = "trips_cleaned.csv",
    output_file: str = "trips_features.csv"
) -> pd.DataFrame:
    """Run full feature engineering pipeline."""
    df = load_cleaned_trips(input_file)
    df = create_feature_set(df)
    save_features(df, output_file)
    return df


if __name__ == "__main__":
    run_feature_pipeline()

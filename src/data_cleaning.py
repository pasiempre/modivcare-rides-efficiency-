"""Data cleaning and preprocessing for NEMT rides."""

import pandas as pd
import numpy as np
from typing import Optional

from .config import RAW_DIR, INTERIM_DIR, LATE_THRESHOLD_MINUTES
from .utils import haversine_distance, minutes_between


def load_raw_trips(filename: str = "trips.csv") -> pd.DataFrame:
    """Load raw trip data."""
    filepath = RAW_DIR / filename
    df = pd.read_csv(filepath, parse_dates=[
        "requested_pickup_time",
        "scheduled_pickup_time",
        "actual_pickup_time",
        "actual_dropoff_time",
    ])
    return df


def clean_trips(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and standardize trip data.
    
    Operations:
    - Remove invalid coordinates
    - Recalculate distances if needed
    - Standardize timestamps
    - Add derived time columns
    """
    df = df.copy()
    
    # Remove trips with invalid coordinates
    coord_cols = ["pickup_lat", "pickup_lng", "dropoff_lat", "dropoff_lng"]
    df = df.dropna(subset=coord_cols)
    
    # Ensure coordinates are within valid ranges
    valid_coords = (
        (df["pickup_lat"].between(-90, 90)) &
        (df["dropoff_lat"].between(-90, 90)) &
        (df["pickup_lng"].between(-180, 180)) &
        (df["dropoff_lng"].between(-180, 180))
    )
    df = df[valid_coords]
    
    # Recalculate distance for consistency
    df["distance_miles_calc"] = df.apply(
        lambda row: haversine_distance(
            row["pickup_lat"], row["pickup_lng"],
            row["dropoff_lat"], row["dropoff_lng"]
        ),
        axis=1
    )
    
    # Add time-derived columns
    df["scheduled_date"] = df["scheduled_pickup_time"].dt.date
    df["scheduled_hour"] = df["scheduled_pickup_time"].dt.hour
    df["scheduled_day_of_week"] = df["scheduled_pickup_time"].dt.dayofweek
    df["is_weekend"] = df["scheduled_day_of_week"].isin([5, 6])
    
    # Flag cancelled trips FIRST (before computing time-based features)
    df["is_cancelled"] = df["cancellation_reason"].notna()
    
    # Calculate pickup delay (only for non-cancelled trips)
    df["pickup_delay_minutes"] = np.nan
    non_cancelled_mask = ~df["is_cancelled"]
    df.loc[non_cancelled_mask, "pickup_delay_minutes"] = df.loc[non_cancelled_mask].apply(
        lambda row: minutes_between(
            row["scheduled_pickup_time"],
            row["actual_pickup_time"]
        ),
        axis=1
    )
    
    # Calculate trip duration (only for non-cancelled trips)
    df["trip_duration_minutes"] = np.nan
    df.loc[non_cancelled_mask, "trip_duration_minutes"] = df.loc[non_cancelled_mask].apply(
        lambda row: minutes_between(
            row["actual_pickup_time"],
            row["actual_dropoff_time"]
        ),
        axis=1
    )
    
    # Recalculate late flags based on threshold (NaN for cancelled trips)
    df["is_late_pickup"] = df["pickup_delay_minutes"] > LATE_THRESHOLD_MINUTES
    
    return df


def save_cleaned_data(df: pd.DataFrame, filename: str = "trips_cleaned.csv") -> None:
    """Save cleaned data to interim directory."""
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    filepath = INTERIM_DIR / filename
    df.to_csv(filepath, index=False)
    print(f"Saved {len(df)} cleaned trips to {filepath}")


def run_cleaning_pipeline(
    input_file: str = "trips.csv",
    output_file: str = "trips_cleaned.csv"
) -> pd.DataFrame:
    """Run full cleaning pipeline."""
    print("Loading raw data...")
    df = load_raw_trips(input_file)
    print(f"Loaded {len(df)} trips")
    
    print("Cleaning data...")
    df_clean = clean_trips(df)
    print(f"Cleaned to {len(df_clean)} valid trips")
    
    save_cleaned_data(df_clean, output_file)
    
    return df_clean


if __name__ == "__main__":
    run_cleaning_pipeline()

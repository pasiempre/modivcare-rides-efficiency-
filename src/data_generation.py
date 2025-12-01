"""Synthetic data generation for NEMT rides."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
from faker import Faker

from .config import (
    RANDOM_SEED,
    DEFAULT_NUM_TRIPS,
    DEFAULT_NUM_DRIVERS,
    DEFAULT_NUM_REGIONS,
    GEO_BOUNDS,
    TRIP_TYPES,
    OPERATING_HOURS,
    VEHICLE_CAPACITIES,
    RAW_DIR,
)
from .utils import set_seed, haversine_distance


fake = Faker()
Faker.seed(RANDOM_SEED)


def generate_trips(
    num_trips: int = DEFAULT_NUM_TRIPS,
    num_drivers: int = DEFAULT_NUM_DRIVERS,
    num_regions: int = DEFAULT_NUM_REGIONS,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    Generate synthetic NEMT trip data.
    
    Args:
        num_trips: Number of trips to generate
        num_drivers: Number of unique drivers
        num_regions: Number of geographic regions
        start_date: Start date for trip generation
        end_date: End date for trip generation
        seed: Random seed for reproducibility
        
    Returns:
        DataFrame with synthetic trip data
    """
    set_seed(seed)
    
    if start_date is None:
        start_date = datetime(2025, 1, 1)
    if end_date is None:
        end_date = datetime(2025, 3, 31)
    
    # Generate base data
    trips = []
    
    regions = [f"Region_{i+1}" for i in range(num_regions)]
    driver_ids = [f"DRV_{i:04d}" for i in range(num_drivers)]
    member_ids = [f"MBR_{i:06d}" for i in range(num_trips * 2)]  # More members than trips
    
    trip_type_names = list(TRIP_TYPES.keys())
    trip_type_probs = list(TRIP_TYPES.values())
    
    for i in range(num_trips):
        # Random date within range
        days_range = (end_date - start_date).days
        trip_date = start_date + timedelta(days=np.random.randint(0, days_range))
        
        # Random time within operating hours
        hour = np.random.randint(OPERATING_HOURS["start"], OPERATING_HOURS["end"])
        minute = np.random.choice([0, 15, 30, 45])
        requested_time = trip_date.replace(hour=hour, minute=minute, second=0)
        
        # Scheduled time (usually within 30 min of requested)
        schedule_offset = int(np.random.randint(-15, 30))
        scheduled_time = requested_time + timedelta(minutes=schedule_offset)
        
        # Actual pickup time (with some variance and potential delays)
        delay_minutes = int(np.random.choice(
            [-5, 0, 0, 0, 5, 10, 15, 20, 30],  # Weighted toward on-time
            p=[0.05, 0.30, 0.25, 0.15, 0.10, 0.07, 0.04, 0.02, 0.02]
        ))
        actual_pickup = scheduled_time + timedelta(minutes=delay_minutes)
        
        # Generate coordinates
        pickup_lat = np.random.uniform(GEO_BOUNDS["lat_min"], GEO_BOUNDS["lat_max"])
        pickup_lng = np.random.uniform(GEO_BOUNDS["lng_min"], GEO_BOUNDS["lng_max"])
        
        # Dropoff typically within reasonable distance
        dropoff_lat = pickup_lat + np.random.uniform(-0.1, 0.1)
        dropoff_lng = pickup_lng + np.random.uniform(-0.1, 0.1)
        
        # Calculate distance
        distance = haversine_distance(pickup_lat, pickup_lng, dropoff_lat, dropoff_lng)
        
        # Travel time based on distance (avg 25 mph in urban)
        travel_minutes = (distance / 25) * 60 + np.random.randint(5, 15)
        actual_dropoff = actual_pickup + timedelta(minutes=travel_minutes)
        
        # Vehicle and passengers
        vehicle_capacity = np.random.choice(VEHICLE_CAPACITIES)
        num_passengers = np.random.randint(1, min(vehicle_capacity, 3) + 1)
        
        # Late flags
        late_pickup = delay_minutes > 10
        expected_dropoff = scheduled_time + timedelta(minutes=(distance / 25) * 60 + 10)
        late_dropoff = actual_dropoff > expected_dropoff + timedelta(minutes=10)
        
        # Cancellation (small percentage)
        cancelled = np.random.random() < 0.03
        cancellation_reason = None
        if cancelled:
            cancellation_reason = np.random.choice([
                "member_no_show",
                "member_cancelled",
                "driver_unavailable",
                "weather",
                "vehicle_issue",
            ])
            actual_pickup = None
            actual_dropoff = None
        
        trips.append({
            "trip_id": f"TRP_{i:06d}",
            "member_id": np.random.choice(member_ids),
            "driver_id": np.random.choice(driver_ids),
            "pickup_lat": pickup_lat,
            "pickup_lng": pickup_lng,
            "dropoff_lat": dropoff_lat,
            "dropoff_lng": dropoff_lng,
            "requested_pickup_time": requested_time,
            "scheduled_pickup_time": scheduled_time,
            "actual_pickup_time": actual_pickup,
            "actual_dropoff_time": actual_dropoff,
            "distance_miles": round(distance, 2),
            "trip_type": np.random.choice(trip_type_names, p=trip_type_probs),
            "vehicle_capacity": vehicle_capacity,
            "num_passengers": num_passengers,
            "late_pickup_flag": late_pickup if not cancelled else None,
            "late_dropoff_flag": late_dropoff if not cancelled else None,
            "cancellation_reason": cancellation_reason,
            "region": np.random.choice(regions),
        })
    
    return pd.DataFrame(trips)


def generate_drivers(
    num_drivers: int = DEFAULT_NUM_DRIVERS,
    num_regions: int = DEFAULT_NUM_REGIONS,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    Generate synthetic driver data.
    
    Args:
        num_drivers: Number of drivers to generate
        num_regions: Number of regions
        seed: Random seed for reproducibility
        
    Returns:
        DataFrame with synthetic driver data
    """
    set_seed(seed)
    
    regions = [f"Region_{i+1}" for i in range(num_regions)]
    
    drivers = []
    for i in range(num_drivers):
        lat = np.random.uniform(GEO_BOUNDS["lat_min"], GEO_BOUNDS["lat_max"])
        lng = np.random.uniform(GEO_BOUNDS["lng_min"], GEO_BOUNDS["lng_max"])
        
        drivers.append({
            "driver_id": f"DRV_{i:04d}",
            "driver_name": fake.name(),
            "vehicle_capacity": np.random.choice(VEHICLE_CAPACITIES),
            "region": np.random.choice(regions),
            "home_lat": lat,
            "home_lng": lng,
            "years_experience": np.random.randint(1, 15),
            "rating": round(np.random.uniform(3.5, 5.0), 2),
            "is_active": np.random.random() > 0.05,  # 95% active
        })
    
    return pd.DataFrame(drivers)


def save_raw_data(df: pd.DataFrame, filename: str = "trips.csv") -> None:
    """Save generated data to raw directory."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    filepath = RAW_DIR / filename
    df.to_csv(filepath, index=False)
    print(f"Saved {len(df)} records to {filepath}")


if __name__ == "__main__":
    print("Generating synthetic NEMT data...")
    
    # Generate trips
    trips_df = generate_trips()
    save_raw_data(trips_df, "trips.csv")
    
    # Generate drivers
    drivers_df = generate_drivers()
    save_raw_data(drivers_df, "drivers.csv")
    
    print("Done!")

"""ModivCare Rides Efficiency - Configuration Module"""

from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"

MODELS_DIR = PROJECT_ROOT / "models"
REPORTS_DIR = PROJECT_ROOT / "reports" / "figures"

# Data generation settings
RANDOM_SEED = 42
DEFAULT_NUM_TRIPS = 5000
DEFAULT_NUM_DRIVERS = 150
DEFAULT_NUM_REGIONS = 5

# Geographic bounds (example: Phoenix, AZ metro area)
GEO_BOUNDS = {
    "lat_min": 33.2,
    "lat_max": 33.7,
    "lng_min": -112.3,
    "lng_max": -111.8,
}

# Trip type distributions
TRIP_TYPES = {
    "dialysis": 0.35,
    "physical_therapy": 0.20,
    "follow_up": 0.15,
    "specialist": 0.12,
    "mental_health": 0.10,
    "other": 0.08,
}

# Time windows
OPERATING_HOURS = {
    "start": 6,   # 6 AM
    "end": 20,    # 8 PM
}

# Efficiency scoring weights
EFFICIENCY_WEIGHTS = {
    "on_time_performance": 0.35,
    "route_deviation": 0.25,
    "capacity_utilization": 0.20,
    "idle_time": 0.20,
}

# Thresholds
LATE_THRESHOLD_MINUTES = 10  # Minutes after scheduled time to count as late
IDLE_THRESHOLD_MINUTES = 15  # Excessive idle time threshold

# Vehicle settings
VEHICLE_CAPACITIES = [1, 2, 4, 6]  # Possible vehicle capacities
DEFAULT_VEHICLE_CAPACITY = 4

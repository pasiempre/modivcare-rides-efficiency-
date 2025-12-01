"""Utility functions for the ModivCare Rides Efficiency project."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Tuple

from .config import RANDOM_SEED


def set_seed(seed: int = RANDOM_SEED) -> None:
    """Set random seed for reproducibility."""
    np.random.seed(seed)


def haversine_distance(
    lat1: float, lng1: float, lat2: float, lng2: float
) -> float:
    """
    Calculate the great-circle distance between two points on Earth.
    
    Args:
        lat1, lng1: Coordinates of first point
        lat2, lng2: Coordinates of second point
        
    Returns:
        Distance in miles
    """
    R = 3959  # Earth's radius in miles
    
    lat1, lng1, lat2, lng2 = map(np.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlng / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    
    return R * c


def minutes_between(start: datetime, end: datetime) -> float:
    """Calculate minutes between two timestamps."""
    if pd.isna(start) or pd.isna(end):
        return np.nan
    return (end - start).total_seconds() / 60


def format_duration(minutes: float) -> str:
    """Format duration in minutes to human-readable string."""
    if pd.isna(minutes):
        return "N/A"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def calculate_time_window(
    base_time: datetime, 
    window_minutes: int = 30
) -> Tuple[datetime, datetime]:
    """Calculate a time window around a base time."""
    half_window = timedelta(minutes=window_minutes / 2)
    return (base_time - half_window, base_time + half_window)


def normalize_score(value: float, min_val: float, max_val: float) -> float:
    """Normalize a value to 0-100 scale."""
    if max_val == min_val:
        return 50.0
    return ((value - min_val) / (max_val - min_val)) * 100

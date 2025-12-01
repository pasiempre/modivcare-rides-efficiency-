"""Routing simulation engine for NEMT optimization."""

import pandas as pd
import numpy as np
from typing import List, Dict, Callable, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import PROCESSED_DIR, RANDOM_SEED
from .utils import haversine_distance, set_seed


@dataclass
class SimulationResult:
    """Results from a routing simulation run."""
    strategy_name: str
    total_trips: int
    on_time_rate: float
    total_miles: float
    avg_trip_duration: float
    avg_idle_time: float
    utilization_rate: float
    
    def to_dict(self) -> Dict:
        return {
            "strategy": self.strategy_name,
            "total_trips": self.total_trips,
            "on_time_rate": round(self.on_time_rate * 100, 2),
            "total_miles": round(self.total_miles, 2),
            "avg_trip_duration": round(self.avg_trip_duration, 2),
            "avg_idle_time": round(self.avg_idle_time, 2),
            "utilization_rate": round(self.utilization_rate * 100, 2),
        }


def assign_fcfs(trips: pd.DataFrame, drivers: List[str]) -> pd.DataFrame:
    """
    First-Come-First-Served assignment strategy.
    
    Assigns trips to drivers in order of request time,
    using the next available driver.
    """
    trips = trips.sort_values("requested_pickup_time").copy()
    driver_available_at = {d: datetime.min for d in drivers}
    
    assignments = []
    
    for _, trip in trips.iterrows():
        # Find first available driver
        available_drivers = [
            d for d, t in driver_available_at.items()
            if t <= trip["scheduled_pickup_time"]
        ]
        
        if not available_drivers:
            # All busy, pick one that becomes free soonest
            assigned_driver = min(driver_available_at, key=driver_available_at.get)
        else:
            assigned_driver = available_drivers[0]
        
        # Estimate when driver will be free after this trip
        trip_duration = trip["trip_duration_minutes"] if pd.notna(trip["trip_duration_minutes"]) else 30
        finish_time = trip["scheduled_pickup_time"] + timedelta(minutes=trip_duration + 10)
        driver_available_at[assigned_driver] = finish_time
        
        assignments.append({
            "trip_id": trip["trip_id"],
            "assigned_driver": assigned_driver,
            "strategy": "FCFS",
        })
    
    return pd.DataFrame(assignments)


def assign_nearest(trips: pd.DataFrame, drivers: List[str], driver_locations: Dict) -> pd.DataFrame:
    """
    Nearest-driver assignment strategy.
    
    Assigns each trip to the closest available driver.
    """
    trips = trips.sort_values("scheduled_pickup_time").copy()
    driver_available_at = {d: datetime.min for d in drivers}
    
    assignments = []
    
    for _, trip in trips.iterrows():
        # Find available drivers
        available_drivers = [
            d for d, t in driver_available_at.items()
            if t <= trip["scheduled_pickup_time"]
        ]
        
        if not available_drivers:
            available_drivers = drivers  # All busy, consider all
        
        # Find nearest driver
        pickup_loc = (trip["pickup_lat"], trip["pickup_lng"])
        distances = {
            d: haversine_distance(
                driver_locations[d][0], driver_locations[d][1],
                pickup_loc[0], pickup_loc[1]
            )
            for d in available_drivers
        }
        assigned_driver = min(distances, key=distances.get)
        
        # Update driver location and availability
        driver_locations[assigned_driver] = (trip["dropoff_lat"], trip["dropoff_lng"])
        trip_duration = trip["trip_duration_minutes"] if pd.notna(trip["trip_duration_minutes"]) else 30
        finish_time = trip["scheduled_pickup_time"] + timedelta(minutes=trip_duration + 10)
        driver_available_at[assigned_driver] = finish_time
        
        assignments.append({
            "trip_id": trip["trip_id"],
            "assigned_driver": assigned_driver,
            "strategy": "Nearest",
        })
    
    return pd.DataFrame(assignments)


def assign_capacity_aware(
    trips: pd.DataFrame, 
    drivers: List[str],
    driver_capacities: Dict[str, int]
) -> pd.DataFrame:
    """
    Capacity-aware assignment strategy.
    
    Prioritizes matching vehicle capacity to passenger count.
    """
    trips = trips.sort_values("scheduled_pickup_time").copy()
    driver_available_at = {d: datetime.min for d in drivers}
    
    assignments = []
    
    for _, trip in trips.iterrows():
        passengers = trip["num_passengers"]
        
        # Find available drivers
        available_drivers = [
            d for d, t in driver_available_at.items()
            if t <= trip["scheduled_pickup_time"]
        ]
        
        if not available_drivers:
            available_drivers = drivers
        
        # Score by capacity match (prefer smallest vehicle that fits)
        def capacity_score(driver):
            cap = driver_capacities[driver]
            if cap < passengers:
                return 1000  # Penalty for too small
            return cap - passengers  # Prefer minimal excess
        
        assigned_driver = min(available_drivers, key=capacity_score)
        
        trip_duration = trip["trip_duration_minutes"] if pd.notna(trip["trip_duration_minutes"]) else 30
        finish_time = trip["scheduled_pickup_time"] + timedelta(minutes=trip_duration + 10)
        driver_available_at[assigned_driver] = finish_time
        
        assignments.append({
            "trip_id": trip["trip_id"],
            "assigned_driver": assigned_driver,
            "strategy": "Capacity-Aware",
        })
    
    return pd.DataFrame(assignments)


def simulate_strategy(
    trips: pd.DataFrame,
    assignments: pd.DataFrame,
    add_noise: bool = True
) -> SimulationResult:
    """
    Simulate trip execution based on assignments and calculate metrics.
    """
    set_seed(RANDOM_SEED)
    
    merged = trips.merge(assignments, on="trip_id")
    
    # Filter to non-cancelled
    active = merged[~merged["is_cancelled"]].copy()
    
    # Calculate simulated metrics with optional noise
    if add_noise:
        # Add some random variation to simulate real-world variance
        noise = np.random.normal(1.0, 0.1, len(active))
        simulated_delay = active["pickup_delay_minutes"].fillna(0) * noise
    else:
        simulated_delay = active["pickup_delay_minutes"].fillna(0)
    
    on_time = (simulated_delay <= 10).mean()
    total_miles = active["distance_miles"].sum()
    avg_duration = active["trip_duration_minutes"].mean()
    
    # Calculate idle time (simplified)
    avg_idle = 15  # Placeholder - would need more complex calculation
    
    # Calculate capacity utilization if not present
    if "capacity_utilization" not in active.columns:
        active["capacity_utilization"] = active["num_passengers"] / active["vehicle_capacity"]
    
    # Utilization
    utilization = active["capacity_utilization"].mean()
    
    return SimulationResult(
        strategy_name=assignments["strategy"].iloc[0],
        total_trips=len(active),
        on_time_rate=on_time,
        total_miles=total_miles,
        avg_trip_duration=avg_duration,
        avg_idle_time=avg_idle,
        utilization_rate=utilization,
    )


def run_simulation_comparison(
    trips: pd.DataFrame,
    num_drivers: int = 50,
    seed: int = RANDOM_SEED
) -> pd.DataFrame:
    """
    Run all routing strategies and compare results.
    
    Note: This is a conceptual comparison using historical durations/delays
    with light stochastic variation, not a full vehicle routing optimization model.
    Strategy differences reflect assignment logic, not recalculated travel dynamics.
    """
    # Seed for reproducibility
    set_seed(seed)
    
    # Setup
    drivers = [f"DRV_{i:04d}" for i in range(num_drivers)]
    
    # Initialize driver locations randomly (now deterministic with seed)
    driver_locations = {
        d: (
            np.random.uniform(33.2, 33.7),
            np.random.uniform(-112.3, -111.8)
        )
        for d in drivers
    }
    
    # Driver capacities (now deterministic with seed)
    driver_capacities = {
        d: np.random.choice([2, 4, 6])
        for d in drivers
    }
    
    results = []
    
    # Run each strategy
    print("Running FCFS strategy...")
    fcfs_assignments = assign_fcfs(trips, drivers)
    fcfs_result = simulate_strategy(trips, fcfs_assignments)
    results.append(fcfs_result.to_dict())
    
    print("Running Nearest-Driver strategy...")
    nearest_assignments = assign_nearest(trips, drivers, driver_locations.copy())
    nearest_result = simulate_strategy(trips, nearest_assignments)
    results.append(nearest_result.to_dict())
    
    print("Running Capacity-Aware strategy...")
    capacity_assignments = assign_capacity_aware(trips, drivers, driver_capacities)
    capacity_result = simulate_strategy(trips, capacity_assignments)
    results.append(capacity_result.to_dict())
    
    return pd.DataFrame(results)


def save_simulation_results(results: pd.DataFrame) -> None:
    """Save simulation comparison results."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    filepath = PROCESSED_DIR / "simulation_results.csv"
    results.to_csv(filepath, index=False)
    print(f"Saved simulation results to {filepath}")


if __name__ == "__main__":
    # Load scored trips
    trips = pd.read_csv(
        PROCESSED_DIR / "trips_scored.csv",
        parse_dates=[
            "requested_pickup_time",
            "scheduled_pickup_time",
            "actual_pickup_time",
            "actual_dropoff_time",
        ]
    )
    
    print("Running routing simulation comparison...")
    results = run_simulation_comparison(trips)
    print("\nResults:")
    print(results.to_string(index=False))
    
    save_simulation_results(results)

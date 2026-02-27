"""Routing simulation engine for NEMT optimization."""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
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
    initial_locations: Dict[str, Tuple[float, float]],
    driver_capacities: Dict[str, int],
    avg_speed_mph: float = 25.0,
    add_noise: bool = True
) -> SimulationResult:
    """
    Simulate trip execution based on assignments and calculate metrics.
    
    This simulation accounts for:
    - Deadhead travel between trips
    - Actual arrival times based on travel dynamics
    - Strategy-dependent delays and idle times
    """
    set_seed(RANDOM_SEED)
    
    merged = trips.merge(assignments, on="trip_id")
    active = merged[~merged["is_cancelled"]].copy()
    
    strategy_name = assignments["strategy"].iloc[0]
    
    total_miles = 0.0
    total_idle_minutes = 0.0
    all_delays = []
    all_utilizations = []
    total_duration = 0.0
    
    # Process each driver's day
    for driver, driver_trips in active.groupby("assigned_driver"):
        # Sort by scheduled pickup
        driver_trips = driver_trips.sort_values("scheduled_pickup_time")
        
        current_loc = initial_locations[driver]
        # Start time is 1 hour before first trip or 6 AM (whichever is later)
        first_trip_time = driver_trips["scheduled_pickup_time"].iloc[0]
        current_time = max(first_trip_time - timedelta(hours=1), first_trip_time.replace(hour=6, minute=0, second=0, microsecond=0))
        
        driver_capacity = driver_capacities[driver]
        
        for _, trip in driver_trips.iterrows():
            pickup_loc = (trip["pickup_lat"], trip["pickup_lng"])
            dropoff_loc = (trip["dropoff_lat"], trip["dropoff_lng"])

            # BUG FIX: Reset driver start time at day boundaries
            # Prevents overnight gaps from being counted as idle time
            trip_date = trip["scheduled_pickup_time"].date()
            if current_time.date() < trip_date:
                # New day: reset to 1 hour before trip or 6 AM (whichever is later)
                current_time = max(
                    trip["scheduled_pickup_time"] - timedelta(hours=1),
                    trip["scheduled_pickup_time"].replace(hour=6, minute=0, second=0, microsecond=0)
                )

            # 1. Deadhead travel
            deadhead_miles = haversine_distance(current_loc[0], current_loc[1], pickup_loc[0], pickup_loc[1])
            deadhead_time_mins = (deadhead_miles / avg_speed_mph) * 60
            
            if add_noise:
                deadhead_time_mins *= np.random.normal(1.0, 0.1)
            
            arrival_at_pickup = current_time + timedelta(minutes=deadhead_time_mins)
            
            # 2. Pickup timing
            # Driver can't pick up before scheduled time unless they arrived early
            # but if they arrive early, they wait (idle)
            actual_pickup_time = max(arrival_at_pickup, trip["scheduled_pickup_time"])
            
            idle_mins = (actual_pickup_time - arrival_at_pickup).total_seconds() / 60
            delay_mins = (actual_pickup_time - trip["scheduled_pickup_time"]).total_seconds() / 60
            
            # 3. Trip execution
            trip_duration = trip["trip_duration_minutes"]
            if add_noise:
                trip_duration *= np.random.normal(1.0, 0.05)
            
            actual_dropoff_time = actual_pickup_time + timedelta(minutes=trip_duration)
            
            # 4. Update metrics
            total_miles += deadhead_miles + trip["distance_miles"]
            total_idle_minutes += idle_mins
            total_duration += trip_duration
            all_delays.append(delay_mins)
            all_utilizations.append(trip["num_passengers"] / driver_capacity)
            
            # 5. Update state
            current_loc = dropoff_loc
            current_time = actual_dropoff_time

    # Aggregate Results
    on_time_rate = np.mean([1 if d <= 10 else 0 for d in all_delays]) if all_delays else 0
    avg_idle = total_idle_minutes / len(active) if len(active) > 0 else 0
    utilization = np.mean(all_utilizations) if all_utilizations else 0
    
    return SimulationResult(
        strategy_name=strategy_name,
        total_trips=len(active),
        on_time_rate=on_time_rate,
        total_miles=total_miles,
        avg_trip_duration=total_duration / len(active) if len(active) > 0 else 0,
        avg_idle_time=avg_idle,
        utilization_rate=utilization,
    )


def run_simulation_comparison(
    trips: pd.DataFrame,
    num_drivers: int = 50,
    seed: int = RANDOM_SEED
) -> pd.DataFrame:
    """
    Run all routing strategies and compare results with dynamic simulation.
    """
    # Seed for reproducibility
    set_seed(seed)
    
    # Ensure time columns are datetimes
    trips = trips.copy()
    for col in ["requested_pickup_time", "scheduled_pickup_time", "actual_pickup_time", "actual_dropoff_time"]:
        if col in trips.columns:
            trips[col] = pd.to_datetime(trips[col])
    
    # Setup
    drivers = [f"DRV_{i:04d}" for i in range(num_drivers)]
    
    # Initialize driver locations randomly (now deterministic with seed)
    initial_locations = {
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
    fcfs_result = simulate_strategy(trips, fcfs_assignments, initial_locations, driver_capacities)
    results.append(fcfs_result.to_dict())
    
    print("Running Nearest-Driver strategy...")
    # nearest_assignments updates locations, so we pass a copy
    nearest_assignments = assign_nearest(trips, drivers, initial_locations.copy())
    nearest_result = simulate_strategy(trips, nearest_assignments, initial_locations, driver_capacities)
    results.append(nearest_result.to_dict())
    
    print("Running Capacity-Aware strategy...")
    capacity_assignments = assign_capacity_aware(trips, drivers, driver_capacities)
    capacity_result = simulate_strategy(trips, capacity_assignments, initial_locations, driver_capacities)
    results.append(capacity_result.to_dict())
    
    return pd.DataFrame(results)


def save_simulation_results(results: pd.DataFrame) -> None:
    """Save simulation comparison results."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    filepath = PROCESSED_DIR / "simulation_results.csv"
    results.to_csv(filepath, index=False)
    print(f"Saved simulation results to {filepath}")


if __name__ == "__main__":
    # Load scored trips or cleaned trips if scored doesn't exist
    scored_path = PROCESSED_DIR / "trips_scored.csv"
    if not scored_path.exists():
        scored_path = PROCESSED_DIR / "trips_with_efficiency.csv"
        
    if not scored_path.exists():
        print(f"Error: Could not find trip data in {PROCESSED_DIR}")
        exit(1)
        
    trips = pd.read_csv(
        scored_path,
        parse_dates=[
            "requested_pickup_time",
            "scheduled_pickup_time",
            "actual_pickup_time",
            "actual_dropoff_time",
        ]
    )
    
    print(f"Running routing simulation comparison using {scored_path.name}...")
    results = run_simulation_comparison(trips)
    print("\nResults:")
    print(results.to_string(index=False))
    
    save_simulation_results(results)
